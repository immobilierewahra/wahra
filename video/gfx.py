"""Drawing toolkit: premultiplied-alpha layers, Arabic text, gold fills, icons, logo, easing."""
import math
import os

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
FONTS = os.path.join(HERE, "assets", "fonts")

GOLD_STOPS = [(0.0, (250, 233, 180)), (0.45, (219, 181, 102)), (0.75, (190, 145, 70)), (1.0, (150, 108, 45))]
GOLD = (214, 176, 98)
GOLD_LIGHT = (240, 214, 150)
DARK = (22, 18, 15)
CREAM = (246, 240, 228)
WHITE = (255, 255, 255)
WA_GREEN = (37, 211, 102)


# ---------------------------------------------------------------- easing
def clamp01(x):
    return max(0.0, min(1.0, x))


def prog(t, a, b):
    return clamp01((t - a) / (b - a)) if b > a else float(t >= a)


def ease_out(x):
    return 1 - (1 - clamp01(x)) ** 3


def ease_in(x):
    return clamp01(x) ** 3


def ease_io(x):
    x = clamp01(x)
    return 4 * x ** 3 if x < 0.5 else 1 - (-2 * x + 2) ** 3 / 2


def ease_back(x, s=1.70158):
    x = clamp01(x) - 1
    return 1 + (s + 1) * x ** 3 + s * x ** 2


def ease_expo(x):
    x = clamp01(x)
    return 1 if x >= 1 else 1 - 2 ** (-10 * x)


def bounce(x):
    x = clamp01(x)
    n, d = 7.5625, 2.75
    if x < 1 / d:
        return n * x * x
    if x < 2 / d:
        x -= 1.5 / d
        return n * x * x + 0.75
    if x < 2.5 / d:
        x -= 2.25 / d
        return n * x * x + 0.9375
    x -= 2.625 / d
    return n * x * x + 0.984375


def fade(t, a, b, fi=0.35, fo=0.35):
    """1 inside [a, b] with fade-in/out ramps."""
    return min(prog(t, a, a + fi), 1 - prog(t, b - fo, b)) if fo else prog(t, a, a + fi)


def lerp(a, b, x):
    return a + (b - a) * x


# ---------------------------------------------------------------- layers
class Layer:
    """Premultiplied RGBA float32 image with a padding margin around its content box."""

    def __init__(self, arr, pad=0):
        self.a = arr.astype(np.float32)
        self.pad = pad
        self.h, self.w = arr.shape[:2]
        self._pil = None

    @property
    def cw(self):
        return self.w - 2 * self.pad

    @property
    def ch(self):
        return self.h - 2 * self.pad

    def scaled(self, s):
        if abs(s - 1) < 1e-3:
            return self
        if self._pil is None:
            buf = np.ascontiguousarray(np.clip(self.a * 255 + 0.5, 0, 255).astype(np.uint8))
            self._pil = Image.frombuffer("RGBa", (self.w, self.h), buf.tobytes(), "raw", "RGBa", 0, 1)
        w, h = max(1, round(self.w * s)), max(1, round(self.h * s))
        arr = np.asarray(self._pil.resize((w, h), Image.BICUBIC), dtype=np.float32) / 255
        return Layer(arr, self.pad * s)


def from_mask(mask, color=WHITE, gold=False):
    """mask: float array HxW in 0..1 -> Layer filled with a colour or the gold gradient."""
    h, w = mask.shape
    if gold:
        rgb = gold_gradient(h, w)
    else:
        rgb = np.empty((h, w, 3), np.float32)
        rgb[:] = np.array(color, np.float32) / 255
    out = np.empty((h, w, 4), np.float32)
    out[..., :3] = rgb * mask[..., None]
    out[..., 3] = mask
    return Layer(out)


def gold_gradient(h, w, stops=GOLD_STOPS):
    ys = np.linspace(0, 1, h)
    cols = np.stack([np.interp(ys, [s[0] for s in stops], [s[1][k] for s in stops]) for k in range(3)], -1) / 255
    return np.repeat(cols[:, None, :], w, 1).astype(np.float32)


