"""Vertical multi-photo video ("reel") on a recorded voice-over – Yessine Centre.

VIDEO_VARIANT=yessine python3 reel.py                 -> build/yessine/video_silent.mp4
VIDEO_VARIANT=yessine python3 reel.py --still 3 15    -> build/yessine/preview/still_*.png
"""
import argparse
import math
import multiprocessing as mp
import os
import subprocess

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

import gfx as g
import timeline as T
from gfx import ease_back, ease_in, ease_io, ease_out, fade, lerp, place, prog
from render import gold_line, pad_layer, pop_in, portrait, rings, shimmer_pos, text_in, to_arr

SCRIPT = T.read_script()
W, H = SCRIPT.get("size", [1080, 1440])
FPS = T.FPS
SCREEN = SCRIPT["screen"]
BUILD = T.BUILD
PHOTOS = os.path.join(T.HERE, "assets", "yessine")
EM, CAIRO, MONT, PLAY = "ElMessiri.ttf", "Cairo.ttf", "Montserrat.ttf", "PlayfairDisplay.ttf"

# Points of interest in each photo (fractions of width / height) used to aim the camera.
FOCUS = {
    "facade_grand_angle": (0.52, 0.40), "facade_face": (0.55, 0.42), "facade_face2": (0.52, 0.45),
    "hall_ascenseurs": (0.36, 0.55), "couloir_marbre": (0.45, 0.47), "hall_boites": (0.45, 0.50),
    "espace_lumineux": (0.62, 0.42), "grande_piece": (0.45, 0.52), "bureau_vue": (0.66, 0.42),
    "cuisine": (0.60, 0.48), "sanitaire": (0.35, 0.55), "couloir_int": (0.45, 0.45),
}
SIGN = ("facade_face", 0.665, 0.655)      # the "YESSINE CENTRE" sign on the façade
GALLERY = ["bureau_vue", "cuisine", "sanitaire", "couloir_int"]

TL = None
A = {}


