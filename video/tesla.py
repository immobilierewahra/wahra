"""Trend video: the Tesla parked in the Résidence La Sirène render lifts off and flies up to the rooftop (R+6).

python3 tesla.py                -> output/sirene_tesla.mp4  (1080x1920, ~15 s, music + sound design, no voice)
python3 tesla.py --still 3 6 9  -> build/sirene/preview/still_*.png

The car is cut out of the render (sirene_plate.py -> build/sirene/car_sprite.npy + plate.png, the render
without the car), then animated over the clean plate. Needs opencv-python-headless for the cut-out.
"""
import argparse
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
OUT = os.path.join(HERE, "output", "sirene_tesla.mp4")
W, H, FPS = 1080, 1920, 30
TOTAL = 15.0
PANEL_Y, PANEL_H = 520, 900                   # photo window inside the vertical frame
SW, SH = 1488, 845                            # source render size
CAR_BOX = (0, 712, 260, 805)                  # where the car sits in the render
CAR_C = ((CAR_BOX[0] + CAR_BOX[2]) / 2, (CAR_BOX[1] + CAR_BOX[3]) / 2)
ROOF = ((670, 132), (1062, 104))              # top edge of the "la Sirène" band (the rooftop line)
FLOORS = [560, 495, 430, 365, 300, 235]       # car bottom above these -> R+1 .. R+6
SCREEN = {
    "phones": [("+216 20 026 026", "phone"), ("+216 25 684 686", "whatsapp"), ("+216 29 404 009", "whatsapp")],
    "agency": "IMMOBILIÈRE WAHRA",
}
TESLA_RED = (232, 33, 39)

# beats (seconds)
T_POWER, T_LIFT, T_ARRIVE, T_LAND, T_INFO = 2.6, 3.9, 8.7, 9.35, 10.2
LAND_X = 870
S_END = 0.5
A = {}


# ====================================================================== motion
def roof_y(x):
    (x0, y0), (x1, y1) = ROOF
    return y0 + (x - x0) * (y1 - y0) / (x1 - x0)


def bez(p, u):
    a, b, c, d = p
    return tuple((1 - u) ** 3 * a[k] + 3 * (1 - u) ** 2 * u * b[k] + 3 * (1 - u) * u ** 2 * c[k] + u ** 3 * d[k]
                 for k in range(2))


def climb_keys():
    """Car bottom (source px) over time: one floor per half beat at 120 BPM, then across to the landing spot."""
    h = CAR_BOX[3] - CAR_BOX[1]
    land_bottom = roof_y(LAND_X) + 6
    ks = [(T_LIFT, CAR_BOX[3] - 14)] + [(T_LIFT + 0.6 + 0.45 * k, f) for k, f in enumerate(FLOORS)]
    ks += [(T_LIFT + 0.6 + 0.45 * 5 + 0.9, 125), (T_ARRIVE, land_bottom - 70)]
    return ks


def interp(keys, t):
    for (t0, v0), (t1, v1) in zip(keys, keys[1:]):
        if t <= t1:
            u = prog(t, t0, t1)
            return lerp(v0, v1, u)
    return keys[-1][1]