def stack(*layers):
    """Composite same-size layers bottom to top."""
    out = layers[0].a.copy()
    for L in layers[1:]:
        a = L.a[..., 3:4]
        out = out * (1 - a) + L.a
    return Layer(out, layers[0].pad)


def with_shadow(L, blur=8, off=(0, 4), strength=0.55, glow=None):
    """Add a soft drop shadow (or coloured glow) below a layer. Needs pad >= blur*2."""
    alpha = Image.fromarray(np.clip(L.a[..., 3] * 255, 0, 255).astype(np.uint8))
    sh = np.asarray(alpha.filter(ImageFilter.GaussianBlur(blur)), np.float32) / 255
    sh = np.roll(sh, (off[1], off[0]), (0, 1)) * strength
    color = np.array(glow if glow else (0, 0, 0), np.float32) / 255
    base = np.zeros_like(L.a)
    base[..., :3] = color * sh[..., None]
    base[..., 3] = sh
    a = L.a[..., 3:4]
    return Layer(base * (1 - a) + L.a, L.pad)


def place(dst, L, x, y, anchor="lt", a=1.0, scale=1.0, reveal=None, rtl=True, soft=40, shimmer=None, add=False):
    """Composite layer L onto dst (HxWx3 float32).

    (x, y) refers to the content box point named by anchor: [l|m|r][t|m|b].
    reveal: 0..1 horizontal wipe (from the right when rtl). shimmer: 0..1 position of a light sweep.
    """
    if a <= 0.003 or (reveal is not None and reveal <= 0):
        return
    if scale != 1.0:
        L = L.scaled(scale)
    p = L.pad
    hx = {"l": 0, "m": 0.5, "r": 1}[anchor[0]]
    vy = {"t": 0, "m": 0.5, "b": 1}[anchor[1]]
    ox = int(round(x - p - hx * L.cw))
    oy = int(round(y - p - vy * L.ch))
    H, W = dst.shape[:2]
    x0, y0, x1, y1 = max(0, ox), max(0, oy), min(W, ox + L.w), min(H, oy + L.h)
    if x1 <= x0 or y1 <= y0:
        return
    src = L.a[y0 - oy:y1 - oy, x0 - ox:x1 - ox]
    k = np.float32(a)
    if reveal is not None and reveal < 1:
        cols = np.arange(x0 - ox, x1 - ox, dtype=np.float32)
        if rtl:
            cols = L.w - 1 - cols
        ramp = np.clip((reveal * (L.w + soft) - cols) / soft, 0, 1)[None, :, None]
        k = k * ramp
    rgb, al = src[..., :3], src[..., 3:4]
    if shimmer is not None and 0 < shimmer < 1:
        yy, xx = np.mgrid[y0 - oy:y1 - oy, x0 - ox:x1 - ox].astype(np.float32)
        pos = shimmer * (L.w + L.h) * 1.2 - L.h * 0.6
        band = np.exp(-((xx + yy * 0.6 - pos) / (L.h * 0.35)) ** 2)[..., None]
        rgb = rgb + (al - rgb) * band * 0.75
    d = dst[y0:y1, x0:x1]
    if not add:
        d *= 1 - al * k
    d += rgb * k


# ---------------------------------------------------------------- text
_font_cache = {}


def font(name, size, weight=None):
    key = (name, size, weight)
    if key not in _font_cache:
        f = ImageFont.truetype(os.path.join(FONTS, name), size, layout_engine=ImageFont.Layout.RAQM)
        if weight is not None:
            axes = f.get_variation_axes()
            f.set_variation_by_axes([weight] + [0] * (len(axes) - 1))
        _font_cache[key] = f
    return _font_cache[key]


def is_arabic(s):
    return any("؀" <= ch <= "ۿ" for ch in s)