# ====================================================================== photos
class Photo:
    def __init__(self, name):
        im = Image.open(os.path.join(PHOTOS, f"{name}.jpg")).convert("RGB")
        a = to_arr(im)
        a = np.clip(a - 0.045 * np.sin(2 * np.pi * a), 0, 1)              # gentle contrast
        a = np.clip(a * np.array([1.025, 1.0, 0.975], np.float32), 0, 1)  # a touch warmer
        self.img = Image.fromarray((a * 255 + 0.5).astype(np.uint8))
        self.w, self.h = self.img.size
        self.s0 = max(W / self.w, H / self.h)          # cover fit
        self.name = name
        self._blur = None

    def view(self, fx, fy, z, sx=0.5, sy=0.5, out=(W, H), blur=False):
        """Crop so that the photo point (fx, fy) lands at the output point (sx, sy) at zoom z."""
        ow, oh = out
        s = max(ow / self.w, oh / self.h) * z
        bw, bh = ow / s, oh / s
        x0 = min(max(fx * self.w - sx * bw, 0), self.w - bw)
        y0 = min(max(fy * self.h - sy * bh, 0), self.h - bh)
        src = self.blurred() if blur else self.img
        k = src.size[0] / self.w
        fr = src.resize((ow, oh), Image.BICUBIC, box=(x0 * k, y0 * k, (x0 + bw) * k, (y0 + bh) * k))
        return np.array(to_arr(fr)), (x0, y0, s)

    def blurred(self):
        if self._blur is None:
            small = self.img.resize((self.w // 3, self.h // 3), Image.BILINEAR)
            self._blur = small.filter(ImageFilter.GaussianBlur(9))
        return self._blur


def to_screen(view, fx, fy, ph):
    x0, y0, s = view
    return (fx * ph.w - x0) * s, (fy * ph.h - y0) * s


# ====================================================================== assets
def emblem_mask(px):
    """Yessine Centre mark: the façade's nested frames, balconies and glass curtain wall."""
    S = px * 4
    img = Image.new("L", (S, S))
    d = ImageDraw.Draw(img)
    u = lambda *v: [c * S / 100 for c in v]
    d.rectangle(u(6, 6, 94, 94), outline=255, width=int(S * 0.045))
    d.rectangle(u(18, 20, 62, 94), outline=255, width=int(S * 0.035))
    for y in (38, 52, 66, 80):
        d.line(u(24, y, 56, y), fill=255, width=int(S * 0.025))
    d.rectangle(u(68, 16, 84, 88), fill=255)
    for y in range(24, 88, 9):
        d.line(u(68, y, 84, y), fill=0, width=int(S * 0.012))
    d.line(u(76, 16, 76, 88), fill=0, width=int(S * 0.012))
    return np.asarray(img.resize((px, px), Image.LANCZOS), np.float32) / 255


def emblem(px):
    L = g.from_mask(emblem_mask(px), gold=True)
    return g.with_shadow(pad_layer(L, 20), blur=8, off=(0, 3), strength=0.6)


def card(size, radius=28):
    """Rounded photo card with a gold border (the photo itself is drawn live for a slow zoom)."""
    m = Image.new("L", (size * 3, size * 3))
    ImageDraw.Draw(m).rounded_rectangle((0, 0, size * 3 - 1, size * 3 - 1), radius * 3, fill=255)
    mask = np.asarray(m.resize((size, size), Image.LANCZOS), np.float32) / 255
    b = Image.new("L", (size * 3, size * 3))
    ImageDraw.Draw(b).rounded_rectangle((0, 0, size * 3 - 1, size * 3 - 1), radius * 3, outline=255, width=9)
    border = g.from_mask(np.asarray(b.resize((size, size), Image.LANCZOS), np.float32) / 255, gold=True)
    return mask, border


def build_assets():
    global TL
    TL = T.load()
    names = set(FOCUS)
    A["ph"] = {n: Photo(n) for n in names}
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    r = np.sqrt(((xx - W / 2) / (W / 2)) ** 2 + ((yy - H / 2) / (H / 2)) ** 2) / math.sqrt(2)
    A["vignette"] = (1 - 0.38 * r ** 2.4)[..., None].astype(np.float32)
    A["topgrad"] = g.gradient_rect(W, 520, g.DARK, 0.85, 0.0, axis=0)
    A["botgrad"] = g.gradient_rect(W, 700, g.DARK, 0.0, 0.9, axis=0)
    A["sprites"] = [g.radial_sprite(r, g.GOLD_LIGHT, 1.8) for r in (3, 5, 8, 13, 20)]
    rng = np.random.default_rng(11)
    n = 50
    A["particles"] = dict(x=rng.uniform(0, W, n), y=rng.uniform(0, H, n), s=rng.integers(0, 5, n),
                          v=rng.uniform(10, 34, n), amp=rng.uniform(5, 25, n), ph=rng.uniform(0, 6.28, n),
                          w=rng.uniform(0.3, 1.0, n), a=rng.uniform(0.15, 0.55, n))
    f = g.font
    A["wm_emblem"] = emblem(46)
    A["wm_text"] = g.text(SCREEN["project"], f(MONT, 17, 700), gold=True, tracking=4, blur=4)
    # hook
    A["emblem_big"] = emblem(150)
    A["h1"] = g.text("مكتبك ليس مجرد مكان للعمل", f(EM, 54, 600))
    A["h2"] = g.text("بل هو عنوان", f(EM, 120, 700), gold=True, blur=10, off=(0, 5))
    A["h3"] = g.text("يعكس صورة نشاطك ونجاحك", f(EM, 52, 600))
    # brand
    A["b_name"] = g.text(SCREEN["project"], f(MONT, 70, 800), gold=True, tracking=7, blur=8, shadow=0.8)
    A["b_city"] = g.text(SCREEN["city_ar"], f(EM, 64, 700), blur=7)
    A["b_city_l"] = g.text(SCREEN["city_latin"], f(MONT, 24, 600), color=g.CREAM, tracking=10, blur=5)
    A["pin"] = g.with_shadow(pad_layer(g.from_mask(g.icon_mask("pin", 96), gold=True), 24), blur=8, off=(0, 6))
    A["ring"] = ring_layer(220, 66)
    A["pin_small"] = g.icon_badge("pin", 70)
    # offer
    A["o_badge"] = badge_box("À VENDRE")
    A["o_title"] = g.text(SCREEN["offer_ar"], f(EM, 104, 700), gold=True, blur=9)
    A["o_loc"] = g.text("في موقع استراتيجي", f(EM, 52, 600), blur=6)
    A["o_chips"] = [(g.icon_badge(ic, 100), g.text(lb, f(CAIRO, 36, 700), blur=5))
                    for lb, ic in [("الراحة", "sofa"), ("قيمة الاستثمار", "chart")]]
    # spaces
    A["kw"] = [g.text(t, f(EM, 86, 700), gold=True, blur=9, shadow=0.8)
               for t in ["فضاء مهني", "يليق بطموحاتك", "انطلاقة مميّزة"]]
    A["here1"] = g.text("مكتبك القادم", f(EM, 70, 600), blur=7, shadow=0.8)
    A["here2"] = g.text("هنا", f(EM, 150, 700), gold=True, blur=11, off=(0, 6), shadow=0.8)
    # contact
    A["c_portrait"] = portrait(270)
    A["c_name"] = g.text("نحن في خدمتكم", f(EM, 38, 600))
    A["c_head"] = g.text("تواصلوا معنا الآن", f(EM, 74, 700), gold=True, blur=8)
    A["c_sub"] = g.text("لمزيد من المعلومات وتحديد موعد للزيارة", f(EM, 38, 500), color=g.CREAM, blur=5)
    A["c_row"] = g.rounded_box(860, 104, 20, alpha=0.6)
    A["c_icons"] = {"phone": g.icon_badge("phone", 74),
                    "whatsapp": g.icon_badge("whatsapp", 74, ring=None, fill=g.WA_GREEN, fill_alpha=1.0,
                                             icon_color=g.WHITE, icon_scale=0.62)}
    A["c_rows"] = []
    for label, num, ic in SCREEN["phones"]:
        groups = num.split(" ")
        A["c_rows"].append(dict(label=g.text(label, f(CAIRO, 24, 600), color=g.GOLD_LIGHT, blur=4),
                                nums=[g.text(" ".join(groups[:k]), f(MONT, 50, 600), blur=5)
                                      for k in range(1, len(groups) + 1)], icon=ic))
    # discover
    A["d_head"] = g.text("المكاتب المتاحة للبيع", f(EM, 66, 700), gold=True, blur=8)
    A["d_card"] = card(420)
    A["d_loc"] = loc_chip(SCREEN["city_ar"])
    A["d_web_label"] = g.text("موقعنا الإلكتروني", f(CAIRO, 30, 600), color=g.CREAM, blur=4)
    A["d_web_name"] = g.text(SCREEN["agency"], f(MONT, 46, 800), gold=True, tracking=4, blur=6)
    A["d_web_box"] = g.rounded_box(900, 170, 26, alpha=0.75, border="gold", bw=2)
    A["d_globe"] = globe_badge(92)
    # outro / end card
    A["e1"] = g.text("اختر لمشروعك عنواناً", f(EM, 72, 700), gold=True, blur=8)
    A["e2"] = g.text("يليق بطموحك", f(EM, 58, 600), blur=7)
    A["e_emblem"] = emblem(180)
    A["e_name"] = g.text(SCREEN["project"], f(MONT, 66, 800), gold=True, tracking=7, blur=8)
    A["e_offer"] = g.text(f"{SCREEN['offer_ar']} · {SCREEN['city_ar']}", f(EM, 48, 600), blur=6)
    A["e_phones"] = [(A["c_icons"][ic], g.text(num, f(MONT, 40, 600), blur=5))
                     for _, num, ic in SCREEN["phones"]]
    A["e_agency"] = g.text(SCREEN["agency"], f(MONT, 24, 700), gold=True, tracking=7, blur=4)
    # subtitles (wrapped to two lines when needed)
    A["subs"] = [subtitle(c["sub"]) for c in TL["cues"]]


def ring_layer(w, h):
    img = Image.new("L", (w * 4, h * 4))
    ImageDraw.Draw(img).ellipse((4, 4, w * 4 - 5, h * 4 - 5), outline=255, width=10)
    return g.from_mask(np.asarray(img.resize((w, h), Image.LANCZOS), np.float32) / 255, gold=True)


def badge_box(label):
    t = g.text(label, g.font(PLAY, 40, 700), gold=True, tracking=8, blur=5)
    box = g.rounded_box(t.cw + 70, t.ch + 40, 4, alpha=0.5, border="gold", bw=2)
    return t, box


def loc_chip(label):
    t = g.text(label, g.font(EM, 46, 700), color=g.DARK, shadow=0)
    ic = g.icon_mask("pin", 44)
    w, h = t.cw + 44 + 70, 84
    img = Image.new("L", (w * 3, h * 3))
    ImageDraw.Draw(img).rounded_rectangle((0, 0, w * 3 - 1, h * 3 - 1), 42 * 3, fill=255)
    base = g.from_mask(np.asarray(img.resize((w, h), Image.LANCZOS), np.float32) / 255, gold=True)
    arr = base.a.copy()
    tx, ty = w - 28 - t.cw - t.pad, (h - t.ch) // 2 - t.pad
    sub = arr[max(0, ty):ty + t.h, tx:tx + t.w]
    ta = t.a[max(0, -ty):max(0, -ty) + sub.shape[0], :sub.shape[1]]
    sub[:] = sub * (1 - ta[..., 3:4]) + ta
    iy = (h - 44) // 2
    dark = np.array(g.DARK, np.float32) / 255
    arr[iy:iy + 44, 22:66, :3] = arr[iy:iy + 44, 22:66, :3] * (1 - ic[..., None]) + dark * ic[..., None]
    return g.with_shadow(pad_layer(g.Layer(arr), 24), blur=10, off=(0, 5), strength=0.7)


def globe_badge(px):
    S = px * 4
    img = Image.new("L", (S, S))
    d = ImageDraw.Draw(img)
    u = lambda *v: [c * S / 100 for c in v]
    w = int(S * 0.045)
    d.ellipse(u(22, 22, 78, 78), outline=255, width=w)
    d.ellipse(u(38, 22, 62, 78), outline=255, width=w)
    d.line(u(22, 50, 78, 50), fill=255, width=w)
    d.line(u(27, 36, 73, 36), fill=255, width=w)
    d.line(u(27, 64, 73, 64), fill=255, width=w)
    gm = np.asarray(img.resize((px, px), Image.LANCZOS), np.float32) / 255
    disc = Image.new("L", (S, S))
    ImageDraw.Draw(disc).ellipse((0, 0, S - 1, S - 1), fill=255)
    dm = np.asarray(disc.resize((px, px), Image.LANCZOS), np.float32) / 255
    ringi = Image.new("L", (S, S))
    ImageDraw.Draw(ringi).ellipse((4, 4, S - 5, S - 5), outline=255, width=int(S * 0.035))
    rm = np.asarray(ringi.resize((px, px), Image.LANCZOS), np.float32) / 255
    L = g.stack(g.from_mask(dm * 0.85, g.DARK), g.from_mask(rm, gold=True), g.from_mask(gm, gold=True))
    return g.with_shadow(pad_layer(L, 16), blur=6, off=(0, 3), strength=0.5)


def subtitle(text):
    fnt = g.font(CAIRO, 36, 600) if g.is_arabic(text) else g.font(MONT, 34, 600)
    lines = [text]
    if g.text_mask(text, fnt, pad=0).shape[1] > W * 0.84:
        words = text.split()
        best = None
        for k in range(1, len(words)):
            a, b = " ".join(words[:k]), " ".join(words[k:])
            wa, wb = g.text_mask(a, fnt, pad=0).shape[1], g.text_mask(b, fnt, pad=0).shape[1]
            if best is None or max(wa, wb) < best[0]:
                best = (max(wa, wb), a, b)
        lines = [best[1], best[2]]
    layers = [g.text(l, fnt, blur=4, shadow=0.7) for l in lines]
    bw = max(L.cw for L in layers) + 56
    bh = 58 * len(layers) + 12
    return layers, g.rounded_box(bw, bh, 16, alpha=0.6)


# ====================================================================== helpers
def particles(fr, t, strength=1.0):
    P = A["particles"]
    for k in range(len(P["x"])):
        y = (P["y"][k] - P["v"][k] * t) % (H + 60) - 30
        x = P["x"][k] + P["amp"][k] * math.sin(t * P["w"][k] + P["ph"][k])
        tw = 0.6 + 0.4 * math.sin(t * 2.1 * P["w"][k] + P["ph"][k] * 3)
        place(fr, A["sprites"][P["s"][k]], x, y, "mm", a=P["a"][k] * tw * strength, add=True)


def cue(scene, k=0):
    return [c for c in TL["cues"] if c["scene"] == scene][k]


def kenburns(name, t, t0, t1, z0, z1, dx=0.0, dy=0.0, focus=None, **kw):
    fx, fy = focus or FOCUS[name]
    u = ease_io(prog(t, t0, t1))
    return A["ph"][name].view(fx + dx * u, fy + dy * u, lerp(z0, z1, u), **kw)


def fit_row(fr, k, R, x_right, yc, t, appear, a=1.0):
    p = prog(t, appear, appear + 0.6)
    if p <= 0:
        return
    xo = (1 - ease_out(p)) * 70
    place(fr, A["c_row"], x_right + xo, yc, "rm", a=ease_out(p) * a)
    place(fr, A["c_icons"][R["icon"]], x_right - 22 + xo, yc, "rm", a=min(1, p * 2) * a)
    tx = x_right - 118 + xo
    place(fr, R["label"], tx, yc - 24, "rm", a=ease_out(p) * a)
    n = 1 + sum(1 for k2 in range(1, len(R["nums"])) if t >= appear + 0.3 + 0.2 * k2)
    full = R["nums"][-1]
    place(fr, R["nums"][min(n, len(R["nums"])) - 1], tx - full.cw, yc + 20, "lm", a=ease_out(p) * a)


# ====================================================================== scenes
def sc_hook(t, S):
    c0, c1 = cue("hook", 0), cue("hook", 1)
    fr, _ = kenburns("facade_grand_angle", t, 0.2, S["end"] + 0.6, 1.28, 1.06, dy=-0.04)
    fr *= lerp(0.36, 0.46, prog(t, 1.0, S["end"]))
    particles(fr, t, 0.9)
    k = min(1.0, c0["start"] / 1.3)
    op = ease_io(prog(t, 0.5 * k, 1.4 * k))
    half = op * H / 2
    top, bot = int(H / 2 - half), int(math.ceil(H / 2 + half))
    fr[:max(0, top)] = 0
    fr[min(H, bot):] = 0
    lw = ease_out(prog(t, 0.05, 0.6 * k)) * W * 0.9
    la = 1 - prog(t, 1.25 * k, 1.6 * k)
    gold_line(fr, W / 2, max(top, 1), lw, a=la)
    gold_line(fr, W / 2, min(bot, H - 2), lw, a=la)
    pop_in(fr, A["emblem_big"], W / 2, 290, "mm", 0.9 * k, t, 0.7, s0=0.7, shimmer=shimmer_pos(t, 1.6 * k))
    text_in(fr, A["h1"], W / 2, 520, "mm", c0["start"], t)
    p2 = prog(t, c1["start"] - 0.1, c1["start"] + 0.6)
    if p2 > 0:
        place(fr, A["h2"], W / 2, 660, "mm", a=min(1, p2 * 2), scale=lerp(1.2, 1, ease_out(p2)),
              shimmer=shimmer_pos(t, c1["start"] + 0.8, 1.2))
    t3 = T.at(c1, "يعكس", 0.35)
    text_in(fr, A["h3"], W / 2, 800, "mm", t3 - 0.05, t)
    gold_line(fr, W / 2, 870, 380 * ease_out(prog(t, t3 + 0.2, t3 + 1.0)))
    return fr


def sc_brand(t, S):
    c = cue("brand")
    ph = A["ph"][SIGN[0]]
    fr, view = kenburns(SIGN[0], t, S["start"] - 0.4, S["end"] + 0.4, 1.0, 1.14, focus=(0.6, 0.5))
    place(fr, A["botgrad"], 0, H - 700)
    tip = to_screen(view, SIGN[1], SIGN[2] - 0.035, ph)
    pd = prog(t, c["start"] - 0.1, c["start"] + 0.7)
    if pd > 0:
        for k in range(2):
            if t > c["start"] + 0.55 + k * 0.6:
                phs = ((t - c["start"] - 0.55 - k * 0.6) % 1.2) / 1.2
                place(fr, A["ring"], tip[0], tip[1], "mm", a=(1 - phs) * 0.9, scale=lerp(0.25, 1.4, ease_out(phs)))
        place(fr, A["pin"], tip[0], tip[1] - (1 - g.bounce(pd)) * 420, "mb", a=min(1, pd * 4))
    pn = prog(t, c["start"] - 0.05, c["start"] + 0.55)
    if pn > 0:
        place(fr, A["b_name"], W / 2, 1050, "mm", a=min(1, pn * 2), scale=lerp(1.15, 1, ease_out(pn)),
              shimmer=shimmer_pos(t, c["start"] + 0.5, 1.0))
    gold_line(fr, W / 2, 1112, 560 * ease_out(prog(t, c["start"] + 0.3, c["start"] + 1.0)))
    tc = T.at(c, "رادس", 0.75)
    pop_in(fr, A["pin_small"], W / 2 + A["b_city"].cw / 2 + 50, 1180, "mm", tc - 0.1, t, 0.45)
    text_in(fr, A["b_city"], W / 2 - 10, 1180, "mm", tc - 0.1, t, 0.5)
    place(fr, A["b_city_l"], W / 2, 1250, "mm", a=ease_out(prog(t, tc + 0.1, tc + 0.6)))
    return fr


def sc_offer(t, S):
    c0, c1 = cue("offer", 0), cue("offer", 1)
    fr, _ = kenburns("facade_face2", t, S["start"] - 0.4, S["end"] + 0.4, 1.38, 1.16, focus=(0.52, 0.72), dy=-0.34)
    place(fr, A["topgrad"], 0, 0)
    place(fr, A["botgrad"], 0, H - 700)
    tb, bx = A["o_badge"]
    pb = prog(t, c0["start"] - 0.2, c0["start"] + 0.35)
    if pb > 0:
        place(fr, bx, W / 2, 140, "mm", a=ease_out(pb), scale=lerp(1.25, 1, ease_out(pb)))
        place(fr, tb, W / 2, 140, "mm", a=ease_out(pb), scale=lerp(1.25, 1, ease_out(pb)),
              shimmer=shimmer_pos(t, c0["start"] + 0.4, 1.0))
    text_in(fr, A["o_title"], W / 2, 270, "mm", c0["start"] + 0.05, t, shimmer=shimmer_pos(t, c0["start"] + 1.3, 1.2))
    tl = T.at(c0, "موقع", 0.5)
    pop_in(fr, A["pin_small"], W / 2 + A["o_loc"].cw / 2 + 48, 380, "mm", tl - 0.15, t, 0.45)
    text_in(fr, A["o_loc"], W / 2 - 12, 380, "mm", tl - 0.1, t)
    for k, word in enumerate(["الراحة", "وقيمة"]):
        t0 = T.at(c1, word, 0.3 + 0.4 * k) - 0.1
        cx = W / 2 + (180 if k == 0 else -180)          # RTL: first item on the right
        ic, lb = A["o_chips"][k]
        pop_in(fr, ic, cx, 1030, "mm", t0, t, 0.5)
        text_in(fr, lb, cx, 1110, "mt", t0 + 0.12, t, 0.5, rise=8)
    return fr


def spaces_plan(S, tl=None):
    tl = tl or TL
    c0, c1, c2 = cue_of(tl, "spaces", 0), cue_of(tl, "spaces", 1), cue_of(tl, "spaces", 2)
    cuts = [S["start"] - 1.0, T.at(c0, "يليق") - 0.2, c1["start"] - 0.2, c2["start"] - 0.2, S["end"] + 1.0]
    shots = [("hall_ascenseurs", 1.06, 1.2, 0.04, 0.0), ("couloir_marbre", 1.2, 1.06, 0.0, 0.0),
             ("espace_lumineux", 1.05, 1.18, -0.05, 0.0), ("grande_piece", 1.18, 1.04, 0.03, 0.0)]
    words = [T.at(c0, "فضاء"), T.at(c0, "يليق"), T.at(c1, "انطلاقة")]
    return cuts, shots, words, c2


def sc_spaces(t, S):
    cuts, shots, words, c2 = spaces_plan(S)
    k = max(i for i in range(4) if cuts[i] <= t) if t >= cuts[0] else 0
    def shot(i):
        name, z0, z1, dx, dy = shots[i]
        fr, _ = kenburns(name, t, cuts[i], cuts[i + 1] + 0.3, z0, z1, dx=dx, dy=dy)
        return fr
    fr = shot(k)
    if k > 0 and t - cuts[k] < 0.35:   # quick slide between interiors (RTL)
        x = ease_io((t - cuts[k]) / 0.35)
        prev = shot(k - 1)
        off = int(x * W)
        out = np.empty_like(fr)
        out[:, off:] = prev[:, :W - off]
        out[:, :off] = fr[:, W - off:]
        fr = out
    place(fr, A["botgrad"], 0, H - 700)
    for i, (L, tw) in enumerate(zip(A["kw"], words)):
        nxt = words[i + 1] - 0.25 if i + 1 < len(words) else c2["start"] - 0.25
        end = min(nxt, cuts[i + 1] + 0.05)          # each keyword leaves with its own photo
        a = 1 - prog(t, end - 0.2, end)
        if a > 0:
            text_in(fr, L, W / 2, 1110, "mm", tw - 0.1, t, 0.5, a=a, shimmer=shimmer_pos(t, tw + 0.4, 0.9))
    th = T.at(c2, "مكتبك", 0.3)
    text_in(fr, A["here1"], W / 2, 1010, "mm", th - 0.15, t, 0.5)
    p = prog(t, th + 0.35, th + 0.85)
    if p > 0:
        place(fr, A["here2"], W / 2, 1130, "mm", a=min(1, p * 2), scale=lerp(1.4, 1, ease_back(p)),
              shimmer=shimmer_pos(t, th + 0.9, 1.0))
    return fr


def sc_contact(t, S):
    c0, c1 = cue("contact", 0), cue("contact", 1)
    fr, _ = kenburns("hall_boites", t, S["start"] - 0.5, S["end"] + 0.5, 1.1, 1.22, blur=True)
    fr *= 0.38
    fr += np.array([0.05, 0.03, 0.0], np.float32)
    particles(fr, t, 0.8)
    pcx, pcy = W / 2, 290
    pp = prog(t, S["start"] + 0.1, S["start"] + 0.8)
    if pp > 0:
        rings(fr, pcx, pcy, 152, t, ease_out(pp))
        place(fr, A["c_portrait"], pcx, pcy, "mm", a=min(1, pp * 2), scale=lerp(0.85, 1, ease_back(pp)))
        text_in(fr, A["c_name"], pcx, 462, "mt", S["start"] + 0.5, t)
    text_in(fr, A["c_head"], W / 2, 600, "mm", c0["start"] - 0.05, t)
    text_in(fr, A["c_sub"], W / 2, 685, "mm", c0["start"] + 1.0, t)
    for k, R in enumerate(A["c_rows"]):
        fit_row(fr, k, R, W / 2 + 430, 810 + k * 125, t, c1["start"] - 0.1 + 0.18 * k)
    return fr


def sc_discover(t, S):
    c0, c1 = cue("discover", 0), cue("discover", 1)
    fr, _ = kenburns("espace_lumineux", t, S["start"] - 0.5, S["end"] + 0.5, 1.1, 1.2, blur=True)
    fr *= 0.36
    particles(fr, t, 0.7)
    text_in(fr, A["d_head"], W / 2, 110, "mm", c0["start"] - 0.05, t)
    mask, border = A["d_card"]
    size = mask.shape[0]
    t_cards = T.at(c0, "المكاتب", 0.2)
    for k, name in enumerate(GALLERY):
        p = prog(t, t_cards + 0.22 * k, t_cards + 0.22 * k + 0.55)
        if p <= 0:
            continue
        cx = W / 2 + (230 if k % 2 == 0 else -230)
        cy = 410 + (k // 2) * 470
        img, _ = A["ph"][name].view(*FOCUS[name], lerp(1.05, 1.2, prog(t, t_cards, S["end"])), out=(size, size))
        Lc = g.Layer(np.concatenate([img * mask[..., None], mask[..., None]], -1))
        Lc = g.stack(Lc, border)
        s = lerp(0.7, 1, ease_back(p))
        place(fr, g.with_shadow(pad_layer(Lc, 24), blur=12, off=(0, 8), strength=0.7), cx, cy + (1 - ease_out(p)) * 60,
              "mm", a=min(1, p * 2), scale=s)
    pop_in(fr, A["d_loc"], W / 2, 645, "mm", T.at(c0, "وموقع", 0.7) - 0.1, t, 0.5, s0=0.5)
    pw = prog(t, c1["start"] - 0.1, c1["start"] + 0.5)
    if pw > 0:
        y = 1185 + (1 - ease_out(pw)) * 60
        place(fr, A["d_web_box"], W / 2, y, "mm", a=ease_out(pw))
        place(fr, A["d_globe"], W / 2 + 360, y, "mm", a=ease_out(pw))
        place(fr, A["d_web_label"], W / 2 + 290, y - 40, "rm", a=ease_out(pw))
        tn = T.at(c1, "Immobilière", 0.55)
        text_in(fr, A["d_web_name"], W / 2 - 50, y + 22, "mm", tn - 0.15, t, 0.6, rtl=False,
                shimmer=shimmer_pos(t, tn + 0.5, 1.1))
    return fr


def endcard_pace(tl=None):
    tl = tl or TL
    return max(0.55, min(1.0, (tl["total"] - tl["vo_end"] - 0.85) / 2.95))


def sc_outro(t, S):
    c = cue("outro")
    endc = TL["vo_end"] + 0.25
    fr, _ = kenburns("facade_face", t, S["start"] - 0.5, TL["total"], 1.2, 1.0, focus=(0.55, 0.45))
    e = ease_io(prog(t, endc, endc + 0.8))
    if e > 0:
        bl, _ = kenburns("facade_face", t, S["start"] - 0.5, TL["total"], 1.2, 1.0, focus=(0.55, 0.45), blur=True)
        fr = fr * (1 - e) + bl * 0.34 * e
    fr += np.array([0.05, 0.03, 0.0], np.float32) * (1 - e)
    out = 1 - prog(t, endc - 0.1, endc + 0.4)
    if out > 0:
        place(fr, A["topgrad"], 0, 0, a=out)
        text_in(fr, A["e1"], W / 2, 130, "mm", c["start"] - 0.05, t, a=out, shimmer=shimmer_pos(t, c["start"] + 0.9))
        text_in(fr, A["e2"], W / 2, 230, "mm", T.at(c, "يليق", 0.6) - 0.1, t, a=out)
    if e > 0:
        q = endcard_pace()
        particles(fr, t, e)
        pop_in(fr, A["e_emblem"], W / 2, 330, "mm", endc + 0.15 * q, t, 0.7 * q, s0=0.7,
               shimmer=shimmer_pos(t, endc + 0.9 * q, 1.1))
        text_in(fr, A["e_name"], W / 2, 500, "mm", endc + 0.35 * q, t, 0.6 * q, rtl=False)
        place(fr, A["e_offer"], W / 2, 585, "mm", a=ease_out(prog(t, endc + 0.6 * q, endc + 1.1 * q)))
        gold_line(fr, W / 2, 645, 560 * ease_out(prog(t, endc + 0.7 * q, endc + 1.4 * q)))
        for k, (ic, num) in enumerate(A["e_phones"]):
            p = prog(t, endc + (0.9 + 0.15 * k) * q, endc + (1.4 + 0.15 * k) * q)
            if p > 0:
                y = 740 + k * 100 + (1 - ease_out(p)) * 20
                wtot = ic.cw + 22 + num.cw
                x = W / 2 + wtot / 2
                place(fr, ic, x, y, "rm", a=ease_out(p))
                place(fr, num, x - ic.cw - 22, y, "rm", a=ease_out(p))
        place(fr, A["e_agency"], W / 2, 1080, "mm", a=ease_out(prog(t, endc + 1.5 * q, endc + 2.1 * q)))
    return fr


SCENE_FN = dict(hook=sc_hook, brand=sc_brand, offer=sc_offer, spaces=sc_spaces, contact=sc_contact,
                discover=sc_discover, outro=sc_outro)
TRANS_KIND = ["goldwipe", "zoom", "push", "iris", "scan", "flash"]


# ====================================================================== transitions
def zoomed(fr, s):
    if abs(s - 1) < 1e-3:
        return fr
    im = Image.fromarray((np.clip(fr, 0, 1) * 255).astype(np.uint8))
    bw, bh = W / s, H / s
    return to_arr(im.resize((W, H), Image.BILINEAR, box=((W - bw) / 2, (H - bh) / 2, (W + bw) / 2, (H + bh) / 2)))


def transition(kind, a, b, x):
    xs = np.arange(W, dtype=np.float32)[None, :, None]
    ys = np.arange(H, dtype=np.float32)[:, None, None]
    if kind == "goldwipe":
        d = ((W - xs) + 0.45 * ys) / (W + 0.45 * H)
        pos = lerp(-0.12, 1.12, ease_io(x))
        m = np.clip((pos - d) / 0.02, 0, 1)
        band = np.exp(-((d - pos + 0.04) / 0.035) ** 2)
        out = a * (1 - m) + b * m
        return out * (1 - band * 0.9) + g.gold_gradient(H, W) * band * 0.9
    if kind == "zoom":
        e = ease_io(x)
        return zoomed(a, 1 + 0.35 * e) * (1 - e) + zoomed(b, 1.25 - 0.25 * e) * e + 0.1 * math.sin(math.pi * x)
    if kind == "push":
        off = int(ease_io(x) * W)
        out = np.empty_like(a)
        out[:, off:] = a[:, :W - off]
        out[:, :off] = b[:, W - off:]
        if 0 < off < W:
            out = out + np.exp(-((xs - off) / 8) ** 2) * 0.8 * np.array([0.95, 0.8, 0.5], np.float32)
        return out
    if kind == "scan":
        pos = lerp(-30, H + 30, ease_io(x))
        m = np.clip((pos - ys) / 24, 0, 1)
        glow = np.exp(-((ys - pos) / 7) ** 2) + 0.35 * np.exp(-((ys - pos) / 40) ** 2)
        return a * (1 - m) + b * m + glow * np.array([0.95, 0.8, 0.45], np.float32)
    if kind == "iris":
        cx, cy = W / 2, 290
        r = ease_in(x) * math.hypot(W, H) * 1.05
        dist = np.sqrt((xs - cx) ** 2 + (ys - cy) ** 2)
        m = np.clip((r - dist) / 20, 0, 1)
        ring = np.exp(-((dist - r) / 6) ** 2) * (r > 1)
        return a * (1 - m) + b * m + ring * np.array([0.95, 0.8, 0.45], np.float32)
    if kind == "flash":
        e = ease_io(x)
        fl = math.sin(math.pi * x) ** 2
        return (a * (1 - e) + b * e) * (1 - 0.35 * fl) + fl * np.array([1.0, 0.88, 0.66], np.float32) * 0.45
    raise KeyError(kind)


# ====================================================================== frame
def subtitles(fr, t):
    for c, (lines, box) in zip(TL["cues"], A["subs"]):
        t0, t1 = c["start"] - 0.06, c["end"] + min(c["pause"], 0.25)
        if t0 - 0.2 < t < t1 + 0.2:
            a = fade(t, t0, t1, 0.14, 0.14)
            yb = H - 52 + 6 * (1 - ease_out(prog(t, t0, t0 + 0.25)))
            place(fr, box, W / 2, yb, "mb", a=a)
            n = len(lines)
            for k, L in enumerate(lines):
                place(fr, L, W / 2, yb - box.ch + 6 + 29 + k * 58, "mm", a=a)


def watermark(fr, t):
    a = fade(t, TL["scenes"][1]["start"] + 0.4, TL["vo_end"] + 0.25, 0.5, 0.4)
    if a > 0:
        place(fr, A["wm_emblem"], 24, 20, "lt", a=a * 0.95)
        place(fr, A["wm_text"], 82, 43, "lm", a=a * 0.95)


def frame(t):
    sc = TL["scenes"]
    k = max(i for i, s in enumerate(sc) if s["start"] <= t) if t >= 0 else 0
    fr = None
    for j, b in enumerate(TL["transitions"]):
        if abs(t - b) < TL["trans"] / 2:
            x = (t - (b - TL["trans"] / 2)) / TL["trans"]
            fr = transition(TRANS_KIND[j % len(TRANS_KIND)], SCENE_FN[sc[j]["name"]](t, sc[j]),
                            SCENE_FN[sc[j + 1]["name"]](t, sc[j + 1]), x)
            break
    if fr is None:
        fr = SCENE_FN[sc[k]["name"]](t, sc[k])
    fr = np.clip(fr, 0, 1) * A["vignette"]
    watermark(fr, t)
    subtitles(fr, t)
    fr *= 1 - prog(t, TL["total"] - 0.6, TL["total"])
    return (np.clip(fr, 0, 1) * 255 + 0.5).astype(np.uint8)


def events():
    """Times of on-screen beats, for the sound design (audio.py)."""
    build = TL or T.load()
    S = {s["name"]: s for s in build["scenes"]}
    ev = []
    cuts, _, _, c2 = spaces_plan(S["spaces"], build)
    ev += [("swish", c) for c in cuts[1:4]]
    ev += [("pop", T.at(cue_of(build, "brand"), "رادس", 0.75) - 0.1)]
    c1 = cue_of(build, "offer", 1)
    ev += [("pop", T.at(c1, w, 0.3 + 0.4 * k) - 0.1) for k, w in enumerate(["الراحة", "وقيمة"])]
    ev += [("stamp", cue_of(build, "offer")["start"] - 0.25)]
    ev += [("chime", T.at(c2, "مكتبك", 0.3) + 0.4)]
    ev += [("pop", cue_of(build, "contact", 1)["start"] - 0.1 + 0.18 * k) for k in range(3)]
    t_cards = T.at(cue_of(build, "discover"), "المكاتب", 0.2)
    ev += [("pop", t_cards + 0.22 * k) for k in range(4)]
    ev += [("chime", T.at(cue_of(build, "discover", 1), "Immobilière", 0.55) + 0.3)]
    return ev


def cue_of(tl, scene, k=0):
    return [c for c in tl["cues"] if c["scene"] == scene][k]


# ====================================================================== output
def render_chunk(args):
    idx, f0, f1 = args
    out = os.path.join(BUILD, f"seg_{idx:02d}.mp4")
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
           "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-preset", "slow", "-crf", "18", "-threads", "2",
           "-profile:v", "high", "-pix_fmt", "yuv420p", "-g", "60", out]
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    for n in range(f0, f1):
        p.stdin.write(frame(n / FPS).tobytes())
    p.stdin.close()
    p.wait()
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--still", type=float, nargs="*")
    ap.add_argument("--workers", type=int, default=os.cpu_count())
    args = ap.parse_args()
    build_assets()
    os.makedirs(os.path.join(BUILD, "preview"), exist_ok=True)
    if args.still:
        for t in args.still:
            Image.fromarray(frame(t)).save(os.path.join(BUILD, "preview", f"still_{t:06.2f}.png"))
        return
    n = int(round(TL["total"] * FPS))
    k = args.workers
    with mp.get_context("fork").Pool(k) as pool:
        segs = pool.map(render_chunk, [(i, i * n // k, (i + 1) * n // k) for i in range(k)])
    lst = os.path.join(BUILD, "segments.txt")
    with open(lst, "w") as f:
        f.writelines(f"file '{s}'\n" for s in segs)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy",
                    os.path.join(BUILD, "video_silent.mp4")], check=True)
    T.srt(TL, os.path.join(BUILD, "subtitles_ar.srt"))
    print("frames", n, "->", os.path.join(BUILD, "video_silent.mp4"))


if __name__ == "__main__":
    main()
