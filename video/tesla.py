"""Trend video: the Tesla parked in the Résidence La Sirène render lifts off on jets, climbs the façade floor by
floor, does a 360° flip and lands on the rooftop (R+6). Arabic voice-over, music and sound design.

python3 tesla.py                -> output/sirene_tesla.mp4  (1080x1920, 19 s)
python3 tesla.py --still 3 6 9  -> build/sirene/preview/still_*.png

The car is cut out of the render (sirene_plate.py -> build/sirene/car_sprite.npy + plate.png, the render
without the car), then animated over the clean plate. The voice-over lines come from sirene_vo.py (vo_sirene/).
"""
import argparse
import json
import math
import multiprocessing as mp
import os
import subprocess

import numpy as np
import soundfile as sf
from PIL import Image, ImageFilter

import gfx as g
from gfx import ease_back, ease_in, ease_io, ease_out, fade, lerp, place, prog

HERE = os.path.dirname(os.path.abspath(__file__))
BUILD = os.path.join(HERE, "build", "sirene")
VO_DIR = os.path.join(HERE, "vo_sirene")
OUT = os.path.join(HERE, "output", "sirene_tesla.mp4")
W, H, FPS = 1080, 1920, 30
TOTAL = 19.0
PANEL_Y, PANEL_H = 520, 900                   # photo window inside the vertical frame
SW, SH = 1488, 845                            # source render size
CAR_BOX = (0, 712, 260, 805)                  # where the car sits in the render
CAR_C = ((CAR_BOX[0] + CAR_BOX[2]) / 2, (CAR_BOX[1] + CAR_BOX[3]) / 2)
CAR_HGT = CAR_BOX[3] - CAR_BOX[1]
ROOF = ((670, 132), (1062, 104))              # top edge of the "la Sirène" band (the rooftop line)
FLOORS = [560, 495, 430, 365, 300, 235]       # car bottom above these -> R+1 .. R+6
FLOOR_BANDS = [(540, 600), (475, 540), (410, 475), (345, 410), (280, 345), (215, 280)]
FACADE_X = (310, 1300)
SIGN = (857, 130)                             # centre of the "la Sirène" neon sign
SCREEN = {
    "phones": [("+216 20 026 026", "phone"), ("+216 25 684 686", "whatsapp"), ("+216 29 404 009", "whatsapp")],
    "agency": "IMMOBILIÈRE WAHRA",
}
TESLA_RED = (232, 33, 39)

# beats (seconds) – 120 BPM, the beat drops at take-off; one floor per beat
BEAT = 0.5
T_POWER, T_LIFT = 2.4, 3.9
T_FLOOR0 = T_LIFT + 0.6
T_TOP = T_FLOOR0 + BEAT * 5                   # R+6 reached
T_SPIN0, T_SPIN1 = 8.0, 8.85
T_ARRIVE, T_LAND = 9.75, 10.4
T_INFO = 13.8
VO_AT = {"hook": 0.35, "power": 4.0, "climb": 6.05, "spin": 7.75, "land": 10.6, "addr": 13.95, "call": 16.6}
LAND_X = 870
S_END = 0.5
A = {}


# ====================================================================== motion
def roof_y(x):
    (x0, y0), (x1, y1) = ROOF
    return y0 + (x - x0) * (y1 - y0) / (x1 - x0)


def land_cy():
    return roof_y(LAND_X) + 6 - CAR_HGT * S_END / 2


def climb_keys():
    """Car bottom (source px) over time: one floor per beat, then across to above the landing spot."""
    ks = [(T_LIFT, CAR_BOX[3] - 14)] + [(T_FLOOR0 + BEAT * k, f) for k, f in enumerate(FLOORS)]
    ks += [(T_TOP + 0.9, 125), (T_ARRIVE, land_cy() + CAR_HGT * S_END / 2 - 70)]
    return ks


def interp(keys, t):
    for (t0, v0), (t1, v1) in zip(keys, keys[1:]):
        if t <= t1:
            return lerp(v0, v1, prog(t, t0, t1))
    return keys[-1][1]


def spin(t):
    return 360 * ease_io(prog(t, T_SPIN0, T_SPIN1))


def car_state(t):
    """Car centre (source px), scale, rotation (deg, + = nose up) and 'flying' amount at time t."""
    x, y = CAR_C
    s, ang, fly = 1.0, 0.0, 0.0
    if t < T_LIFT:
        p = ease_io(prog(t, T_POWER, T_LIFT))
        y -= 16 * p
        x += 1.5 * math.sin(t * 47) * p
        ang = 0.9 * math.sin(t * 23) * p
        fly = 0.35 * p
    elif t < T_ARRIVE:
        s = lerp(1.0, 0.64, ease_out(prog(t, T_LIFT, T_TOP))) if t < T_TOP else \
            lerp(0.64, S_END, ease_io(prog(t, T_TOP, T_ARRIVE)))
        k = climb_keys()
        bottom = 0.5 * interp(k, t) + 0.25 * interp(k, t - 0.06) + 0.25 * interp(k, t + 0.06)
        y = bottom - CAR_HGT * s / 2
        x = lerp(CAR_C[0], 420, ease_io(prog(t, T_LIFT, T_TOP))) if t < T_TOP else \
            lerp(420, LAND_X, ease_io(prog(t, T_TOP, T_ARRIVE)))
        y -= 26 * math.sin(math.pi * prog(t, T_SPIN0 - 0.1, T_SPIN1 + 0.1))       # hop up for the flip
        ang = 6 * (1 - prog(t, T_TOP - 0.5, T_TOP)) - 3 * fade(t, T_TOP, T_SPIN0, 0.3, 0.3) \
            + 4 * prog(t, T_ARRIVE - 0.4, T_ARRIVE) + spin(t) + 0.6 * math.sin(t * 9)
        fly = 1.0
    else:
        p = prog(t, T_ARRIVE, T_LAND)
        x, y = LAND_X, lerp(land_cy() - 70, land_cy(), ease_out(p))
        b = prog(t, T_LAND, T_LAND + 0.35)
        y -= 6 * math.sin(math.pi * b) * (1 - b)
        s, ang = S_END, 4.0
        fly = 1 - prog(t, T_LAND, T_LAND + 0.6)
    return x, y, s, ang, fly