def text_mask(text, fnt, tracking=0, pad=24):
    direction = "rtl" if is_arabic(text) else "ltr"
    probe = ImageDraw.Draw(Image.new("L", (1, 1)))
    if tracking and direction == "ltr":
        # manual letter spacing for latin caps
        parts, x = [], 0
        for ch in text:
            bb = probe.textbbox((0, 0), ch, font=fnt)
            parts.append((ch, x))
            x += probe.textlength(ch, font=fnt) + tracking
        x -= tracking
        asc, desc = fnt.getmetrics()
        bb_all = probe.textbbox((0, 0), "HÉÀ", font=fnt)
        top, bottom = bb_all[1], bb_all[3]
        w, h = int(math.ceil(x)), bottom - top
        img = Image.new("L", (w + 2 * pad, h + 2 * pad))
        d = ImageDraw.Draw(img)
        for ch, cx in parts:
            d.text((pad + cx, pad - top), ch, font=fnt, fill=255)
    else:
        bb = probe.textbbox((0, 0), text, font=fnt, direction=direction)
        w, h = bb[2] - bb[0], bb[3] - bb[1]
        img = Image.new("L", (w + 2 * pad, h + 2 * pad))
        ImageDraw.Draw(img).text((pad - bb[0], pad - bb[1]), text, font=fnt, fill=255, direction=direction)
    return np.asarray(img, np.float32) / 255


def text(txt, fnt, color=WHITE, gold=False, shadow=0.55, blur=7, off=(0, 3), tracking=0, glow=None):
    m = text_mask(txt, fnt, tracking=tracking, pad=max(24, blur * 3))
    L = from_mask(m, color, gold)
    L.pad = max(24, blur * 3)
    if shadow:
        L = with_shadow(L, blur=blur, off=off, strength=shadow, glow=glow)
    return L


# ---------------------------------------------------------------- shapes
def rounded_box(w, h, r, fill=DARK, alpha=0.75, border=None, bw=2, ss=3):
    img = Image.new("L", (w * ss, h * ss))
    ImageDraw.Draw(img).rounded_rectangle((0, 0, w * ss - 1, h * ss - 1), r * ss, fill=255)
    m = np.asarray(img.resize((w, h), Image.LANCZOS), np.float32) / 255
    L = from_mask(m * alpha, fill)
    if border:
        img = Image.new("L", (w * ss, h * ss))
        ImageDraw.Draw(img).rounded_rectangle((0, 0, w * ss - 1, h * ss - 1), r * ss, outline=255, width=bw * ss)
        bm = np.asarray(img.resize((w, h), Image.LANCZOS), np.float32) / 255
        L = stack(L, from_mask(bm, border, gold=(border == "gold")))
    return L


def gradient_rect(w, h, color, a0, a1, axis=0):
    """Rectangle whose alpha goes a0 -> a1 along axis (0 = top->bottom, 1 = left->right)."""
    n = h if axis == 0 else w
    ramp = np.linspace(a0, a1, n, dtype=np.float32)
    m = np.repeat(ramp[:, None], w, 1) if axis == 0 else np.repeat(ramp[None, :], h, 0)
    return from_mask(m, color)


def radial_sprite(r, color=GOLD_LIGHT, power=2.0):
    yy, xx = np.mgrid[-r:r + 1, -r:r + 1].astype(np.float32)
    d = np.sqrt(xx ** 2 + yy ** 2) / r
    m = np.clip(1 - d, 0, 1) ** power
    L = from_mask(m, color)
    L.pad = 0
    return L


# ---------------------------------------------------------------- icons (100-unit grid, 4x supersampled)
PHONE_PATH = ("M6.62 10.79c1.44 2.83 3.76 5.14 6.59 6.59l2.2-2.2c.27-.27.67-.36 1.02-.24 1.12.37 2.33.57 3.57.57"
              ".55 0 1 .45 1 1V20c0 .55-.45 1-1 1-9.39 0-17-7.61-17-17 0-.55.45-1 1-1h3.5c.55 0 1 .45 1 1 0 1.25.2 "
              "2.45.57 3.57.11.35.03.74-.25 1.02l-2.2 2.2z")