def car_state(t):
    """Car centre (source px), scale, rotation (deg, + = nose up) and 'flying' amount at time t."""
    h = CAR_BOX[3] - CAR_BOX[1]
    land_cy = roof_y(LAND_X) + 6 - h * S_END / 2
    x, y = CAR_C
    s, ang, fly = 1.0, 0.0, 0.0
    t_top = T_LIFT + 0.6 + 0.45 * 5          # R+6 reached
    if t < T_LIFT:
        p = ease_io(prog(t, T_POWER, T_LIFT))
        y -= 14 * p
        x += 1.5 * math.sin(t * 47) * p
        ang = 0.8 * math.sin(t * 23) * p
        fly = 0.35 * p
    elif t < T_ARRIVE:
        s = lerp(1.0, 0.64, ease_out(prog(t, T_LIFT, t_top))) if t < t_top else lerp(0.64, S_END, ease_io(prog(t, t_top, T_ARRIVE)))
        bottom = interp(climb_keys(), t)
        # smooth the joints between half-beat segments a little
        bottom = 0.5 * bottom + 0.25 * interp(climb_keys(), t - 0.06) + 0.25 * interp(climb_keys(), t + 0.06)
        y = bottom - h * s / 2
        if t >= T_ARRIVE - 0.001:
            y = land_cy - 70
        x = lerp(CAR_C[0], 420, ease_io(prog(t, T_LIFT, t_top))) if t < t_top else \
            lerp(420, LAND_X, ease_io(prog(t, t_top, T_ARRIVE)))
        ang = 6 * (1 - prog(t, t_top - 0.5, t_top)) - 3 * fade(t, t_top, T_ARRIVE, 0.3, 0.5) + 4 * prog(t, T_ARRIVE - 0.4, T_ARRIVE)
        ang += 0.6 * math.sin(t * 9)
        fly = 1.0
    else:
        p = prog(t, T_ARRIVE, T_LAND)
        x, y = LAND_X, lerp(land_cy - 70, land_cy, ease_out(p))
        y -= 6 * math.sin(math.pi * prog(t, T_LAND, T_LAND + 0.35)) * (1 - prog(t, T_LAND, T_LAND + 0.35))
        s, ang = S_END, 4.0
        fly = 1 - prog(t, T_LAND, T_LAND + 0.6)
    return x, y, s, ang, fly