def jet_power(t):
    """Rear jet strength 0..1.5."""
    if t < T_POWER:
        return 0.0
    if t < T_LIFT:
        return 0.35 * ease_in(prog(t, T_POWER + 0.4, T_LIFT))
    if t < T_LAND + 0.3:
        boost = 1.5 * math.exp(-(t - T_LIFT) * 2.5) + 0.4 * math.exp(-max(0, t - T_TOP) * 3) * (t > T_TOP)
        spin_b = 0.5 * math.sin(math.pi * prog(t, T_SPIN0, T_SPIN1))
        return min(1.5, 0.75 + boost + spin_b) * (1 - prog(t, T_ARRIVE, T_LAND + 0.3))
    return 0.0


def under_power(t):
    """Downward lift jets (hover and take-off)."""
    return fade(t, T_POWER, T_LIFT + 0.9, 0.5, 0.6) * (1 + 0.8 * math.exp(-abs(t - T_LIFT) * 5))


def floors_passed(t):
    x, y, s, *_ = car_state(t)
    return sum(1 for f in FLOORS if y + CAR_HGT * s / 2 < f) if t > T_LIFT else 0


def floor_times():
    out, last = [], 0
    for n in range(int(T_LIFT * FPS), int(T_LAND * FPS) + 1):
        k = floors_passed(n / FPS)
        if k > last:
            out.append((n / FPS, k))
            last = k
    return out


def camera(t):
    """(centre x, centre y, zoom) of the photo window, in source px."""
    def follow(tt):
        x, y, s, *_ = car_state(tt - 0.12)
        return (lerp(x, 700, 0.3), y + 40, lerp(1.6, 1.3, prog(tt, T_TOP, T_ARRIVE)))
    keys = [(0.0, (500, 422, 1.0)), (2.0, (520, 440, 1.06)), (3.1, (330, 600, 1.5)), (4.1, follow),
            (9.4, follow), (10.3, (860, 200, 1.55)), (12.4, (872, 160, 1.85)), (14.8, (800, 300, 1.3)),
            (TOTAL, (790, 310, 1.26))]
    for (t0, a), (t1, b) in zip(keys, keys[1:]):
        if t <= t1:
            va = a(t) if callable(a) else a
            vb = b(t) if callable(b) else b
            e = ease_io(prog(t, t0, t1)) if not (callable(a) and callable(b)) else 0.0
            return tuple(lerp(va[k], vb[k], e) for k in range(3))
    return keys[-1][1]


def window(t):
    cx, cy, z = camera(t)
    ww, wh = SH * (W / PANEL_H) / z, SH / z
    x0 = min(max(cx - ww / 2, 0), SW - ww)
    y0 = min(max(cy - wh / 2, 0), SH - wh)
    return x0, y0, W / ww


def vo_lines():
    meta = json.load(open(os.path.join(VO_DIR, "lines.json"), encoding="utf-8"))
    return [dict(m, start=VO_AT[m["key"]], end=VO_AT[m["key"]] + m["dur"]) for m in meta]


# ====================================================================== assets
def glow_ellipse(w, h, color):
    yy, xx = np.mgrid[-h:h + 1, -w:w + 1].astype(np.float32)
    d = np.sqrt((xx / w) ** 2 + (yy / h) ** 2)
    L = g.from_mask(np.clip(1 - d, 0, 1) ** 1.6, color)
    L.pad = 0
    return L