def svg_path(path, scale=1.0, offset=(0, 0), grow=1.0, steps=12):
    """Flatten a simple SVG path (M/L/H/V/C and relative forms, single subpath) to points."""
    import re
    toks = re.findall(r"[MLHVCZmlhvcz]|-?(?:\d+\.?\d*|\.\d+)", path)
    pts, cur, cmd, i = [], (0.0, 0.0), None, 0
    num = lambda: float(toks[i])
    while i < len(toks):
        if toks[i].isalpha():
            cmd = toks[i]
            i += 1
            if cmd in "zZ":
                continue
        rel = cmd.islower()
        c = cmd.upper()
        if c in "ML":
            x, y = float(toks[i]), float(toks[i + 1]); i += 2
            cur = (cur[0] + x, cur[1] + y) if rel else (x, y)
            pts.append(cur)
        elif c == "H":
            x = float(toks[i]); i += 1
            cur = (cur[0] + x if rel else x, cur[1]); pts.append(cur)
        elif c == "V":
            y = float(toks[i]); i += 1
            cur = (cur[0], cur[1] + y if rel else y); pts.append(cur)
        elif c == "C":
            v = [float(t) for t in toks[i:i + 6]]; i += 6
            if rel:
                v = [v[k] + cur[k % 2] for k in range(6)]
            p0, p1, p2, p3 = cur, (v[0], v[1]), (v[2], v[3]), (v[4], v[5])
            for k in range(1, steps + 1):
                t = k / steps
                a, b, cc, dd = (1 - t) ** 3, 3 * (1 - t) ** 2 * t, 3 * (1 - t) * t ** 2, t ** 3
                pts.append((a * p0[0] + b * p1[0] + cc * p2[0] + dd * p3[0], a * p0[1] + b * p1[1] + cc * p2[1] + dd * p3[1]))
            cur = p3
    cx = sum(p[0] for p in pts) / len(pts)
    cy = sum(p[1] for p in pts) / len(pts)
    return [((cx + (x - cx) * grow + offset[0]) * scale, (cy + (y - cy) * grow + offset[1]) * scale) for x, y in pts]


def _canvas(px, ss=4):
    S = px * ss
    img = Image.new("L", (S, S))
    return img, ImageDraw.Draw(img), (lambda *v: [c * S / 100 for c in v])


def _finish(img, px):
    return np.asarray(img.resize((px, px), Image.LANCZOS), np.float32) / 255


