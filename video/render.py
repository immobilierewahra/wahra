"""Render the motion-graphics video (silent) frame by frame.

python3 render.py                 -> build/video_silent.mp4
python3 render.py --still 12.5 40 -> build/preview/still_12.50.png ... (quick checks)
VIDEO_VARIANT=30s python3 render.py   (other cut, see timeline.py)
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

HERE = os.path.dirname(os.path.abspath(__file__))
BUILD = T.BUILD
W, H, FPS = T.W, T.H, T.FPS

# Text shown on screen that is not spoken word-for-word.
CONFIG = {
    "agency": "IMMOBILIÈRE WAHRA",
    "place_latin": "RIADH EL ANDALOUS",
    "phones": [("اتصلوا بنا", "+216 20 026 026", "phone"),
               ("واتساب", "+216 25 684 686", "whatsapp"),
               ("واتساب", "+216 29 404 009", "whatsapp")],
    "features": [("شقق عصرية بتشطيبات راقية", "sofa"), ("إقامة آمنة ومريحة", "shield"), ("موقف سيارات خاص", "car"),
                 ("مصعد عصري", "elevator"), ("جودة عالية وتصميم مميّز", "diamond")],
    "apartment_box": (836, 386, 955, 452),   # balcony highlighted for "choose your apartment"
}

TL = None
A = {}


# ====================================================================== assets
def to_arr(img):
    return np.asarray(img, np.float32) / 255


def build_assets():
    global TL
    TL = T.load()
    CONFIG.update(TL["screen"])
    src = Image.open(os.path.join(HERE, "assets", "building.jpg")).convert("RGB")
    a = to_arr(src)
    a = np.clip(a - 0.05 * np.sin(2 * np.pi * a), 0, 1)              # gentle S-curve
    a = np.clip(a * np.array([1.03, 1.0, 0.96], np.float32), 0, 1)   # warm
    graded = Image.fromarray((a * 255 + 0.5).astype(np.uint8))
    big = graded.resize((W * 2, H * 2), Image.LANCZOS).filter(ImageFilter.UnsharpMask(2, 60, 2))
    A["img"] = big
    A["blur"] = graded.filter(ImageFilter.GaussianBlur(10)).resize((W * 2, H * 2), Image.BILINEAR)
    A["blueprint"] = make_blueprint(big)

    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    r = np.sqrt(((xx - W / 2) / (W / 2)) ** 2 + ((yy - H / 2) / (H / 2)) ** 2) / math.sqrt(2)
    A["vignette"] = (1 - 0.42 * r ** 2.4)[..., None].astype(np.float32)
    A["topgrad"] = g.gradient_rect(W, 320, g.DARK, 0.8, 0.0, axis=0)
    xg = np.linspace(0, 1, 980, dtype=np.float32)
    sm = np.clip((xg - 0.45) / 0.55, 0, 1)
    A["leftgrad"] = g.from_mask(np.repeat((0.86 * (1 - sm * sm * (3 - 2 * sm)))[None, :], H, 0), g.DARK)
    A["botgrad"] = g.gradient_rect(W, 360, g.DARK, 0.0, 0.85, axis=0)

    A["sprites"] = [g.radial_sprite(r, g.GOLD_LIGHT, 1.8) for r in (3, 5, 8, 13, 20)]
    rng = np.random.default_rng(7)
    n = 46
    A["particles"] = dict(x=rng.uniform(0, W, n), y=rng.uniform(0, H, n), s=rng.integers(0, 5, n),
                          v=rng.uniform(8, 30, n), amp=rng.uniform(5, 25, n), ph=rng.uniform(0, 6.28, n),
                          w=rng.uniform(0.3, 1.0, n), a=rng.uniform(0.15, 0.55, n))

    f = g.font
    EM = "ElMessiri.ttf"
    # --- persistent
    A["wm_emblem"] = g.emblem(44)
    A["wm_text"] = g.text("رياض الأندلس", f(EM, 26, 700), gold=True, blur=5)
    # --- intro
    A["emblem_big"] = g.emblem(118)
    A["i_l1"] = g.text("فرصتك لامتلاك", f(EM, 48, 600))
    A["i_l2"] = g.text("شقة راقية", f(EM, 112, 700), gold=True, blur=10, off=(0, 5))
    A["i_l3"] = g.text("في رياض الأندلس", f(EM, 48, 600))
    # --- location
    A["pin"] = g.with_shadow(pad_layer(g.from_mask(g.icon_mask("pin", 86), gold=True), 24), blur=8, off=(0, 6))
    A["ring"] = ellipse_ring(200, 60)
    A["l_t1"] = g.text("موقع مميّز", f(EM, 62, 700), gold=True, blur=8)
    A["l_t2"] = g.text("رياض الأندلس", f(EM, 46, 600))
    A["l_t3"] = g.text(CONFIG["place_latin"], f("Montserrat.ttf", 18, 600), gold=True, tracking=7, blur=5, shadow=0.9)
    # --- standing
    A["s_badge"] = badge("HAUT STANDING")
    A["s_t1"] = g.text("إقامة من الطراز الرفيع", f(EM, 58, 700), gold=True, blur=8)
    A["s_t2"] = g.text("بتصميم عصري وأنيق", f(EM, 42, 500))
    A["s_chips"] = [(g.icon_badge(ic, 74), g.text(lb, f("Cairo.ttf", 27, 700), blur=5))
                    for lb, ic in [("الراحة", "sofa"), ("الأمان", "shield"), ("جودة الحياة", "leaf")]]
    # --- features
    A["f_panel"] = g.rounded_box(530, 566, 20, alpha=0.88, border="gold", bw=2)
    A["f_head"] = g.text("مميزات الإقامة", f("Cairo.ttf", 46, 800), gold=True, blur=6)
    A["f_rows"] = [(g.icon_badge(ic, 60), g.text(lb, f("Cairo.ttf", 28, 700), blur=4),
                    g.text(lb, f("Cairo.ttf", 28, 700), gold=True, blur=4)) for lb, ic in CONFIG["features"]]
    A["f_hl"] = g.rounded_box(494, 72, 14, fill=g.GOLD, alpha=0.16)
    # --- plan
    A["p_t1"] = g.text("البيع على المخطط", f(EM, 74, 700), blur=8)
    A["p_t2"] = g.text("VENTE SUR PLAN", f("Montserrat.ttf", 31, 700), gold=True, tracking=10, blur=5)
    A["p_frame"] = frame_box(620, 170)
    A["p_tag"] = tag("شقتكم", "key")
    A["p_t3"] = g.text("واستثمروا في مشروع سكني مميّز", f(EM, 46, 600))
    A["p_t4"] = g.text("وفي موقع استثنائي", f(EM, 62, 700), gold=True, blur=8)
    A["p_chart"] = g.icon_badge("chart", 66)
    # --- contact
    A["c_portrait"] = portrait(310)
    A["c_name"] = g.text("نحن في خدمتكم", f(EM, 34, 600))
    A["c_head"] = g.text("للمزيد من المعلومات والحجز", f(EM, 48, 700), gold=True, blur=7)
    A["c_fr"] = g.text("Pour plus d’informations et réservation", f("PlayfairDisplay.ttf", 24, 500), color=g.CREAM, blur=4)
    A["c_row"] = g.rounded_box(650, 104, 18, alpha=0.55)
    A["c_row_on"] = g.rounded_box(650, 104, 18, alpha=0.7, border="gold", bw=2)
    A["c_icons"] = {"phone": g.icon_badge("phone", 74),
                    "whatsapp": g.icon_badge("whatsapp", 74, ring=None, fill=g.WA_GREEN, fill_alpha=1.0,
                                             icon_color=g.WHITE, icon_scale=0.62)}
    A["c_rows"] = []
    for label, num, ic in CONFIG["phones"]:
        groups = num.split(" ")
        prefixes = [" ".join(groups[:k]) for k in range(1, len(groups) + 1)]
        A["c_rows"].append(dict(label=g.text(label, f("Cairo.ttf", 23, 600), color=g.GOLD_LIGHT, blur=4),
                                nums=[g.text(p, f("Montserrat.ttf", 46, 600), blur=5) for p in prefixes], icon=ic))
    # --- outro
    A["o_t1"] = g.text("استثمر في مستقبلك", f(EM, 66, 700), gold=True, blur=8)
    A["o_t2"] = g.text("واختر عنواناً يليق بك في رياض الأندلس", f(EM, 42, 600))
    A["o_emblem"] = g.emblem(150)
    A["o_name"] = g.text("رياض الأندلس", f(EM, 68, 700), gold=True, blur=8)
    A["o_sub"] = g.text("HAUT STANDING  ·  VENTE SUR PLAN", f("Montserrat.ttf", 19, 500), color=g.CREAM, tracking=5, blur=4)
    A["o_agency"] = g.text(CONFIG["agency"], f("Montserrat.ttf", 15, 600), gold=True, tracking=6, blur=3)
    A["o_contacts"] = [(g.icon_badge("phone", 50) if ic == "phone" else
                        g.icon_badge("whatsapp", 50, ring=None, fill=g.WA_GREEN, fill_alpha=1.0, icon_color=g.WHITE,
                                     icon_scale=0.62), g.text(num, f("Montserrat.ttf", 27, 600), blur=4))
                       for _, num, ic in CONFIG["phones"]]
    # --- subtitles
    A["subs"] = []
    for c in TL["cues"]:
        fnt = f("Cairo.ttf", 31, 600) if g.is_arabic(c["sub"]) else f("Montserrat.ttf", 29, 600)
        txt = g.text(c["sub"], fnt, blur=4, shadow=0.7)
        box = g.rounded_box(txt.cw + 48, 54, 14, alpha=0.58)
        A["subs"].append((txt, box))


def pad_layer(L, pad):
    arr = np.zeros((L.h + 2 * pad, L.w + 2 * pad, 4), np.float32)
    arr[pad:pad + L.h, pad:pad + L.w] = L.a
    return g.Layer(arr, pad + L.pad)


def ellipse_ring(w, h):
    img = Image.new("L", (w * 4, h * 4))
    ImageDraw.Draw(img).ellipse((4, 4, w * 4 - 5, h * 4 - 5), outline=255, width=10)
    return g.from_mask(np.asarray(img.resize((w, h), Image.LANCZOS), np.float32) / 255, gold=True)


def badge(label):
    t = g.text(label, g.font("PlayfairDisplay.ttf", 32, 600), gold=True, tracking=7, blur=5)
    bw, bh = t.cw + 64, t.ch + 34
    box = g.rounded_box(bw, bh, 4, alpha=0.45, border="gold", bw=2)
    arr = box.a.copy()
    ox, oy = (bw - t.cw) // 2 - t.pad, (bh - t.ch) // 2 - t.pad
    canvas = np.zeros((bh + 2 * 40, bw + 2 * 40, 4), np.float32)
    canvas[40:40 + bh, 40:40 + bw] = arr
    sub = canvas[40 + oy:40 + oy + t.h, 40 + ox:40 + ox + t.w]
    sub[:] = sub * (1 - t.a[..., 3:4]) + t.a
    return g.Layer(canvas, 40)


def frame_box(w, h):
    """Blueprint-style title frame: thin white rectangle with corner ticks."""
    img = Image.new("L", (w * 3, h * 3))
    d = ImageDraw.Draw(img)
    d.rectangle((6, 6, w * 3 - 7, h * 3 - 7), outline=200, width=4)
    for cx, cy in [(6, 6), (w * 3 - 7, 6), (6, h * 3 - 7), (w * 3 - 7, h * 3 - 7)]:
        d.line((cx - 36, cy, cx + 36, cy), fill=255, width=7)
        d.line((cx, cy - 36, cx, cy + 36), fill=255, width=7)
    m = np.asarray(img.resize((w, h), Image.LANCZOS), np.float32) / 255
    fill = g.from_mask(np.full((h, w), 0.28, np.float32), (8, 36, 70))
    return pad_layer(g.stack(fill, g.from_mask(m, (220, 238, 255))), 12)


def tag(label, icon):
    t = g.text(label, g.font("Cairo.ttf", 30, 800), color=g.DARK, shadow=0)
    ic = g.icon_mask(icon, 34)
    w, h = t.cw + 34 + 60, 56
    img = Image.new("L", (w * 3, (h + 14) * 3))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((0, 0, w * 3 - 1, h * 3 - 1), 30, fill=255)
    d.polygon(((w * 1.5 - 14) * 3 // 1, h * 3 - 3, (w * 1.5 + 14) * 3 // 1, h * 3 - 3, w * 1.5 * 3 // 1, (h + 13) * 3), fill=255)
    m = np.asarray(img.resize((w, h + 14), Image.LANCZOS), np.float32) / 255
    base = g.from_mask(m, gold=True)
    arr = base.a.copy()
    tx, ty = w - 22 - t.cw - t.pad, (h - t.ch) // 2 - t.pad
    sub = arr[max(0, ty):ty + t.h, tx:tx + t.w]
    ta = t.a[max(0, -ty):max(0, -ty) + sub.shape[0], :sub.shape[1]]
    sub[:] = sub * (1 - ta[..., 3:4]) + ta
    iy = (h - 34) // 2
    arr[iy:iy + 34, 18:52, :3] = arr[iy:iy + 34, 18:52, :3] * (1 - ic[..., None]) + np.array(g.DARK, np.float32) / 255 * ic[..., None]
    return g.with_shadow(pad_layer(g.Layer(arr), 22), blur=8, off=(0, 4), strength=0.6)


def portrait(d):
    im = Image.open(os.path.join(HERE, "assets", "advisor.png")).convert("RGB")
    cx, cy, r = 625, 625, 598
    im = im.crop((cx - r, cy - r, cx + r, cy + r)).resize((d, d), Image.LANCZOS)
    mimg = Image.new("L", (d * 4, d * 4))
    ImageDraw.Draw(mimg).ellipse((0, 0, d * 4 - 1, d * 4 - 1), fill=255)
    m = np.asarray(mimg.resize((d, d), Image.LANCZOS), np.float32) / 255
    rgb = to_arr(im)
    arr = np.concatenate([rgb * m[..., None], m[..., None]], -1)
    return g.with_shadow(pad_layer(g.Layer(arr), 30), blur=14, off=(0, 8), strength=0.7)


# ====================================================================== helpers
def cam(img, fx, fy, z, sx=W / 2, sy=H / 2):
    """Crop of the 2x source so that source point (fx, fy) lands at screen (sx, sy) with zoom z."""
    bw, bh = W / z, H / z
    x0 = min(max(fx - sx / z, 0), W - bw)
    y0 = min(max(fy - sy / z, 0), H - bh)
    fr = to_arr(img.resize((W, H), Image.BICUBIC, box=(x0 * 2, y0 * 2, (x0 + bw) * 2, (y0 + bh) * 2)))
    return np.array(fr), (x0, y0, z)


def to_screen(view, px, py):
    x0, y0, z = view
    return (px - x0) * z, (py - y0) * z


def particles(fr, t, strength=1.0):
    P = A["particles"]
    for k in range(len(P["x"])):
        y = (P["y"][k] - P["v"][k] * t) % (H + 60) - 30
        x = P["x"][k] + P["amp"][k] * math.sin(t * P["w"][k] + P["ph"][k])
        tw = 0.6 + 0.4 * math.sin(t * 2.1 * P["w"][k] + P["ph"][k] * 3)
        spr = A["sprites"][P["s"][k]]
        place(fr, spr, x, y, "mm", a=P["a"][k] * tw * strength, add=True)


def gold_line(fr, cx, y, width, thick=2, a=1.0):
    if width < 2:
        return
    place(fr, g.hline(int(width), thick), cx, y, "mm", a=a)
    place(fr, g.hline(int(width), thick + 6), cx, y, "mm", a=0.18 * a, add=True)


def seg(fr, xa, ya, xb, yb, width=3, color=(0.95, 0.82, 0.5), a=1.0, glow=True):
    """Axis-aligned line with a soft glow."""
    col = np.array(color, np.float32)
    xa, xb = sorted((xa, xb))
    ya, yb = sorted((ya, yb))
    for wdt, aa in (((width + 8, 0.2), (width, 1.0)) if glow else ((width, 1.0),)):
        x0, x1 = int(max(0, xa - wdt / 2)), int(min(W, xb + wdt / 2))
        y0, y1 = int(max(0, ya - wdt / 2)), int(min(H, yb + wdt / 2))
        if x1 > x0 and y1 > y0:
            d = fr[y0:y1, x0:x1]
            d += (col - d) * (aa * a)


def rect_stroke(fr, x0, y0, x1, y1, p, width=3, color=(0.95, 0.82, 0.5), a=1.0):
    """Axis-aligned rectangle drawn progressively (p in 0..1) clockwise from the top-left corner."""
    segs = [((x0, y0), (x1, y0)), ((x1, y0), (x1, y1)), ((x1, y1), (x0, y1)), ((x0, y1), (x0, y0))]
    lens = [abs(b[0] - a_[0]) + abs(b[1] - a_[1]) for a_, b in segs]
    left = p * sum(lens)
    for (s, e), L in zip(segs, lens):
        if left <= 0 or L <= 0:
            continue
        q = min(1, left / L)
        left -= L
        seg(fr, s[0], s[1], s[0] + (e[0] - s[0]) * q, s[1] + (e[1] - s[1]) * q, width, color, a)


def text_in(fr, L, x, y, anchor, t0, t, dur=0.7, rise=14, a=1.0, rtl=True, **kw):
    """Standard text entrance: wipe-reveal (RTL) + slight rise + fade."""
    p = prog(t, t0, t0 + dur)
    if p <= 0:
        return
    place(fr, L, x, y + rise * (1 - ease_out(p)), anchor, a=a * ease_out(min(1, p * 1.6)),
          reveal=ease_out(p), rtl=rtl, **kw)


def pop_in(fr, L, x, y, anchor, t0, t, dur=0.5, a=1.0, s0=0.6, **kw):
    p = prog(t, t0, t0 + dur)
    if p <= 0:
        return
    place(fr, L, x, y, anchor, a=a * min(1, p * 2.5), scale=lerp(s0, 1, ease_back(p)), **kw)


def shimmer_pos(t, t0, dur=1.1):
    p = prog(t, t0, t0 + dur)
    return p if 0 < p < 1 else None


# ====================================================================== scenes
def sc_intro(t, S):
    R = TL["roles"]["intro"]
    c0 = R["cue"]
    z = lerp(1.24, 1.05, ease_out(prog(t, 0.5, S["end"] + 0.6)))
    fr, _ = cam(A["img"], 728, 360, z)
    fr *= lerp(0.38, 0.5, prog(t, 1.0, S["end"]))
    particles(fr, t, 0.9)

    k = min(1.0, c0["start"] / 1.3)   # shorter lead-in -> faster opening
    op = ease_io(prog(t, 0.55 * k, 1.45 * k))
    half = op * H / 2
    top, bot = int(H / 2 - half), int(math.ceil(H / 2 + half))
    fr[:max(0, top)] = 0
    fr[min(H, bot):] = 0
    lw = ease_out(prog(t, 0.05, 0.6 * k)) * W * 0.9
    la = 1 - prog(t, 1.25 * k, 1.6 * k)
    gold_line(fr, W / 2, max(top, 1), lw, a=la)
    gold_line(fr, W / 2, min(bot, H - 2), lw, a=la)

    pop_in(fr, A["emblem_big"], W / 2, 152, "mm", 0.95 * k, t, 0.7, s0=0.7, shimmer=shimmer_pos(t, 1.7 * k))
    text_in(fr, A["i_l1"], W / 2, 278, "mm", c0["start"], t)
    p2 = prog(t, R["l2"] - 0.1, R["l2"] + 0.6)
    if p2 > 0:
        place(fr, A["i_l2"], W / 2, 384, "mm", a=min(1, p2 * 2), scale=lerp(1.18, 1, ease_out(p2)),
              shimmer=shimmer_pos(t, R["shine"], 1.2))
    text_in(fr, A["i_l3"], W / 2, 490, "mm", R["l3"] - 0.05, t)
    gold_line(fr, W / 2, 545, 320 * ease_out(prog(t, R["l3"] + 0.2, R["l3"] + 1.0)))
    return fr


def sc_location(t, S):
    c, word = TL["roles"]["location"]["cue"], TL["roles"]["location"]["word"]
    u = prog(t, S["start"] - 0.4, S["end"] + 0.4)
    fr, view = cam(A["img"], lerp(560, 700, ease_io(u)), 330, lerp(1.22, 1.1, ease_io(u)))
    place(fr, A["topgrad"], 0, 0)
    tip = to_screen(view, 706, 186)
    pd = prog(t, c["start"] - 0.15, c["start"] + 0.75)
    if pd > 0:
        for k in range(2):
            ph = ((t - c["start"] - 0.6 - k * 0.6) % 1.2) / 1.2
            if t > c["start"] + 0.6 + k * 0.6:
                place(fr, A["ring"], tip[0], tip[1], "mm", a=(1 - ph) * 0.9, scale=lerp(0.25, 1.4, ease_out(ph)))
        place(fr, A["pin"], tip[0], tip[1] - (1 - g.bounce(pd)) * 340, "mb", a=min(1, pd * 4))
    x = W - 64
    text_in(fr, A["l_t1"], x, 22, "rt", c["start"], t)
    text_in(fr, A["l_t2"], x, 96, "rt", word - 0.05, t)
    gold_line(fr, x - 160, 160, 320 * ease_out(prog(t, word, word + 0.8)))
    place(fr, A["l_t3"], x, 172, "rt", a=ease_out(prog(t, word + 0.3, word + 0.9)))
    return fr


def sc_standing(t, S):
    R = TL["roles"]["standing"]
    c2 = R["cue"]
    u = prog(t, S["start"] - 0.5, S["end"] + 0.5)
    fr, _ = cam(A["img"], lerp(905, 915, u), lerp(420, 405, u), lerp(1.32, 1.62, ease_io(u)), sx=W * 0.7)
    place(fr, A["leftgrad"], 0, 0)
    x = 660
    pb = prog(t, c2["start"] - 0.1, c2["start"] + 0.5)
    if pb > 0:
        place(fr, A["s_badge"], x, 102, "rt", a=ease_out(pb), scale=lerp(0.9, 1, ease_out(pb)),
              shimmer=shimmer_pos(t, c2["start"] + 0.6, 1.2))
    text_in(fr, A["s_t1"], x, 178, "rt", R["t1"] - 0.1, t, shimmer=shimmer_pos(t, R["shine"], 1.3))
    text_in(fr, A["s_t2"], x, 268, "rt", R["t2"] - 0.1, t)
    for k, (tw, (ic, lb)) in enumerate(zip(R["chips"], A["s_chips"])):
        t0 = tw - 0.1
        cx = x - 90 - k * 186
        pop_in(fr, ic, cx, 410, "mm", t0, t, 0.5)
        text_in(fr, lb, cx, 462, "mt", t0 + 0.12, t, 0.5, rise=8)
    return fr


FEATURE_HOME = (640, 400, 1.12)
FEATURE_CAMS = {"sofa": (420, 372, 1.85), "shield": (575, 545, 1.9), "car": (700, 640, 1.6),
                "elevator": (805, 560, 2.0), "diamond": (330, 300, 1.7)}


def features_cam(t):
    R = TL["roles"]["features"]
    keys = [R["header"]] + R["rows"]
    cams = [list(FEATURE_HOME)] + [list(FEATURE_CAMS[ic]) for _, ic in CONFIG["features"][:len(R["rows"])]]
    for k, (_, ic) in enumerate(CONFIG["features"][:len(R["rows"])]):
        if ic == "elevator":  # ride up the building while the elevator is mentioned
            cams[k + 1][1] = lerp(560, 290, ease_io(prog(t, R["rows"][k] - 0.1, min(R["ends"][k], R["rows"][k] + 3) + 0.2)))
    cur = cams[0]
    for k in range(1, len(keys)):
        e = ease_io(prog(t, keys[k] - 0.35, keys[k] + 0.75))
        if e <= 0:
            break
        prev = cur
        cur = [lerp(prev[0], cams[k][0], e), lerp(prev[1], cams[k][1], e),
               math.exp(lerp(math.log(prev[2]), math.log(cams[k][2]), e))]
    return cur


def sc_features(t, S):
    R = TL["roles"]["features"]
    fx, fy, z = features_cam(t)
    drift = 1 + 0.03 * math.sin((t - S["start"]) * 0.35)
    fr, _ = cam(A["img"], fx, fy, z * drift, sx=445, sy=330)
    ps = ease_out(prog(t, S["start"] - 0.2, S["start"] + 0.6))
    off = (1 - ps) * 560
    px, py = W - 40 + off, 48
    place(fr, A["f_panel"], px, py, "rt", a=ps)
    hx = px - 40
    text_in(fr, A["f_head"], hx, py + 30, "rt", R["header"] - 0.1, t)
    gold_line(fr, px - 265, py + 110, 420 * ease_out(prog(t, R["header"], R["header"] + 0.8)))
    for k, (ic, white, gold) in enumerate(A["f_rows"][:len(R["rows"])]):
        t0, nxt = R["rows"][k], R["ends"][k]
        yc = py + 160 + k * 84
        active = fade(t, t0 - 0.1, nxt - 0.1, 0.25, 0.25)
        if active > 0:
            place(fr, A["f_hl"], px - 265, yc, "mm", a=active)
        pop_in(fr, ic, hx - 6, yc, "rm", t0 - 0.15, t, 0.45)
        p = prog(t, t0 - 0.05, t0 + 0.6)
        if p > 0:
            xx = hx - 82 + (1 - ease_out(p)) * 30
            place(fr, white, xx, yc, "rm", a=ease_out(p) * (1 - active))
            place(fr, gold, xx, yc, "rm", a=ease_out(p) * active)
    return fr


def sc_plan(t, S):
    R = TL["roles"]["plan"]
    c10, c11, c12 = R["title"], R["pick"], R["invest"]
    zin = ease_io(prog(t, c11["start"] - 0.2, c11["start"] + min(1.4, c11["dur"] * 0.8)))
    zout = ease_io(prog(t, c12["start"] + 0.3, c12["start"] + 1.8)) if c12 else 0.0
    ax0, ay0, ax1, ay1 = CONFIG["apartment_box"]
    acx, acy = (ax0 + ax1) / 2, (ay0 + ay1) / 2
    fx = lerp(lerp(728, acx, zin), 728, zout)
    fy = lerp(lerp(372, acy + 20, zin), 380, zout)
    z = math.exp(lerp(lerp(math.log(1.06), math.log(2.3), zin), math.log(1.1), zout))
    real, view = cam(A["img"], fx, fy, z)
    blue, _ = cam(A["blueprint"], fx, fy, z)
    sp = ease_io(prog(t, c10["end"] - 0.2, c11["start"] + 0.8))
    if sp <= 0:
        fr = blue
    elif sp >= 1:
        fr = real
    else:
        xs = lerp(W + 60, -60, sp)
        cols = np.clip((np.arange(W, dtype=np.float32) - xs) / 50, 0, 1)[None, :, None]
        fr = blue * (1 - cols) + real * cols
        glow = np.exp(-((np.arange(W, dtype=np.float32) - xs) / 10) ** 2)[None, :, None]
        fr += glow * np.array([0.55, 0.85, 1.0], np.float32) * 0.9

    # blueprint dimension lines (draw-on)
    dp = ease_out(prog(t, c10["start"], c10["start"] + 1.2)) * (1 - prog(t, c10["end"], c10["end"] + 0.5))
    if dp > 0:
        x0s, ys = to_screen(view, 62, 712)
        x1s, _ = to_screen(view, 1376, 712)
        xv, y0v = to_screen(view, 1410, 186)
        _, y1v = to_screen(view, 1410, 690)
        col = (0.86, 0.94, 1.0)
        seg(fr, x0s, ys, x0s + (x1s - x0s) * dp, ys, 2, col, 0.8)
        seg(fr, xv, y1v - (y1v - y0v) * dp, xv, y1v, 2, col, 0.8)
        for xx in (x0s, x0s + (x1s - x0s) * dp):
            seg(fr, xx, ys - 10, xx, ys + 10, 2, col, 0.8)
        for yy in (y1v, y1v - (y1v - y0v) * dp):
            seg(fr, xv - 10, yy, xv + 10, yy, 2, col, 0.8)

    # title stamp
    pt = prog(t, c10["start"] - 0.15, c10["start"] + 0.35)
    out = prog(t, c11["start"] + 0.2, c11["start"] + 0.7)
    if pt > 0 and out < 1:
        s = lerp(1.3, 1, ease_out(pt))
        a = min(1, pt * 2) * (1 - out)
        yy = 112 - 40 * ease_in(out)
        place(fr, A["p_frame"], W / 2, yy + 32, "mm", a=a * 0.95, scale=s)
        place(fr, A["p_t1"], W / 2, yy, "mm", a=a, scale=s)
        place(fr, A["p_t2"], W / 2, yy + 76, "mm", a=a, scale=s, shimmer=shimmer_pos(t, c10["start"] + 0.2))

    # choose your apartment
    sel = prog(t, c11["start"] + 0.3, c11["start"] + min(1.5, c11["dur"] * 0.85))
    sel_out = prog(t, c12["start"] + 0.2, c12["start"] + 0.8) if c12 else 0.0
    if sel > 0 and sel_out < 1:
        x0, y0 = to_screen(view, ax0, ay0)
        x1, y1 = to_screen(view, ax1, ay1)
        a = 1 - sel_out
        d = fr[int(max(0, y0)):int(min(H, y1)), int(max(0, x0)):int(min(W, x1))]
        d += (np.array([0.95, 0.8, 0.45], np.float32) - d) * 0.12 * a * ease_out(sel)
        rect_stroke(fr, x0, y0, x1, y1, ease_io(sel), width=4, a=a)
        pop_in(fr, A["p_tag"], (x0 + x1) / 2, y0 - 12, "mb", T.at(c11, "شقتكم", 0.4), t, 0.5, a=a)

    # invest
    if c12 is None:
        return fr
    if t > c12["start"] - 0.5:
        place(fr, A["topgrad"], 0, 0, a=prog(t, c12["start"] - 0.4, c12["start"] + 0.3))
    text_in(fr, A["p_t3"], W / 2, 64, "mm", c12["start"] - 0.05, t)
    text_in(fr, A["p_t4"], W / 2, 140, "mm", T.at(c12, "وفي") - 0.1, t, shimmer=shimmer_pos(t, T.at(c12, "استثنائي") + 0.3))
    pop_in(fr, A["p_chart"], W / 2 + A["p_t3"].cw / 2 + 52, 64, "mm", c12["start"] + 0.3, t)
    return fr


def sc_contact(t, S):
    u = prog(t, S["start"] - 0.5, S["end"] + 0.5)
    fr, _ = cam(A["blur"], lerp(700, 760, u), 380, lerp(1.08, 1.22, u))
    fr *= 0.42
    fr += np.array([0.05, 0.03, 0.0], np.float32)
    particles(fr, t, 0.8)
    R = TL["roles"]["contact"]
    c13 = R["head"]

    # portrait + rotating gold arcs
    pcx, pcy = 330, 300
    pp = prog(t, S["start"] + 0.1, S["start"] + 0.8)
    if pp > 0:
        rings(fr, pcx, pcy, 172, t, ease_out(pp))
        place(fr, A["c_portrait"], pcx, pcy, "mm", a=min(1, pp * 2), scale=lerp(0.85, 1, ease_back(pp)))
        text_in(fr, A["c_name"], pcx, 492, "mt", S["start"] + 0.5, t)
        gold_line(fr, pcx, 545, 220 * ease_out(prog(t, S["start"] + 0.8, S["start"] + 1.5)))

    x = W - 64
    text_in(fr, A["c_head"], x, 52, "rt", c13["start"] - 0.05, t)
    text_in(fr, A["c_fr"], x, 128, "rt", c13["start"] + 0.7, t)
    appear, windows = R["appear"], R["windows"]
    for k, Row in enumerate(A["c_rows"]):
        yc = 252 + k * 126
        p = prog(t, appear[k], appear[k] + 0.6)
        if p <= 0:
            continue
        win = windows[k]
        later = [w[0] for w in windows[k + 1:] if w]
        if win is None:
            on = 0.0
        elif later:
            on = fade(t, win[0] - 0.2, later[0] - 0.4, 0.3, 0.3)
        else:
            on = prog(t, win[0] - 0.2, win[0] + 0.1)
        xo = (1 - ease_out(p)) * 60
        place(fr, A["c_row"], x + xo, yc, "rm", a=ease_out(p) * (1 - on))
        place(fr, A["c_row_on"], x + xo, yc, "rm", a=ease_out(p) * on)
        icon = A["c_icons"][Row["icon"]]
        pulse = 1 + 0.06 * on * math.sin((t - win[0]) * 6) if on > 0 else 1
        place(fr, icon, x - 22 + xo, yc, "rm", a=min(1, p * 2), scale=pulse)
        tx = x - 118 + xo
        place(fr, Row["label"], tx, yc - 22, "rm", a=ease_out(p))
        n = 1 + sum(1 for gt in R["groups"][k] if t >= gt - 0.05)
        n = min(n, len(Row["nums"]))
        full = Row["nums"][-1]
        lx = tx - full.cw
        place(fr, Row["nums"][n - 1], lx, yc + 20, "lm", a=ease_out(p))
    return fr


def rings(fr, cx, cy, r, t, a):
    size = int(r * 2 + 40)
    img = Image.new("L", (size * 2, size * 2))
    d = ImageDraw.Draw(img)
    c = size
    d.ellipse((c - 2 * (r - 12), c - 2 * (r - 12), c + 2 * (r - 12), c + 2 * (r - 12)), outline=255, width=6)
    rot = math.degrees(t * 0.9)
    for k in range(3):
        st = rot + k * 120
        d.arc((c - 2 * r, c - 2 * r, c + 2 * r, c + 2 * r), st, st + 70, fill=255, width=8)
    m = np.asarray(img.resize((size, size), Image.LANCZOS), np.float32) / 255
    place(fr, g.from_mask(m, gold=True), cx, cy, "mm", a=a)


def sc_outro(t, S):
    R = TL["roles"]["outro"]
    c18, c19 = R["l1"], R["l2"]
    endc = R["endcard"]
    u = prog(t, S["start"] - 0.5, TL["total"])
    fx, fy, z = 728, 372, lerp(1.2, 1.0, ease_out(u))
    fr, _ = cam(A["img"], fx, fy, z)
    e = ease_io(prog(t, endc, endc + 0.9))
    if e > 0:
        bl, _ = cam(A["blur"], fx, fy, z)
        fr = fr * (1 - e) + bl * 0.38 * e
    fr += np.array([0.06, 0.035, 0.0], np.float32) * (1 - e)
    out = 1 - prog(t, endc - 0.1, endc + 0.4)
    if out > 0:
        place(fr, A["topgrad"], 0, 0, a=out)
        text_in(fr, A["o_t1"], W / 2, 76, "mm", c18["start"] - 0.05, t, a=out, shimmer=shimmer_pos(t, c18["start"] + 0.9))
        if c19:
            text_in(fr, A["o_t2"], W / 2, 150, "mm", c19["start"] - 0.05, t, a=out)
    if e > 0:
        q = endcard_pace(TL)
        particles(fr, t, e)
        pop_in(fr, A["o_emblem"], W / 2, 150, "mm", endc + 0.2 * q, t, 0.8 * q, s0=0.7,
               shimmer=shimmer_pos(t, endc + 1.0 * q, 1.2))
        text_in(fr, A["o_name"], W / 2, 288, "mm", endc + 0.45 * q, t, 0.7 * q)
        place(fr, A["o_sub"], W / 2, 345, "mm", a=ease_out(prog(t, endc + 0.7 * q, endc + 1.3 * q)))
        gold_line(fr, W / 2, 392, 520 * ease_out(prog(t, endc + 0.8 * q, endc + 1.6 * q)))
        # contact strip
        items = A["o_contacts"]
        gap = 46
        widths = [ic.cw + 12 + tx.cw for ic, tx in items]
        x = W / 2 + (sum(widths) + gap * (len(items) - 1)) / 2
        for k, ((ic, tx), wdt) in enumerate(zip(items, widths)):
            p = prog(t, endc + (1.0 + k * 0.15) * q, endc + (1.6 + k * 0.15) * q)
            if p > 0:
                place(fr, ic, x, 462 + (1 - ease_out(p)) * 16, "rm", a=ease_out(p))
                place(fr, tx, x - ic.cw - 12, 462 + (1 - ease_out(p)) * 16, "rm", a=ease_out(p))
            x -= wdt + gap
        place(fr, A["o_agency"], W / 2, 540, "mm", a=ease_out(prog(t, endc + 1.6 * q, endc + 2.2 * q)))
    return fr


def endcard_pace(tl):
    """1.0 with the long end card; < 1 compresses its animations when the cut leaves less time."""
    return max(0.55, min(1.0, (tl["total"] - tl["roles"]["outro"]["endcard"] - 0.6) / 2.95))


SCENE_FN = dict(intro=sc_intro, location=sc_location, standing=sc_standing, features=sc_features,
                plan=sc_plan, contact=sc_contact, outro=sc_outro)
TRANS_KIND = ["goldwipe", "zoom", "push", "scan", "iris", "flash"]


# ====================================================================== transitions
def zoomed(fr, s):
    if abs(s - 1) < 1e-3:
        return fr
    im = Image.fromarray((np.clip(fr, 0, 1) * 255).astype(np.uint8))
    bw, bh = W / s, H / s
    box = ((W - bw) / 2, (H - bh) / 2, (W + bw) / 2, (H + bh) / 2)
    return to_arr(im.resize((W, H), Image.BILINEAR, box=box))


def transition(kind, a, b, x):
    xs = np.arange(W, dtype=np.float32)[None, :, None]
    ys = np.arange(H, dtype=np.float32)[:, None, None]
    if kind == "goldwipe":
        d = ((W - xs) + 0.45 * ys) / (W + 0.45 * H)
        pos = lerp(-0.12, 1.12, ease_io(x))
        m = np.clip((pos - d) / 0.02, 0, 1)
        band = np.exp(-((d - pos + 0.04) / 0.035) ** 2)
        gold = g.gold_gradient(H, W)
        out = a * (1 - m) + b * m
        return out * (1 - band * 0.9) + gold * band * 0.9
    if kind == "zoom":
        e = ease_io(x)
        A_ = zoomed(a, 1 + 0.35 * e)
        B_ = zoomed(b, 1.25 - 0.25 * e)
        out = A_ * (1 - e) + B_ * e
        return out + 0.12 * math.sin(math.pi * x)
    if kind == "push":
        e = ease_io(x)
        off = int(e * W)
        out = np.empty_like(a)
        out[:, off:] = a[:, :W - off]
        out[:, :off] = b[:, W - off:]
        if 0 < off < W:
            seam = np.exp(-((xs - off) / 8) ** 2) * 0.8
            out = out + seam * np.array([0.95, 0.8, 0.5], np.float32)
        return out
    if kind == "scan":
        pos = lerp(-30, H + 30, ease_io(x))
        m = np.clip((pos - ys) / 24, 0, 1)
        glow = np.exp(-((ys - pos) / 7) ** 2) + 0.35 * np.exp(-((ys - pos) / 40) ** 2)
        out = a * (1 - m) + b * m
        return out + glow * np.array([0.55, 0.85, 1.0], np.float32)
    if kind == "iris":
        cx, cy = 330, 300
        r = ease_in(x) * math.hypot(W, H) * 1.05
        dist = np.sqrt((xs - cx) ** 2 + (ys - cy) ** 2)
        m = np.clip((r - dist) / 20, 0, 1)
        ring = np.exp(-((dist - r) / 6) ** 2) * (r > 1)
        out = a * (1 - m) + b * m
        return out + ring * np.array([0.95, 0.8, 0.45], np.float32)
    if kind == "flash":
        e = ease_io(x)
        out = a * (1 - e) + b * e
        fl = math.sin(math.pi * x) ** 2
        return out * (1 - 0.35 * fl) + fl * np.array([1.0, 0.88, 0.66], np.float32) * 0.45
    raise KeyError(kind)


# ====================================================================== frame
def subtitles(fr, t):
    for c, (txt, box) in zip(TL["cues"], A["subs"]):
        t0, t1 = c["start"] - 0.06, c["end"] + min(c["pause"], 0.25)
        if t0 - 0.2 < t < t1 + 0.2:
            a = fade(t, t0, t1, 0.14, 0.14)
            y = H - 42 + 6 * (1 - ease_out(prog(t, t0, t0 + 0.25)))
            place(fr, box, W / 2, y, "mm", a=a)
            place(fr, txt, W / 2, y - 2, "mm", a=a)


def watermark(fr, t):
    a = fade(t, TL["scenes"][1]["start"] + 0.4, TL["vo_end"] + 0.25, 0.5, 0.4)
    if a > 0:
        place(fr, A["wm_emblem"], 22, 16, "lt", a=a * 0.95)
        place(fr, A["wm_text"], 76, 38, "lm", a=a * 0.95)


def frame(t):
    sc = TL["scenes"]
    k = max(i for i, s in enumerate(sc) if s["start"] <= t) if t >= 0 else 0
    fr = None
    for j, b in enumerate(TL["transitions"]):
        if abs(t - b) < TL["trans"] / 2:
            x = (t - (b - TL["trans"] / 2)) / TL["trans"]
            a = SCENE_FN[sc[j]["name"]](t, sc[j])
            bb = SCENE_FN[sc[j + 1]["name"]](t, sc[j + 1])
            fr = transition(TRANS_KIND[j], a, bb, x)
            break
    if fr is None:
        fr = SCENE_FN[sc[k]["name"]](t, sc[k])
    fr = np.clip(fr, 0, 1) * A["vignette"]
    watermark(fr, t)
    subtitles(fr, t)
    fr *= 1 - prog(t, TL["total"] - 0.6, TL["total"])
    return (np.clip(fr, 0, 1) * 255 + 0.5).astype(np.uint8)


# ====================================================================== output
def render_chunk(args):
    idx, f0, f1 = args
    out = os.path.join(BUILD, f"seg_{idx:02d}.mp4")
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
           "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-preset", "slow", "-crf", "18", "-threads", "2",
           "-profile:v", "high",
           "-pix_fmt", "yuv420p", "-g", "60", out]
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
    chunks = [(i, i * n // k, (i + 1) * n // k) for i in range(k)]
    with mp.get_context("fork").Pool(k) as pool:
        segs = pool.map(render_chunk, chunks)
    lst = os.path.join(BUILD, "segments.txt")
    with open(lst, "w") as f:
        f.writelines(f"file '{s}'\n" for s in segs)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy",
                    os.path.join(BUILD, "video_silent.mp4")], check=True)
    T.srt(TL, os.path.join(BUILD, "subtitles_ar.srt"))
    print("frames", n, "->", os.path.join(BUILD, "video_silent.mp4"))


def make_blueprint(big):
    """Architectural blueprint look: white edge lines on blue paper with a grid."""
    gray = np.asarray(big.convert("L").filter(ImageFilter.GaussianBlur(1.6)), np.float32) / 255
    gx = np.zeros_like(gray)
    gy = np.zeros_like(gray)
    gx[:, 1:-1] = gray[:, 2:] - gray[:, :-2]
    gy[1:-1] = gray[2:] - gray[:-2]
    mag = np.sqrt(gx ** 2 + gy ** 2)
    e = np.clip(mag * 7, 0, 1) ** 0.8
    h, w = gray.shape
    yy, xx = np.mgrid[0:h, 0:w]
    paper = np.empty((h, w, 3), np.float32)
    top, bot = np.array([16, 60, 108], np.float32) / 255, np.array([8, 34, 70], np.float32) / 255
    paper[:] = (top + (bot - top) * (yy / h)[..., None])
    grid = ((xx % 48 < 2) | (yy % 48 < 2)) * 0.07 + ((xx % 240 < 3) | (yy % 240 < 3)) * 0.1
    line = np.array([0.88, 0.95, 1.0], np.float32)
    out = paper + grid[..., None] * line
    out = out * (1 - e[..., None] * 0.92) + line * e[..., None] * 0.92 + gray[..., None] * 0.06
    return Image.fromarray((np.clip(out, 0, 1) * 255).astype(np.uint8))


if __name__ == "__main__":
    main()