def smoke_sprite(r, seed, color=(196, 190, 182)):
    rng = np.random.default_rng(seed)
    yy, xx = np.mgrid[-r:r + 1, -r:r + 1].astype(np.float32)
    d = np.sqrt(xx ** 2 + yy ** 2) / r
    n = Image.fromarray((rng.random((2 * r + 1, 2 * r + 1)) * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(r / 6))
    noise = np.asarray(n, np.float32) / 255
    m = np.clip(1 - d, 0, 1) ** 1.3 * (0.65 + 0.7 * (noise - 0.5) * 2)
    L = g.from_mask(np.clip(m, 0, 1), color)
    L.pad = 0
    return L


def jet_sprite(length, half_h):
    """Exhaust plume pointing left from the image centre (so it rotates around its nozzle)."""
    xs = np.arange(-length, length + 1, dtype=np.float32)
    ys = np.arange(-half_h, half_h + 1, dtype=np.float32)
    X, Y = np.meshgrid(xs, ys)
    u = np.clip(-X / length, 0, 1)                         # 0 at the nozzle, 1 at the tail
    width = half_h * (0.22 + 0.78 * u ** 0.7)
    body = np.exp(-(Y / np.maximum(width, 1)) ** 2) * (X <= 0) * (1 - u) ** 1.15
    core = np.exp(-(Y / np.maximum(width * 0.35, 1)) ** 2) * (X <= 0) * np.exp(-u * 4.5)
    rgb = np.zeros(X.shape + (3,), np.float32)
    col_tail, col_mid, col_core = (np.array(c, np.float32) / 255 for c in ((70, 120, 255), (90, 210, 255), (255, 255, 255)))
    rgb += body[..., None] * (col_mid * (1 - u[..., None]) + col_tail * u[..., None])
    rgb += core[..., None] * col_core
    a = np.clip(body * 0.9 + core, 0, 1)
    arr = np.dstack([np.clip(rgb, 0, 1), a]).astype(np.float32)
    L = g.Layer(arr)
    return L


def build():
    big = lambda im: im.resize((SW * 2, SH * 2), Image.LANCZOS).filter(ImageFilter.UnsharpMask(2, 70, 2))
    A["plate"] = big(Image.open(os.path.join(BUILD, "plate.png")).convert("RGB"))
    A["orig"] = big(Image.open(os.path.join(HERE, "assets", "sirene", "residence.jpg")).convert("RGB"))
    spr = np.load(os.path.join(BUILD, "car_sprite.npy"))
    rgba = spr.copy()
    rgba[..., :3] *= rgba[..., 3:4]
    A["car"] = rgba
    A["car_faded"] = rgba * np.clip(np.arange(rgba.shape[1]) / 22.0, 0, 1)[None, :, None]   # soften the cut rear
    bg = Image.open(os.path.join(HERE, "assets", "sirene", "residence.jpg")).convert("RGB")
    sc = max(W / SW, H / SH)
    bg = bg.resize((int(SW * sc), int(SH * sc)), Image.BILINEAR)
    bx = (bg.width - W) // 2
    bg = bg.crop((bx, 0, bx + W, H)).filter(ImageFilter.GaussianBlur(28))
    a = np.asarray(bg, np.float32) / 255 * 0.28
    yy = np.linspace(0, 1, H, dtype=np.float32)[:, None, None]
    A["bg"] = a * (1 - 0.3 * np.abs(yy - 0.5) * 2) + np.array([0.02, 0.025, 0.05], np.float32)
    A["under"] = glow_ellipse(150, 34, (90, 200, 255))
    A["dot"] = g.radial_sprite(14, (170, 225, 255), 1.6)
    A["dot_big"] = g.radial_sprite(40, (120, 200, 255), 1.8)
    A["flash"] = g.radial_sprite(160, (255, 240, 210), 1.4)
    A["neon"] = glow_ellipse(130, 26, (255, 236, 200))
    A["spark"] = [g.radial_sprite(r, c, 1.3) for r, c in ((5, g.GOLD_LIGHT), (7, (255, 220, 140)), (4, (255, 255, 255)))]
    A["shadow"] = glow_ellipse(140, 22, (0, 0, 0))
    A["jet"] = jet_sprite(170, 34)
    A["smoke"] = [smoke_sprite(r, k) for k, r in enumerate((60, 75, 90, 70, 85))]
    A["vapor"] = [smoke_sprite(r, 20 + k, (235, 240, 246)) for k, r in enumerate((26, 32, 38))]
    rng = np.random.default_rng(5)
    A["puffs"] = [dict(x=rng.uniform(-20, 280), y=rng.uniform(735, 820), k=int(rng.integers(0, 5)),
                       vx=rng.uniform(-25, 35), vy=rng.uniform(-22, 4), s0=rng.uniform(0.6, 1.0),
                       d=rng.uniform(0.0, 0.25), a=rng.uniform(0.6, 0.9)) for _ in range(26)]
    A["puffs"] += [dict(x=rng.uniform(20, 200), y=rng.uniform(715, 750), k=int(rng.integers(0, 5)),
                        vx=rng.uniform(-10, 10), vy=rng.uniform(-8, 2), s0=rng.uniform(0.7, 0.9),
                        d=rng.uniform(0.05, 0.3), a=0.85) for _ in range(8)]
    A["vapors"] = [dict(t0=T_POWER + 0.35 + 0.22 * k + rng.uniform(-0.04, 0.04), side=k % 2,
                        vx=rng.uniform(-60, 60), k=int(rng.integers(0, 3))) for k in range(int((T_LIFT - T_POWER) / 0.22) + 3)]
    A["roofpuffs"] = [dict(dx=rng.uniform(-90, 90), vx=rng.uniform(-60, 60), k=int(rng.integers(0, 5)),
                           s0=rng.uniform(0.25, 0.45)) for _ in range(9)]
    A["confetti"] = [dict(vx=rng.uniform(-260, 260), vy=rng.uniform(-420, -160), k=int(rng.integers(0, 3)),
                          ph=rng.uniform(0, 6.28), d=rng.uniform(0, 0.12)) for _ in range(70)]
    A["lines"] = [dict(x=rng.uniform(-200, W), y=rng.uniform(0, PANEL_H), l=rng.uniform(80, 260),
                       v=rng.uniform(900, 1600), a=rng.uniform(0.05, 0.16)) for _ in range(26)]
    f = g.font
    CA, MO, PL = "Cairo.ttf", "Montserrat.ttf", "PlayfairDisplay.ttf"
    A["cap"] = [
        [(g.text("حتّى", f(CA, 124, 900), blur=8, shadow=0.9), 0.3),
         (g.text("تسلا", f(CA, 124, 900), color=TESLA_RED, blur=8, shadow=0.9), 0.5)],
        [(g.text("تنجّم", f(CA, 84, 900), blur=7, shadow=0.9), 0.85), (g.text("زادة", f(CA, 84, 900), blur=7, shadow=0.9), 1.0),
         (g.text("تطلع", f(CA, 84, 900), blur=7, shadow=0.9), 1.15),
         (g.text("للسطح", f(CA, 84, 900), gold=True, blur=7, shadow=0.9), 1.3)],
        [(g.text("متاع", f(CA, 64, 800), blur=6, shadow=0.9), 1.6),
         (g.text("Résidence La Sirène R+6", f(MO, 50, 800), gold=True, blur=6, shadow=0.9), 1.75)],
    ]
    A["counter_box"] = g.rounded_box(196, 96, 18, alpha=0.82, border="gold", bw=3)
    A["counter"] = [g.text(f"R+{k}", f(MO, 50, 800), gold=True, blur=4) for k in range(0, 7)]
    A["counter"][0] = g.text("RDC", f(MO, 46, 800), gold=True, blur=4)
    A["arrow"] = g.from_mask(arrow_mask(34), gold=True)
    A["roof_tag"] = pill("وصلت للسطح!", f(CA, 44, 900))
    A["t360"] = g.text("360°", f(MO, 64, 800), gold=True, blur=6, shadow=0.9)
    A["b_res"] = g.text("RÉSIDENCE", f(MO, 26, 600), color=g.CREAM, tracking=12, blur=4)
    A["b_name"] = g.text("La Sirène", f(PL, 92, 700), gold=True, blur=7)
    A["b_r6"] = pill_dark("R+6", f(MO, 40, 800))
    A["ph_icons"] = {"phone": g.icon_badge("phone", 58),
                     "whatsapp": g.icon_badge("whatsapp", 58, ring=None, fill=g.WA_GREEN, fill_alpha=1.0,
                                              icon_color=g.WHITE, icon_scale=0.62)}
    A["ph_text"] = [g.text(n, f(MO, 40, 600), blur=4) for n, _ in SCREEN["phones"]]
    A["agency"] = g.text(SCREEN["agency"], f(MO, 22, 700), gold=True, tracking=8, blur=3)
    A["floor_times"] = floor_times()
    A["vo"] = vo_lines()
    A["subs"] = []
    for L in A["vo"]:
        t_ = g.text(L["sub"], f(CA, 40, 800), blur=4, shadow=0.8)
        A["subs"].append((t_, g.rounded_box(t_.cw + 50, 64, 18, alpha=0.62)))


def arrow_mask(px):
    yy, xx = np.mgrid[0:px, 0:px].astype(np.float32) / px
    tri = (yy > 0.12) & (yy < 0.62) & (np.abs(xx - 0.5) < (yy - 0.12) * 0.95)
    stem = (yy >= 0.55) & (yy < 0.92) & (np.abs(xx - 0.5) < 0.13)
    return (tri | stem).astype(np.float32)


def pill(label, fnt):
    t = g.text(label, fnt, color=g.DARK, shadow=0)
    box = g.rounded_box(t.cw + 70, t.ch + 34, (t.ch + 34) // 2, alpha=1.0, fill=g.GOLD_LIGHT)
    return box, t


def pill_dark(label, fnt):
    t = g.text(label, fnt, color=g.DARK, shadow=0)
    box = g.rounded_box(t.cw + 44, t.ch + 22, 14, alpha=1.0, fill=g.GOLD)
    return box, t


# ====================================================================== drawing
def to_panel(win, x, y):
    x0, y0, k = win
    return (x - x0) * k, (y - y0) * k


def to_layer(arr, scale, ang):
    im = Image.frombuffer("RGBa", (arr.shape[1], arr.shape[0]),
                          np.ascontiguousarray(np.clip(arr * 255 + 0.5, 0, 255).astype(np.uint8)).tobytes(),
                          "raw", "RGBa", 0, 1)
    w, h = max(2, round(arr.shape[1] * scale)), max(2, round(arr.shape[0] * scale))
    im = im.resize((w, h), Image.BICUBIC)
    if abs(ang) > 0.05:
        im = im.rotate(ang, resample=Image.BICUBIC, expand=True)
    return g.Layer(np.asarray(im, np.float32) / 255)


def car_layer(scale, ang, faded):
    return to_layer(A["car_faded"] if faded else A["car"], scale, ang)


def local(cx, cy, scale, ang, lx, ly):
    """Point given in sprite pixels from the sprite centre -> rotated/scaled position (y down, ang + = CCW)."""
    r = math.radians(ang)
    return cx + scale * (lx * math.cos(r) + ly * math.sin(r)), cy + scale * (-lx * math.sin(r) + ly * math.cos(r))


def jets(fr, t, win, cx, cy, s, ang):
    x0, y0, k = win
    px, py = to_panel(win, cx, cy)
    sw, sh = CAR_BOX[2] - CAR_BOX[0], CAR_HGT
    flick = 1 + 0.12 * math.sin(t * 61) + 0.08 * math.sin(t * 37 + 1)
    p = jet_power(t)
    if p > 0.02:
        nx, ny = local(px, py, s * k, ang, -sw / 2 + 8, sh * 0.08)
        place(fr, to_layer(A["jet"].a, s * k * 0.75 * p * flick, ang), nx, ny, "mm", a=min(1, p), add=True)
        place(fr, A["dot_big"], nx, ny, "mm", a=0.5 * min(1, p), scale=s * k * 0.9, add=True)
    u = under_power(t)
    if u > 0.02:
        for lx in (-sw * 0.28, sw * 0.22):
            nx, ny = local(px, py, s * k, ang, lx, sh * 0.42)
            place(fr, to_layer(A["jet"].a, s * k * 0.42 * u * flick, ang + 90), nx, ny, "mm", a=min(1, 0.8 * u), add=True)


def floor_lights(fr, t, win):
    """Each floor lights up as the car passes it: a warm sweep across the façade, then a soft glow."""
    x0, y0, k = win
    xs = np.arange(W, dtype=np.float32) / k + x0
    for tf, n in A["floor_times"]:
        if t < tf:
            break
        u = t - tf
        lo, hi = FLOOR_BANDS[n - 1]
        ya, yb = int(max(0, (lo - y0) * k)), int(min(PANEL_H, (hi - y0) * k))
        if yb <= ya:
            continue
        sweep_x = lerp(FACADE_X[0], FACADE_X[1], min(1, u / 0.55))
        sweep = np.exp(-((xs - sweep_x) / 70) ** 2) * (u < 0.7) * (1 - prog(u, 0.45, 0.7))
        inside = ((xs > FACADE_X[0]) & (xs < FACADE_X[1])).astype(np.float32)
        level = (0.32 * sweep + 0.07 * min(1, u / 0.5) * (1 - prog(t, T_LAND + 2, T_LAND + 3))) * inside
        rows = (np.arange(ya, yb, dtype=np.float32) / k + y0 - lo) / (hi - lo)
        prof = np.sin(np.pi * np.clip(rows, 0, 1)) ** 0.7                    # soft top/bottom edges
        fr[ya:yb] += prof[:, None, None] * level[None, :, None] * np.array([1.0, 0.82, 0.5], np.float32)


def panel(t):
    win = window(t)
    x0, y0, k = win
    src = A["orig"] if t < T_POWER - 0.05 else A["plate"]
    ww, wh = W / k, PANEL_H / k
    fr = np.array(np.asarray(src.resize((W, PANEL_H), Image.BICUBIC,
                                        box=(x0 * 2, y0 * 2, (x0 + ww) * 2, (y0 + wh) * 2)), np.float32) / 255)
    if t < T_POWER - 0.05:
        return fr, win
    floor_lights(fr, t, win)
    base = fr.copy()
    cx, cy, s, ang, fly = car_state(t)
    px, py = to_panel(win, cx, cy)
    cw = (CAR_BOX[2] - CAR_BOX[0]) * s * k
    ground = to_panel(win, CAR_C[0], CAR_BOX[3] - 4)

    # ground shadow + under-glow + cold-gas vapour bursts while hovering
    lift = 1 - prog(t, T_LIFT, T_LIFT + 0.8)
    if lift > 0:
        place(fr, A["shadow"], ground[0], ground[1], "mm", a=0.45 * lift, scale=k * 0.95)
        place(fr, A["under"], ground[0], ground[1] - 4, "mm", a=0.9 * prog(t, T_POWER, T_LIFT) * lift, scale=k, add=True)
    for V in A["vapors"]:
        u = t - V["t0"]
        if 0 < u < 0.9:
            vx = CAR_C[0] + (-70 if V["side"] == 0 else 60) + V["vx"] * u
            sx, sy = to_panel(win, vx, CAR_BOX[3] + 4 + 10 * u)
            place(fr, A["vapor"][V["k"]], sx, sy, "mm", a=0.75 * (1 - u / 0.9), scale=k * (0.5 + 1.4 * u))

    # light trail behind the car (also hides the cut-off rear)
    if T_LIFT - 0.1 < t < T_LAND + 0.4:
        for j in range(1, 46):
            tt = t - j * 0.012
            if tt < T_LIFT - 0.1:
                break
            hx, hy, hs, ha, hf = car_state(tt)
            hpx, hpy = to_panel(win, hx, hy)
            rx, ry = local(hpx, hpy, hs * k, ha, -(CAR_BOX[2] - CAR_BOX[0]) / 2 + 8, CAR_HGT * 0.08)
            fadej = (1 - j / 46) * hf * (1 - prog(t, T_ARRIVE, T_LAND + 0.3))
            place(fr, A["dot_big"], rx, ry, "mm", a=0.14 * fadej, scale=hs * k * (1 - j / 60), add=True)
            place(fr, A["dot"], rx, ry, "mm", a=0.32 * fadej, scale=hs * k * 1.2, add=True)
        for j, a in ((3, 0.18), (2, 0.25), (1, 0.32)):     # motion-blur ghosts (also for the flip)
            tt = t - j * 0.02
            if T_LIFT < tt and t < T_ARRIVE:
                hx, hy, hs, ha, hf = car_state(tt)
                gx, gy = to_panel(win, hx, hy)
                place(fr, car_layer(hs * k, ha, True), gx, gy, "mm", a=a)
    if fly > 0.01:
        place(fr, A["under"], px, py + CAR_HGT * s * k * 0.42, "mm", a=0.7 * fly, scale=s * k * 0.85, add=True)

    jets(fr, t, win, cx, cy, s, ang)
    place(fr, car_layer(s * k, ang, t > T_LIFT + 0.05), px, py, "mm")

    # rooftop: the parapet hides the wheels once landed
    if t > T_ARRIVE + 0.2:
        x_lo, x_hi = int(max(0, px - cw)), int(min(W, px + cw))
        if x_hi > x_lo:
            xs = np.arange(x_lo, x_hi)
            ry = (roof_y(xs / k + x0) - y0) * k
            m = (np.arange(PANEL_H)[:, None] > ry[None, :]).astype(np.float32)[..., None]
            fr[:, x_lo:x_hi] = fr[:, x_lo:x_hi] * (1 - m) + base[:, x_lo:x_hi] * m

    # take-off dust over the parking spot
    if t > T_LIFT - 0.15:
        u = t - (T_LIFT - 0.15)
        for P in A["puffs"]:
            uu = u - P["d"]
            if 0 < uu < 4.2:
                a = P["a"] * min(1, uu * 5) * max(0, 1 - (uu / 4.2) ** 1.6)
                sx, sy = to_panel(win, P["x"] + P["vx"] * uu, P["y"] + P["vy"] * uu)
                place(fr, A["smoke"][P["k"]], sx, sy, "mm", a=a, scale=k * (P["s0"] + 0.35 * uu))
    # landing: puff, neon sign lights up, flash, confetti
    if t > T_LAND - 0.05:
        u = t - (T_LAND - 0.05)
        ry0 = roof_y(LAND_X)
        for P in A["roofpuffs"]:
            if u < 1.4:
                sx, sy = to_panel(win, LAND_X + P["dx"] + P["vx"] * u, ry0 - 4 - 8 * u)
                place(fr, A["smoke"][P["k"]], sx, sy, "mm", a=0.7 * (1 - u / 1.4), scale=k * (P["s0"] + 0.25 * u))
        nx, ny = to_panel(win, *SIGN)
        neon = 0.25 + 0.75 * math.exp(-u * 1.8) * (0.6 + 0.4 * math.sin(u * 26) ** 2)
        place(fr, A["neon"], nx, ny + 8 * k, "mm", a=neon, scale=k * 0.85, add=True)
        fx, fy = to_panel(win, LAND_X, ry0)
        place(fr, A["flash"], fx, fy, "mm", a=0.9 * math.exp(-u * 5), scale=k * 0.7, add=True)
        for C in A["confetti"]:
            uc = u - C["d"]
            if 0 < uc < 2.2:
                cxp = LAND_X + C["vx"] * uc * 0.35
                cyp = ry0 - 10 + (C["vy"] * uc + 260 * uc * uc) * 0.35
                sx, sy = to_panel(win, cxp, cyp)
                tw = 0.55 + 0.45 * math.sin(uc * 14 + C["ph"])
                place(fr, A["spark"][C["k"]], sx, sy, "mm", a=tw * (1 - uc / 2.2), scale=k * 0.8, add=True)
    # speed lines while climbing
    sp = 0.6 * fade(t, T_LIFT + 0.3, T_TOP, 0.3, 0.4)
    if sp > 0:
        for L in A["lines"]:
            yy = (L["y"] + L["v"] * t) % (PANEL_H + 400) - 200
            xx = L["x"] - 0.35 * (yy - L["y"])
            x_a, x_b = int(xx), int(xx + 3)
            y_a, y_b = int(max(0, yy)), int(min(PANEL_H, yy + L["l"]))
            if y_b > y_a and 0 <= x_a < W - 3:
                fr[y_a:y_b, x_a:x_b] += L["a"] * sp
    # camera shake at take-off and on landing
    sh = math.exp(-max(0, t - T_LIFT) * 5) * (t > T_LIFT) + 0.6 * math.exp(-max(0, t - T_LAND) * 7) * (t > T_LAND)
    if sh > 0.02:
        dx, dy = int(7 * sh * math.sin(t * 90)), int(6 * sh * math.cos(t * 77))
        fr = np.roll(fr, (dy, dx), (0, 1))
    return fr, win


def overlay_panel(fr, t, win):
    """Floor counter, 360° tag, roof tag and voice-over subtitles over the photo window."""
    ft = A["floor_times"]
    n = sum(1 for tt, _ in ft if tt <= t)
    a = fade(t, T_LIFT - 0.3, TOTAL - 0.3, 0.3, 0.3)
    if a > 0:
        bx, by = W - 40, PANEL_Y + 40
        last = max([tt for tt, _ in ft if tt <= t], default=-9)
        pop = 1 + 0.25 * math.exp(-(t - last) * 9) if t - last < 0.6 else 1
        place(fr, A["counter_box"], bx, by, "rt", a=a)
        place(fr, A["arrow"], bx - 150, by + 48, "mm", a=a * (0.5 + 0.5 * math.sin(t * 9) ** 2 if t < T_LAND else 1))
        place(fr, A["counter"][n], bx - 72, by + 48, "mm", a=a, scale=pop)
    p360 = prog(t, (T_SPIN0 + T_SPIN1) / 2 - 0.15, (T_SPIN0 + T_SPIN1) / 2 + 0.2)
    if p360 > 0 and t < T_SPIN1 + 0.9:
        cx, cy, s, *_ = car_state(t)
        px, py = to_panel(win, cx, cy)
        place(fr, A["t360"], px - 220, PANEL_Y + py + 40, "mm", a=min(1, p360 * 3) * (1 - prog(t, T_SPIN1 + 0.5, T_SPIN1 + 0.9)),
              scale=lerp(1.8, 1, ease_back(p360)))
    pt = prog(t, T_LAND + 0.15, T_LAND + 0.6)
    if pt > 0:
        cx, cy, s, ang, fly = car_state(t)
        px, py = to_panel(win, cx, cy)
        box, txt = A["roof_tag"]
        y = PANEL_Y + py - 95
        sc = lerp(0.4, 1, ease_back(pt))
        place(fr, box, px, y, "mm", a=min(1, pt * 3), scale=sc)
        place(fr, txt, px, y, "mm", a=min(1, pt * 3), scale=sc)
    for L, (txt, box) in zip(A["vo"], A["subs"]):
        if L["start"] - 0.2 < t < L["end"] + 0.4:
            a2 = fade(t, L["start"] - 0.05, L["end"] + 0.25, 0.12, 0.15)
            y = PANEL_Y + PANEL_H - 62 + 6 * (1 - ease_out(prog(t, L["start"], L["start"] + 0.25)))
            place(fr, box, W / 2, y, "mm", a=a2)
            place(fr, txt, W / 2, y - 2, "mm", a=a2)


def caption(fr, t):
    ys = [150, 300, 425]
    gap = 26
    for row, y in zip(A["cap"], ys):
        total = sum(L.cw for L, _ in row) + gap * (len(row) - 1)
        x = W / 2 + total / 2
        for L, t0 in row:
            p = prog(t, t0, t0 + 0.35)
            if p > 0:
                sc = lerp(1.6, 1, ease_back(p))
                shim = shimmer_at(t, T_LAND + 0.1) if L is A["cap"][1][3][0] else None
                if L is A["cap"][0][1][0] and T_LIFT - 0.2 < t < T_LIFT + 0.6:
                    sc *= 1 + 0.12 * math.sin(math.pi * prog(t, T_LIFT - 0.2, T_LIFT + 0.6))
                place(fr, L, x - L.cw / 2, y, "mm", a=min(1, p * 3), scale=sc, shimmer=shim)
            x -= L.cw + gap


def shimmer_at(t, t0, dur=1.0):
    p = prog(t, t0, t0 + dur)
    return p if 0 < p < 1 else None


def bottom(fr, t):
    a = ease_out(prog(t, 0.6, 1.3))
    if a > 0:
        place(fr, A["b_res"], W / 2, 1478, "mm", a=a)
        place(fr, A["b_name"], W / 2 - 60, 1560, "mm", a=a, shimmer=shimmer_at(t, T_LAND + 0.3, 1.1))
        box, txt = A["b_r6"]
        bx = W / 2 - 60 + A["b_name"].cw / 2 + 30 + box.cw / 2
        bump = 1 + 0.2 * math.exp(-max(0, t - T_LAND) * 6) * (t > T_LAND)
        place(fr, box, bx, 1566, "mm", a=a, scale=bump)
        place(fr, txt, bx, 1566, "mm", a=a, scale=bump)
    call = VO_AT["call"]
    for k2, ((num, ic), L) in enumerate(zip(SCREEN["phones"], A["ph_text"])):
        p = prog(t, T_INFO + 0.18 * k2, T_INFO + 0.18 * k2 + 0.5)
        if p > 0:
            icon = A["ph_icons"][ic]
            wtot = icon.cw + 20 + L.cw
            x = W / 2 + wtot / 2
            y = 1665 + k2 * 74 + (1 - ease_out(p)) * 24
            pulse = 1 + 0.12 * math.exp(-max(0, t - call - 0.12 * k2) * 5) * (t > call + 0.12 * k2)
            place(fr, icon, x, y, "rm", a=ease_out(p), scale=pulse)
            place(fr, L, x - icon.cw - 20, y, "rm", a=ease_out(p), scale=pulse)
    place(fr, A["agency"], W / 2, 1880, "mm", a=ease_out(prog(t, 1.0, 1.6)))


def frame(t):
    fr = A["bg"].copy()
    p, win = panel(t)
    slide = ease_out(prog(t, 0.0, 0.5))
    fr[PANEL_Y:PANEL_Y + PANEL_H] = p * slide + fr[PANEL_Y:PANEL_Y + PANEL_H] * (1 - slide)
    for y in (PANEL_Y, PANEL_Y + PANEL_H):
        place(fr, g.hline(W, 3), W / 2, y, "mm", a=slide)
    overlay_panel(fr, t, win)
    caption(fr, t)
    bottom(fr, t)
    fl = math.exp(-max(0, t - T_LAND) * 7) * (t > T_LAND)
    if fl > 0.01:
        fr += fl * 0.25
    fr *= min(1, t / 0.35) * (1 - prog(t, TOTAL - 0.5, TOTAL))
    return (np.clip(fr, 0, 1) * 255 + 0.5).astype(np.uint8)


# ====================================================================== sound
def soundtrack(path):
    import audio as au
    from scipy.ndimage import maximum_filter1d, uniform_filter1d
    from scipy.signal import resample_poly
    SR = au.SR
    N = int(TOTAL * SR) + SR
    mus, fx, vo = np.zeros((N, 2)), np.zeros((N, 2)), np.zeros(N)
    t = np.arange(N) / SR

    def note(f, dur, kind="bass"):
        n = int(dur * SR)
        tt = np.arange(n) / SR
        if kind == "bass":
            sig = sum(np.sin(2 * np.pi * f * h * tt) / h ** 1.2 for h in range(1, 7))
            return au.filt(sig, "lowpass", 900) * np.exp(-tt * 3.5) * np.minimum(1, tt / 0.005)
        sig = sum(np.sin(2 * np.pi * f * h * tt + h) / h ** 1.5 for h in range(1, 5))
        return sig * au.env_adsr(n, 0.02, 0.2, 0.6, 0.3)

    clap_n = int(0.18 * SR)
    clap = au.filt(au.rng.standard_normal(clap_n), "bandpass", [900, 4000]) * np.exp(-np.arange(clap_n) / SR * 22)
    bass_seq = [40, 40, 36, 38]           # E2 E2 C2 D2 (one per bar)
    chords = [[64, 67, 71], [64, 67, 71], [60, 64, 67], [62, 66, 69]]
    end = TOTAL - 0.4
    # build-up
    au.add(mus, au.whoosh(T_LIFT, 0.98, up=True) * 0.6, 0.0, 0.5)
    for b in range(int(T_LIFT / (BEAT / 2))):
        tb = b * BEAT / 2
        au.add(mus, au.shaker(), tb, 0.03 + 0.04 * tb / T_LIFT, pan=0.3)
    for b in range(int(T_LIFT / (BEAT * 4)) + 1):
        for m in chords[b % 4]:
            au.add(mus, note(au.midi(m), BEAT * 4, "pad"), b * BEAT * 4, 0.025)
    n = int(1.6 * SR)
    tt = np.arange(n) / SR
    whine = np.sin(2 * np.pi * np.cumsum(200 + 1100 * (tt / 1.6) ** 2) / SR) * (tt / 1.6) ** 1.5
    au.add(fx, whine, T_POWER - 0.1, 0.11)
    # drop on take-off
    for b in range(int((end - T_LIFT) / BEAT)):
        tb = T_LIFT + b * BEAT
        au.add(mus, au.kick(), tb, 0.55)
        if b % 2 == 1:
            au.add(mus, clap, tb, 0.22)
        for h in (0, 0.5):
            au.add(mus, au.shaker(), tb + h * BEAT, 0.06 if h else 0.035, pan=-0.2)
        bi = (b // 4) % 4
        au.add(mus, note(au.midi(bass_seq[bi]), BEAT * 0.9), tb + 0.25 * BEAT * (b % 2), 0.22)
        if b % 4 == 0:
            for m in chords[bi]:
                au.add(mus, note(au.midi(m), BEAT * 4, "pad"), tb, 0.035)
    mus *= (1 - 0.3 * (t > T_LAND + 0.1))[:, None]
    # sound design
    for V in A["vapors"]:                                        # cold-gas "pssht"
        vn = int(0.22 * SR)
        burst = au.filt(au.rng.standard_normal(vn), "highpass", 2500) * np.exp(-np.arange(vn) / SR * 16)
        au.add(fx, burst, V["t0"], 0.09, pan=-0.3 if V["side"] == 0 else 0.3)
    au.add(fx, au.boom(), T_LIFT - 0.02, 0.6)
    jet_n = int((T_LAND + 0.4 - T_POWER) * SR)                   # jet roar following the jet power
    roar = au.filt(au.rng.standard_normal(jet_n), "bandpass", [180, 2600])
    env = np.array([jet_power(T_POWER + i / SR) + 0.5 * under_power(T_POWER + i / SR) for i in range(0, jet_n, 64)])
    env = np.interp(np.arange(jet_n), np.arange(0, jet_n, 64), env)
    au.add(fx, roar * env, T_POWER, 0.11)
    for tf, nfl in A["floor_times"]:                             # rising tick per floor
        f0 = au.midi(72 + [0, 2, 4, 5, 7, 9][min(5, nfl - 1)])
        au.add(fx, au.pop(f0 * 2, f0, 0.12), tf, 0.22, pan=0.4)
    sn = int((T_SPIN1 - T_SPIN0 + 0.5) * SR)                     # flip: fast swirling whoosh
    swirl = au.filt(au.rng.standard_normal(sn), "bandpass", [600, 5000]) * np.sin(np.linspace(0, np.pi, sn)) ** 1.5
    pan_l = 0.5 + 0.5 * np.sin(np.linspace(0, 4 * np.pi, sn))
    au.add(fx, np.stack([swirl * pan_l, swirl * (1 - pan_l)], 1) * 1.4, T_SPIN0 - 0.2, 0.2)
    au.add(fx, au.boom(), T_LAND - 0.02, 0.55)
    au.add(fx, au.chime(1318.5, 2.4), T_LAND + 0.05, 0.2)
    au.add(fx, au.chime(1760.0, 2.0), T_LAND + 0.35, 0.1)
    bz_n = int(0.6 * SR)                                         # neon sign buzz
    bz = np.sign(np.sin(2 * np.pi * 100 * np.arange(bz_n) / SR)) * np.exp(-np.arange(bz_n) / SR * 4)
    au.add(fx, au.filt(bz, "lowpass", 3000), T_LAND + 0.05, 0.03)
    for row in A["cap"]:
        for _, t0 in row:
            au.add(fx, au.pop(1300, 800, 0.07), t0, 0.08, pan=0.2)
    for k2 in range(3):
        au.add(fx, au.pop(1000, 600), T_INFO + 0.18 * k2, 0.12, pan=0.3)
    # voice-over (with a little presence) and ducking of the bed under it
    for L in A["vo"]:
        x, sr = sf.read(os.path.join(VO_DIR, L["file"]), dtype="float32")
        gg = math.gcd(SR, sr)
        y = resample_poly(x, SR // gg, sr // gg)
        act = np.abs(y) > 0.02 * np.abs(y).max()
        y = y * 0.13 / np.sqrt(np.mean(y[act] ** 2))
        i = int(L["start"] * SR)
        vo[i:i + len(y)] += y[:max(0, N - i)]
    vo = au.filt(vo, "highpass", 90)
    duck = np.clip(uniform_filter1d(np.abs(vo), 2400) / 0.03, 0, 1)
    duck = uniform_filter1d(maximum_filter1d(duck, 4800), 7200)          # hold through short pauses, smooth edges
    mus *= (1 - 0.55 * duck)[:, None]
    fx *= (1 - 0.35 * duck)[:, None]
    mix = au.reverb(mus, 1.6, 6000, 0.18) + au.reverb(fx, 1.4, 7000, 0.15) + np.stack([vo, vo], 1)
    mix *= np.clip((TOTAL - t) / 0.5, 0, 1)[:, None]
    mix = mix[: int(TOTAL * SR)]
    mix *= 10 ** (-1.0 / 20) / np.abs(mix).max()
    tmp = os.path.join(BUILD, "mix_pre.wav")
    sf.write(tmp, mix.astype(np.float32), SR, subtype="FLOAT")
    gain = -14.0 - au.integrated_loudness(tmp)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", tmp, "-af",
                    f"volume={gain:.2f}dB,alimiter=limit=0.84:attack=3:release=60:level=disabled",
                    "-c:a", "pcm_s16le", path], check=True)


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
    args = ap.parse_args()
    if not os.path.exists(os.path.join(BUILD, "car_sprite.npy")):
        subprocess.run(["python3", os.path.join(HERE, "sirene_plate.py")], check=True, cwd=HERE)
    if not os.path.exists(os.path.join(VO_DIR, "lines.json")):
        subprocess.run(["python3", os.path.join(HERE, "sirene_vo.py")], check=True, cwd=HERE)
    build()
    os.makedirs(os.path.join(BUILD, "preview"), exist_ok=True)
    if args.still:
        for t in args.still:
            Image.fromarray(frame(t)).save(os.path.join(BUILD, "preview", f"still_{t:05.2f}.png"))
        return
    n = int(round(TOTAL * FPS))
    k = os.cpu_count()
    with mp.get_context("fork").Pool(k) as pool:
        segs = pool.map(render_chunk, [(i, i * n // k, (i + 1) * n // k) for i in range(k)])
    lst = os.path.join(BUILD, "segments.txt")
    with open(lst, "w") as f:
        f.writelines(f"file '{s}'\n" for s in segs)
    silent = os.path.join(BUILD, "video_silent.mp4")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", silent],
                   check=True)
    wav = os.path.join(BUILD, "mix.wav")
    soundtrack(wav)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", silent, "-i", wav, "-map", "0:v", "-map", "1:a",
                    "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart",
                    "-metadata", "title=Résidence La Sirène R+6", OUT], check=True)
    print("done ->", OUT)


if __name__ == "__main__":
    main()