def floors_passed(t):
    x, y, s, ang, fly = car_state(t)
    bottom = y + (CAR_BOX[3] - CAR_BOX[1]) * s / 2
    return sum(1 for f in FLOORS if bottom < f) if t > T_LIFT else 0


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
        return (lerp(x, 700, 0.3), y + 40, lerp(1.6, 1.3, prog(tt, T_LIFT + 2.0, T_ARRIVE)))
    keys = [(0.0, (500, 422, 1.0)), (2.3, (520, 440, 1.06)), (3.3, (330, 600, 1.5)), (4.1, follow),
            (8.5, follow), (9.3, (860, 200, 1.55)), (11.4, (872, 160, 1.85)), (13.4, (800, 300, 1.3)),
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


# ====================================================================== assets
def glow_ellipse(w, h, color):
    yy, xx = np.mgrid[-h:h + 1, -w:w + 1].astype(np.float32)
    d = np.sqrt((xx / w) ** 2 + (yy / h) ** 2)
    L = g.from_mask(np.clip(1 - d, 0, 1) ** 1.6, color)
    L.pad = 0
    return L


def smoke_sprite(r, seed):
    rng = np.random.default_rng(seed)
    yy, xx = np.mgrid[-r:r + 1, -r:r + 1].astype(np.float32)
    d = np.sqrt(xx ** 2 + yy ** 2) / r
    n = Image.fromarray((rng.random((2 * r + 1, 2 * r + 1)) * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(r / 6))
    noise = np.asarray(n, np.float32) / 255
    m = np.clip(1 - d, 0, 1) ** 1.3 * (0.65 + 0.7 * (noise - 0.5) * 2)
    L = g.from_mask(np.clip(m, 0, 1), (196, 190, 182))
    L.pad = 0
    return L


def build():
    big = lambda im: im.resize((SW * 2, SH * 2), Image.LANCZOS).filter(ImageFilter.UnsharpMask(2, 70, 2))
    A["plate"] = big(Image.open(os.path.join(BUILD, "plate.png")).convert("RGB"))
    A["orig"] = big(Image.open(os.path.join(HERE, "assets", "sirene", "residence.jpg")).convert("RGB"))
    spr = np.load(os.path.join(BUILD, "car_sprite.npy"))
    rgba = spr.copy()
    rgba[..., :3] *= rgba[..., 3:4]
    A["car"] = rgba
    ramp = np.clip(np.arange(rgba.shape[1]) / 22.0, 0, 1)[None, :, None]     # soften the cut-off rear in flight
    faded = rgba * ramp
    A["car_faded"] = faded
    bg = Image.open(os.path.join(HERE, "assets", "sirene", "residence.jpg")).convert("RGB")
    s = max(W / SW, H / SH)
    bg = bg.resize((int(SW * s), int(SH * s)), Image.BILINEAR)
    bx = (bg.width - W) // 2
    bg = bg.crop((bx, 0, bx + W, H)).filter(ImageFilter.GaussianBlur(28))
    a = np.asarray(bg, np.float32) / 255 * 0.28
    yy = np.linspace(0, 1, H, dtype=np.float32)[:, None, None]
    A["bg"] = a * (1 - 0.3 * np.abs(yy - 0.5) * 2) + np.array([0.02, 0.025, 0.05], np.float32)
    A["under"] = glow_ellipse(150, 34, (90, 200, 255))
    A["dot"] = g.radial_sprite(14, (170, 225, 255), 1.6)
    A["dot_big"] = g.radial_sprite(40, (120, 200, 255), 1.8)
    A["flash"] = g.radial_sprite(160, (255, 240, 210), 1.4)
    A["shadow"] = glow_ellipse(140, 22, (0, 0, 0))
    A["smoke"] = [smoke_sprite(r, k) for k, r in enumerate((60, 75, 90, 70, 85))]
    rng = np.random.default_rng(5)
    A["puffs"] = [dict(x=rng.uniform(-20, 280), y=rng.uniform(735, 820), k=int(rng.integers(0, 5)),
                       vx=rng.uniform(-25, 35), vy=rng.uniform(-22, 4), s0=rng.uniform(0.6, 1.0),
                       d=rng.uniform(0.0, 0.25), a=rng.uniform(0.6, 0.9)) for _ in range(26)]
    A["puffs"] += [dict(x=rng.uniform(20, 200), y=rng.uniform(715, 750), k=int(rng.integers(0, 5)),
                        vx=rng.uniform(-10, 10), vy=rng.uniform(-8, 2), s0=rng.uniform(0.7, 0.9),
                        d=rng.uniform(0.05, 0.3), a=0.85) for _ in range(8)]
    A["roofpuffs"] = [dict(dx=rng.uniform(-90, 90), vx=rng.uniform(-60, 60), k=int(rng.integers(0, 5)),
                           s0=rng.uniform(0.25, 0.45)) for _ in range(9)]
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
    A["b_res"] = g.text("RÉSIDENCE", f(MO, 26, 600), color=g.CREAM, tracking=12, blur=4)
    A["b_name"] = g.text("La Sirène", f(PL, 92, 700), gold=True, blur=7)
    A["b_r6"] = pill_dark("R+6", f(MO, 40, 800))
    A["ph_icons"] = {"phone": g.icon_badge("phone", 58),
                     "whatsapp": g.icon_badge("whatsapp", 58, ring=None, fill=g.WA_GREEN, fill_alpha=1.0,
                                              icon_color=g.WHITE, icon_scale=0.62)}
    A["ph_text"] = [g.text(n, f(MO, 40, 600), blur=4) for n, _ in SCREEN["phones"]]
    A["agency"] = g.text(SCREEN["agency"], f(MO, 22, 700), gold=True, tracking=8, blur=3)
    A["floor_times"] = floor_times()


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


def car_layer(scale, ang, faded):
    arr = A["car_faded"] if faded else A["car"]
    im = Image.frombuffer("RGBa", (arr.shape[1], arr.shape[0]),
                          np.ascontiguousarray(np.clip(arr * 255 + 0.5, 0, 255).astype(np.uint8)).tobytes(),
                          "raw", "RGBa", 0, 1)
    w, h = max(2, round(arr.shape[1] * scale)), max(2, round(arr.shape[0] * scale))
    im = im.resize((w, h), Image.BICUBIC)
    if abs(ang) > 0.05:
        im = im.rotate(ang, resample=Image.BICUBIC, expand=True)
    return g.Layer(np.asarray(im, np.float32) / 255)


def panel(t):
    win = window(t)
    x0, y0, k = win
    src = A["orig"] if t < T_POWER - 0.05 else A["plate"]
    ww, wh = W / k, PANEL_H / k
    fr = np.array(np.asarray(src.resize((W, PANEL_H), Image.BICUBIC,
                                        box=(x0 * 2, y0 * 2, (x0 + ww) * 2, (y0 + wh) * 2)), np.float32) / 255)
    if t < T_POWER - 0.05:
        return fr, win
    base = fr.copy()
    cx, cy, s, ang, fly = car_state(t)
    px, py = to_panel(win, cx, cy)
    ch = (CAR_BOX[3] - CAR_BOX[1]) * s * k
    cw = (CAR_BOX[2] - CAR_BOX[0]) * s * k
    ground = to_panel(win, CAR_C[0], CAR_BOX[3] - 4)

    # ground shadow + under-glow while hovering / taking off
    lift = 1 - prog(t, T_LIFT, T_LIFT + 0.8)
    if lift > 0:
        place(fr, A["shadow"], ground[0], ground[1], "mm", a=0.45 * lift, scale=k * 0.95)
        place(fr, A["under"], ground[0], ground[1] - 4, "mm", a=0.9 * prog(t, T_POWER, T_LIFT) * lift, scale=k, add=True)

    # light trail behind the car (also hides the cut-off rear)
    if T_LIFT - 0.1 < t < T_LAND + 0.4:
        for j in range(1, 30):
            tt = t - j * 0.018
            if tt < T_LIFT - 0.1:
                break
            hx, hy, hs, ha, hf = car_state(tt)
            rx, ry = to_panel(win, hx - (CAR_BOX[2] - CAR_BOX[0]) * hs * 0.42, hy + 8 * hs)
            fadej = (1 - j / 30) * hf * (1 - prog(t, T_ARRIVE, T_LAND + 0.3))
            place(fr, A["dot_big"], rx, ry, "mm", a=0.2 * fadej, scale=hs * k * (1 - j / 40), add=True)
            place(fr, A["dot"], rx, ry, "mm", a=0.45 * fadej, scale=hs * k * 1.2, add=True)
        # motion-blur ghosts
        for j, a in ((3, 0.18), (2, 0.25), (1, 0.32)):
            tt = t - j * 0.02
            if tt > T_LIFT and t < T_ARRIVE:
                hx, hy, hs, ha, hf = car_state(tt)
                gx, gy = to_panel(win, hx, hy)
                place(fr, car_layer(hs * k, ha, True), gx, gy, "mm", a=a)
    # under-glow travelling with the car
    if fly > 0.01:
        place(fr, A["under"], px, py + ch * 0.42, "mm", a=0.8 * fly, scale=s * k * 0.85, add=True)

    # the car
    place(fr, car_layer(s * k, ang, t > T_LIFT + 0.05), px, py, "mm")

    # rooftop: the parapet hides the wheels once landed
    if t > T_ARRIVE + 0.2:
        x_lo, x_hi = int(max(0, px - cw)), int(min(W, px + cw))
        if x_hi > x_lo:
            xs = np.arange(x_lo, x_hi)
            ry = (roof_y(xs / k + x0) - y0) * k
            rows = np.arange(PANEL_H)[:, None]
            m = (rows > ry[None, :]).astype(np.float32)[..., None]
            fr[:, x_lo:x_hi] = fr[:, x_lo:x_hi] * (1 - m) + base[:, x_lo:x_hi] * m

    # take-off dust over the parking spot
    if t > T_LIFT - 0.15:
        u = t - (T_LIFT - 0.15)
        for P in A["puffs"]:
            uu = u - P["d"]
            if uu <= 0:
                continue
            a = P["a"] * min(1, uu * 5) * max(0, 1 - (uu / 4.2) ** 1.6)
            sx, sy = to_panel(win, P["x"] + P["vx"] * uu, P["y"] + P["vy"] * uu)
            place(fr, A["smoke"][P["k"]], sx, sy, "mm", a=a, scale=k * (P["s0"] + 0.35 * uu))
    # landing puff + flash
    if t > T_LAND - 0.05:
        u = t - (T_LAND - 0.05)
        ry0 = roof_y(LAND_X)
        for P in A["roofpuffs"]:
            sx, sy = to_panel(win, LAND_X + P["dx"] + P["vx"] * u, ry0 - 4 - 8 * u)
            place(fr, A["smoke"][P["k"]], sx, sy, "mm", a=0.7 * max(0, 1 - u / 1.4), scale=k * (P["s0"] + 0.25 * u))
        fl = math.exp(-u * 5)
        fx, fy = to_panel(win, LAND_X, ry0)
        place(fr, A["flash"], fx, fy, "mm", a=0.9 * fl, scale=k * 0.7, add=True)
    # speed lines while flying fast
    sp = 0.6 * fade(t, T_LIFT + 0.3, T_LIFT + 0.6 + 0.45 * 5, 0.3, 0.4)
    if sp > 0:
        for L in A["lines"]:
            yy = (L["y"] + L["v"] * t) % (PANEL_H + 400) - 200
            xx = L["x"] - 0.35 * (yy - L["y"])
            x_a, x_b = int(xx), int(xx + 3)
            y_a, y_b = int(max(0, yy)), int(min(PANEL_H, yy + L["l"]))
            if y_b > y_a and 0 <= x_a < W - 3:
                fr[y_a:y_b, x_a:x_b] += L["a"] * sp
    # camera shake at take-off
    sh = math.exp(-max(0, t - T_LIFT) * 5) * (t > T_LIFT)
    if sh > 0.02:
        dx, dy = int(7 * sh * math.sin(t * 90)), int(6 * sh * math.cos(t * 77))
        fr = np.roll(fr, (dy, dx), (0, 1))
    return fr, win


def overlay_panel(fr, t, win):
    """Counter + roof tag drawn inside the photo window (panel coordinates offset by PANEL_Y)."""
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
    pt = prog(t, T_LAND + 0.15, T_LAND + 0.6)
    if pt > 0:
        cx, cy, s, ang, fly = car_state(t)
        px, py = to_panel(win, cx, cy)
        box, txt = A["roof_tag"]
        y = PANEL_Y + py - 95
        sc = lerp(0.4, 1, ease_back(pt))
        place(fr, box, px, y, "mm", a=min(1, pt * 3), scale=sc)
        place(fr, txt, px, y, "mm", a=min(1, pt * 3), scale=sc)


def caption(fr, t):
    ys = [150, 300, 425]
    gap = 26
    for row, y in zip(A["cap"], ys):
        total = sum(L.cw for L, _ in row) + gap * (len(row) - 1)
        x = W / 2 + total / 2
        for L, t0 in row:
            p = prog(t, t0, t0 + 0.35)
            if p > 0:
                cxw = x - L.cw / 2
                sc = lerp(1.6, 1, ease_back(p))
                shim = None
                if L is A["cap"][1][3][0]:
                    shim = shimmer_at(t, T_LAND + 0.1)
                if L is A["cap"][0][1][0] and T_LIFT - 0.2 < t < T_LIFT + 0.6:
                    sc *= 1 + 0.12 * math.sin(math.pi * prog(t, T_LIFT - 0.2, T_LIFT + 0.6))
                place(fr, L, cxw, y, "mm", a=min(1, p * 3), scale=sc, shimmer=shim)
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
        place(fr, box, bx, 1566, "mm", a=a, scale=1 + 0.2 * math.exp(-max(0, t - T_LAND) * 6) * (t > T_LAND))
        place(fr, txt, bx, 1566, "mm", a=a, scale=1 + 0.2 * math.exp(-max(0, t - T_LAND) * 6) * (t > T_LAND))
    for k2, ((num, ic), L) in enumerate(zip(SCREEN["phones"], A["ph_text"])):
        p = prog(t, T_INFO + 0.18 * k2, T_INFO + 0.18 * k2 + 0.5)
        if p > 0:
            icon = A["ph_icons"][ic]
            wtot = icon.cw + 20 + L.cw
            x = W / 2 + wtot / 2
            y = 1665 + k2 * 74 + (1 - ease_out(p)) * 24
            place(fr, icon, x, y, "rm", a=ease_out(p))
            place(fr, L, x - icon.cw - 20, y, "rm", a=ease_out(p))
    place(fr, A["agency"], W / 2, 1880, "mm", a=ease_out(prog(t, 1.0, 1.6)))


def frame(t):
    fr = A["bg"].copy()
    p, win = panel(t)
    slide = ease_out(prog(t, 0.0, 0.5))
    fr[PANEL_Y:PANEL_Y + PANEL_H] = p * slide + fr[PANEL_Y:PANEL_Y + PANEL_H] * (1 - slide)
    for y in (PANEL_Y, PANEL_Y + PANEL_H):
        g_line = g.hline(W, 3)
        place(fr, g_line, W / 2, y, "mm", a=slide)
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
    SR = au.SR
    N = int(TOTAL * SR) + SR
    mus, fx = np.zeros((N, 2)), np.zeros((N, 2))
    bpm, beat = 120, 0.5
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
    drop, end = T_LIFT, TOTAL - 0.4
    # build-up
    au.add(mus, au.whoosh(T_LIFT, 0.98, up=True) * 0.6, 0.0, 0.5)
    for b in range(int(T_LIFT / (beat / 2))):
        tb = b * beat / 2
        au.add(mus, au.shaker(), tb, 0.03 + 0.04 * tb / T_LIFT, pan=0.3)
    n = int(1.4 * SR)
    tt = np.arange(n) / SR
    whine = np.sin(2 * np.pi * np.cumsum(200 + 1100 * (tt / 1.4) ** 2) / SR) * (tt / 1.4) ** 1.5
    au.add(fx, whine + 0.3 * np.sign(np.sin(2 * np.pi * 50 * tt)) * (tt / 1.4) * 0.2, T_POWER - 0.1, 0.12)
    # drop
    bar = 4 * beat
    nb = int((end - drop) / beat)
    for b in range(nb):
        tb = drop + b * beat
        au.add(mus, au.kick(), tb, 0.55)
        if b % 2 == 1:
            au.add(mus, clap, tb, 0.22)
        for h in (0, 0.5):
            au.add(mus, au.shaker(), tb + h * beat, 0.06 if h else 0.035, pan=-0.2)
        bi = (b // 4) % 4
        au.add(mus, note(au.midi(bass_seq[bi]), beat * 0.9), tb + 0.25 * beat * (b % 2), 0.22)
        if b % 4 == 0:
            for m in chords[bi]:
                au.add(mus, note(au.midi(m), bar, "pad"), tb, 0.035)
    calm = (t > T_LAND + 0.1)
    mus *= (1 - 0.35 * calm)[:, None]
    # sound design
    au.add(fx, au.boom(), T_LIFT - 0.02, 0.6)
    lift_n = int(1.2 * SR)
    thrust = au.filt(au.rng.standard_normal(lift_n), "lowpass", 1400) * np.exp(-np.arange(lift_n) / SR * 2.5)
    au.add(fx, thrust, T_LIFT - 0.05, 0.4)
    wind_n = int((T_ARRIVE - T_LIFT) * SR)
    wind = au.filt(au.rng.standard_normal(wind_n), "bandpass", [400, 2500]) * np.sin(np.linspace(0, np.pi, wind_n)) ** 0.8
    au.add(fx, wind, T_LIFT, 0.12)
    for k2, (tf, nfl) in enumerate(A["floor_times"]):
        au.add(fx, au.pop(au.midi(72 + [0, 2, 4, 5, 7, 9][min(5, nfl - 1)]) * 2, au.midi(72 + [0, 2, 4, 5, 7, 9][min(5, nfl - 1)]), 0.12),
               tf, 0.22, pan=0.4)
    au.add(fx, au.boom(), T_LAND - 0.02, 0.55)
    au.add(fx, au.chime(1318.5, 2.4), T_LAND + 0.05, 0.2)
    au.add(fx, au.chime(1760.0, 2.0), T_LAND + 0.35, 0.1)
    for row in A["cap"]:
        for _, t0 in row:
            au.add(fx, au.pop(1300, 800, 0.07), t0, 0.08, pan=0.2)
    for k2 in range(3):
        au.add(fx, au.pop(1000, 600), T_INFO + 0.18 * k2, 0.12, pan=0.3)
    mix = au.reverb(mus, 1.6, 6000, 0.18) + au.reverb(fx, 1.4, 7000, 0.15)
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