def icon_mask(name, px):
    img, d, u = _canvas(px)
    S = img.size[0]
    if name == "pin":
        d.ellipse(u(22, 8, 78, 64), fill=255)
        d.polygon(u(26, 48, 74, 48, 50, 94), fill=255)
        d.ellipse(u(38, 24, 62, 48), fill=0)
    elif name == "phone":
        pts = svg_path(PHONE_PATH, scale=100 / 24, offset=(-2, -2), grow=1.1)
        d.polygon([c for p in pts for c in u(*p)], fill=255)
    elif name == "whatsapp":
        d.ellipse(u(12, 10, 88, 86), outline=255, width=int(S * 0.07))
        d.polygon(u(14, 92, 20, 66, 36, 80), fill=255)
        sub = Image.fromarray((icon_mask("phone", px) * 255).astype(np.uint8)).resize((int(S * 0.46),) * 2, Image.LANCZOS)
        img.paste(255, (int(S * 0.27), int(S * 0.25)), sub)
    elif name == "sofa":
        d.rounded_rectangle(u(22, 22, 78, 58), S * 0.06, fill=255)
        d.rounded_rectangle(u(8, 42, 26, 78), S * 0.06, fill=255)
        d.rounded_rectangle(u(74, 42, 92, 78), S * 0.06, fill=255)
        d.rounded_rectangle(u(20, 56, 80, 76), S * 0.04, fill=255)
        d.rectangle(u(14, 76, 20, 88), fill=255)
        d.rectangle(u(80, 76, 86, 88), fill=255)
        d.line(u(27, 56, 73, 56), fill=0, width=int(S * 0.025))
    elif name == "shield":
        poly = [(50, 8), (84, 20), (84, 46)]
        for k in range(1, 21):
            s = k / 20
            poly.append((84 - 34 * s ** 1.3, 46 + 46 * s ** 0.8))
        poly += [(16 + 34 * s ** 1.3, 46 + 46 * s ** 0.8) for s in [k / 20 for k in range(20, 0, -1)]]
        poly += [(16, 46), (16, 20)]
        d.polygon([c for p in poly for c in u(*p)], fill=255)
        d.line(u(33, 50, 46, 63, 69, 36), fill=0, width=int(S * 0.08), joint="curve")
    elif name == "car":
        body = [(6, 66), (8, 52), (24, 46), (36, 30), (66, 30), (80, 46), (94, 52), (95, 66)]
        d.polygon([c for p in body for c in u(*p)], fill=255)
        d.polygon(u(39, 35, 49, 35, 49, 45, 31, 45), fill=0)
        d.polygon(u(53, 35, 64, 35, 73, 45, 53, 45), fill=0)
        for cx in (27, 73):
            d.ellipse(u(cx - 13, 54, cx + 13, 80), fill=0)
            d.ellipse(u(cx - 10, 57, cx + 10, 77), fill=255)
            d.ellipse(u(cx - 4, 63, cx + 4, 71), fill=0)
    elif name == "elevator":
        d.rounded_rectangle(u(16, 6, 84, 94), S * 0.06, outline=255, width=int(S * 0.06))
        d.polygon(u(30, 30, 40, 16, 50, 30), fill=255)
        d.polygon(u(54, 18, 74, 18, 64, 32), fill=255)
        d.rectangle(u(26, 40, 74, 86), fill=255)
        d.line(u(50, 40, 50, 86), fill=0, width=int(S * 0.04))
    elif name == "diamond":
        d.polygon(u(26, 24, 74, 24, 92, 42, 50, 90, 8, 42), fill=255)
        w = int(S * 0.03)
        d.line(u(8, 42, 92, 42), fill=0, width=w)
        d.line(u(36, 24, 28, 42, 50, 90, 72, 42, 64, 24), fill=0, width=w)
        d.line(u(28, 42, 50, 24, 72, 42), fill=0, width=w)
    elif name == "leaf":
        yy, xx = np.mgrid[0:S, 0:S].astype(np.float32) * 100 / S
        m = ((xx - 26) ** 2 + (yy - 74) ** 2 < 62 ** 2) & ((xx - 74) ** 2 + (yy - 26) ** 2 < 62 ** 2)
        img = Image.fromarray((m * 255).astype(np.uint8))
        d = ImageDraw.Draw(img)
        d.line(u(14, 86, 70, 30), fill=0, width=int(S * 0.04))
        d.line(u(10, 90, 30, 70), fill=255, width=int(S * 0.06))
    elif name == "key":
        d.ellipse(u(8, 30, 48, 70), fill=255)
        d.ellipse(u(18, 40, 38, 60), fill=0)
        d.rectangle(u(44, 44, 92, 56), fill=255)
        d.rectangle(u(72, 56, 80, 70), fill=255)
        d.rectangle(u(84, 56, 92, 66), fill=255)
    elif name == "check":
        d.line(u(14, 52, 40, 76, 86, 26), fill=255, width=int(S * 0.13), joint="curve")
    elif name == "chart":
        for k, (x, h) in enumerate([(14, 22), (36, 36), (58, 50)]):
            d.rectangle(u(x, 92 - h, x + 14, 92), fill=255)
        d.line(u(10, 62, 34, 42, 52, 52, 82, 20), fill=255, width=int(S * 0.07), joint="curve")
        d.polygon(u(92, 10, 90, 36, 66, 14), fill=255)
    elif name == "star8":
        c = 50
        for rot in (0, 45):
            pts = [(c + 44 * math.cos(math.radians(rot + 45 + 90 * k)), c + 44 * math.sin(math.radians(rot + 45 + 90 * k))) for k in range(4)]
            d.polygon([v for p in pts for v in u(*p)], fill=255)
        d.ellipse(u(38, 38, 62, 62), fill=0)
        d.ellipse(u(43, 43, 57, 57), fill=255)
    elif name == "building":
        d.rectangle(u(14, 34, 46, 92), fill=255)
        d.rectangle(u(50, 14, 86, 92), fill=255)
        for yy in range(22, 86, 13):
            d.rectangle(u(57, yy, 65, yy + 7), fill=0)
            d.rectangle(u(71, yy, 79, yy + 7), fill=0)
        for yy in range(42, 86, 13):
            d.rectangle(u(21, yy, 29, yy + 7), fill=0)
            d.rectangle(u(32, yy, 40, yy + 7), fill=0)
    else:
        raise KeyError(name)
    return _finish(img, px)


def icon_badge(name, px=64, ring="gold", fill=DARK, fill_alpha=0.85, icon_color=None, icon_scale=0.5):
    """Icon centred in a filled circle with a gold ring."""
    ss = 4
    S = px * ss
    base = Image.new("L", (S, S))
    ImageDraw.Draw(base).ellipse((0, 0, S - 1, S - 1), fill=255)
    disc = np.asarray(base.resize((px, px), Image.LANCZOS), np.float32) / 255
    ringimg = Image.new("L", (S, S))
    ImageDraw.Draw(ringimg).ellipse((ss, ss, S - 1 - ss, S - 1 - ss), outline=255, width=int(S * 0.035))
    ringm = np.asarray(ringimg.resize((px, px), Image.LANCZOS), np.float32) / 255
    ip = int(px * icon_scale)
    im = np.zeros((px, px), np.float32)
    o = (px - ip) // 2
    im[o:o + ip, o:o + ip] = icon_mask(name, ip)
    layers = [from_mask(disc * fill_alpha, fill)]
    if ring:
        layers.append(from_mask(ringm, gold=(ring == "gold"), color=ring if ring != "gold" else WHITE))
    layers.append(from_mask(im, icon_color or WHITE, gold=icon_color is None))
    L = stack(*layers)
    pad = 16
    arr = np.zeros((px + 2 * pad, px + 2 * pad, 4), np.float32)
    arr[pad:pad + px, pad:pad + px] = L.a
    return with_shadow(Layer(arr, pad), blur=6, off=(0, 3), strength=0.5)


# ---------------------------------------------------------------- logo
def emblem_mask(px):
    """Andalusian horseshoe arch inside an alfiz frame, with an eight-point star."""
    ss = 4
    S = px * ss
    img = Image.new("L", (S, S))
    d = ImageDraw.Draw(img)
    u = lambda *v: [c * S / 100 for c in v]
    w = int(S * 0.05)
    d.arc(u(22, 16, 78, 72), 148, 32, fill=255, width=w)
    for x in (26.3, 73.7):
        d.line(u(x, 58, x, 95), fill=255, width=w)
    w2 = int(S * 0.018)
    d.arc(u(29, 23, 71, 65), 150, 30, fill=255, width=w2)
    for x in (31.8, 68.2):
        d.line(u(x, 54, x, 95), fill=255, width=w2)
    d.rectangle(u(10, 4, 90, 96), outline=255, width=int(S * 0.025))
    d.line(u(4, 96, 96, 96), fill=255, width=int(S * 0.025))
    star = Image.fromarray((icon_mask("star8", int(S * 0.24)) * 255).astype(np.uint8))
    img.paste(255, (int(S * 0.38), int(S * 0.32)), star)
    return np.asarray(img.resize((px, px), Image.LANCZOS), np.float32) / 255


def emblem(px, shadow=True):
    L = from_mask(emblem_mask(px), gold=True)
    pad = 20
    arr = np.zeros((px + 2 * pad, px + 2 * pad, 4), np.float32)
    arr[pad:pad + px, pad:pad + px] = L.a
    L = Layer(arr, pad)
    return with_shadow(L, blur=8, off=(0, 3), strength=0.6) if shadow else L


def hline(w, thick=2, gold=True, taper=True):
    m = np.ones((thick, w), np.float32)
    if taper:
        x = np.linspace(-1, 1, w)
        m *= np.clip(1.6 * (1 - np.abs(x) ** 2.5), 0, 1)[None, :]
    L = from_mask(m, gold=gold)
    return L
