#!/usr/bin/env python3
"""Motion-graphics renderer for the Yessine Centre / El Wahra Immobilier promo.

Usage: render.py SRC.mp4 OUT_DIR [--preview t1,t2,...]
"""
import io, math, os, re, subprocess, sys
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont
import cairosvg

HERE = os.path.dirname(os.path.abspath(__file__))
A = os.path.join(HERE, "assets")
ICONS = os.path.join(HERE, "asr/node_modules/lucide-static/icons")

W, H, FPS = 1080, 1920, 30
SRC_W, SRC_H = 392, 850
SRC_DUR = 30.0
OUTRO = 3.5
DUR = SRC_DUR + OUTRO
WEB_T = 24.07          # screen-recording of the website starts here

GREEN = (18, 72, 48)
GREEN_D = (8, 38, 26)
GOLD = (214, 172, 92)
GOLD_L = (240, 210, 140)
CREAM = (250, 246, 236)
WHITE = (255, 255, 255)

CUTS = [4.654, 6.823, 7.740, 8.941, 11.594, 13.412, 15.581, 16.798, 17.733, 22.139]


def font(name, size):
    return ImageFont.truetype(os.path.join(A, name), size)


F_SUB = lambda s: font("montserrat-900.ttf", s)
F_BOLD = lambda s: font("montserrat-800.ttf", s)
F_SEMI = lambda s: font("montserrat-600.ttf", s)
F_MED = lambda s: font("montserrat-500.ttf", s)
F_SERIF = lambda s: font("playfair-display-900.ttf", s)


# ---------------------------------------------------------------- easing
def clamp(x, a=0.0, b=1.0):
    return max(a, min(b, x))


def prog(t, start, dur):
    return clamp((t - start) / dur)


def ease_out_cubic(x):
    return 1 - (1 - x) ** 3


def ease_in_out(x):
    return 3 * x * x - 2 * x * x * x


def ease_out_back(x, s=1.70158):
    x -= 1
    return x * x * ((s + 1) * x + s) + 1


def ease_out_elastic(x):
    if x <= 0 or x >= 1:
        return clamp(x)
    return 2 ** (-10 * x) * math.sin((x * 10 - 0.75) * (2 * math.pi / 3)) + 1


def window(t, a, b, fin=0.25, fout=0.25):
    """1 inside [a,b] with fades; returns (alpha, in-progress)."""
    if t < a or t > b:
        return 0.0
    return min(clamp((t - a) / fin), clamp((b - t) / fout))


# ---------------------------------------------------------------- assets
def icon(name, size, color=WHITE, stroke=2.0):
    svg = open(os.path.join(ICONS, name + ".svg")).read()
    svg = svg.replace("currentColor", "#%02x%02x%02x" % color)
    svg = re.sub(r'stroke-width="[\d.]+"', f'stroke-width="{stroke}"', svg)
    png = cairosvg.svg2png(bytestring=svg.encode(), output_width=size, output_height=size)
    return Image.open(io.BytesIO(png)).convert("RGBA")


def shadow_of(img, radius=18, opacity=0.55, spread=0):
    a = img.split()[-1]
    if spread:
        a = a.filter(ImageFilter.MaxFilter(spread * 2 + 1))
    sh = Image.new("RGBA", img.size, (0, 0, 0, 0))
    sh.putalpha(a.point(lambda v: int(v * opacity)))
    pad = radius * 3
    big = Image.new("RGBA", (img.width + 2 * pad, img.height + 2 * pad), (0, 0, 0, 0))
    big.paste(sh, (pad, pad))
    return big.filter(ImageFilter.GaussianBlur(radius)), pad


def rounded(size, r, fill):
    im = Image.new("RGBA", size, (0, 0, 0, 0))
    ImageDraw.Draw(im).rounded_rectangle([0, 0, size[0] - 1, size[1] - 1], r, fill=fill)
    return im


def gradient(size, c1, c2, vertical=True):
    w, h = size
    n = h if vertical else w
    ramp = np.linspace(0, 1, n)[:, None]
    cols = (np.array(c1)[None, :] * (1 - ramp) + np.array(c2)[None, :] * ramp).astype(np.uint8)
    if vertical:
        arr = np.repeat(cols[:, None, :], w, axis=1)
    else:
        arr = np.repeat(cols[None, :, :], h, axis=0)
    return Image.fromarray(arr, "RGB").convert("RGBA")


def gold_badge(icon_name, d):
    """Gold circle with white icon and a soft inner ring."""
    im = Image.new("RGBA", (d, d), (0, 0, 0, 0))
    g = gradient((d, d), GOLD_L, (176, 132, 58)).copy()
    mask = Image.new("L", (d, d), 0)
    ImageDraw.Draw(mask).ellipse([0, 0, d - 1, d - 1], fill=255)
    im.paste(g, (0, 0), mask)
    ImageDraw.Draw(im).ellipse([5, 5, d - 6, d - 6], outline=(255, 255, 255, 110), width=3)
    ic = icon(icon_name, int(d * 0.5), WHITE, 2.2)
    im.alpha_composite(ic, ((d - ic.width) // 2, (d - ic.height) // 2))
    return im


def make_logo(scale=1.0, dark_text=False):
    """Recreation of the El Wahra Immobilier wordmark: house mark + serif name."""
    s = scale
    mark_d = int(110 * s)
    mark = Image.new("RGBA", (mark_d, mark_d), (0, 0, 0, 0))
    ImageDraw.Draw(mark).rounded_rectangle([0, 0, mark_d - 1, mark_d - 1], int(26 * s),
                                           fill=GREEN, outline=GOLD, width=max(2, int(4 * s)))
    hi = icon("landmark", int(mark_d * 0.62), GOLD_L, 1.8)
    mark.alpha_composite(hi, ((mark_d - hi.width) // 2, (mark_d - hi.height) // 2 - int(2 * s)))
    t1 = "EL WAHRA"
    t2 = "I M M O B I L I E R"
    f1, f2 = F_SERIF(int(64 * s)), F_SEMI(int(22 * s))
    c1 = GREEN if dark_text else WHITE
    tmp = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    w1 = tmp.textbbox((0, 0), t1, font=f1)[2]
    w2 = tmp.textbbox((0, 0), t2, font=f2)[2]
    tw = max(w1, w2)
    im = Image.new("RGBA", (mark_d + int(26 * s) + tw + 4, mark_d), (0, 0, 0, 0))
    im.alpha_composite(mark, (0, 0))
    d = ImageDraw.Draw(im)
    x = mark_d + int(26 * s)
    d.text((x, int(-4 * s)), t1, font=f1, fill=c1)
    d.text((x + 2, int(76 * s)), t2, font=f2, fill=GOLD)
    return im


# ---------------------------------------------------------------- subtitles
# (text, start, end, [word start times or None])
SUBS = [
    ("Médecin, ingénieur, avocat,", 0.12, 1.72, [0.12, 0.62, 1.16]),
    ("architecte, société ou porteur de projet ?", 1.72, 3.86, [1.72, 2.26, 2.62, 2.96, 3.12, 3.28]),
    ("Cette vidéo est pour vous !", 3.86, 4.70, [3.86, 4.0, 4.14, 4.36, 4.52]),
    ("Vous cherchez un espace", 4.82, 7.86, [4.82, 5.46, 6.10, 6.88]),
    ("à la hauteur de vos ambitions ?", 8.04, 11.56, [8.04, 8.48, 8.78, 9.40, 10.10, 10.74]),
    ("Emplacement stratégique", 11.76, 13.14, [11.76, 12.60]),
    ("à Radès : Yessine Centre", 13.14, 14.20, [13.14, 13.28, 13.30, 13.64, 13.96]),
    ("met à votre disposition", 14.30, 15.24, [14.30, 14.56, 14.76, 14.90]),
    ("des locaux commerciaux", 15.24, 16.26, [15.24, 15.40, 15.60]),
    ("et des espaces professionnels", 16.26, 17.60, [16.26, 16.42, 16.66, 16.92]),
    ("modernes et haut standing.", 17.60, 19.36, [17.60, 18.10, 18.20, 18.60]),
    ("Vous trouverez aussi des S+1,", 19.50, 21.14, [19.50, 19.70, 19.90, 20.10, 20.66]),
    ("des S+2 et même des S+3 !", 21.14, 23.80, [21.14, 21.48, 22.34, 22.46, 22.80, 22.96]),
    ("Photos, vidéos, plans…", 24.06, 26.26, [24.06, 24.78, 25.60]),
    ("tout est sur le site El Wahra Immobilier.", 26.26, 28.84, [26.26, 26.54, 26.84, 27.0, 27.34, 27.68, 27.88, 28.2]),
]

HILITE = {"S+1", "S+2", "S+3", "RADÈS", "YESSINE", "CENTRE", "VOUS", "WAHRA", "IMMOBILIER",
          "STRATÉGIQUE", "HAUT", "STANDING", "BIENVENUE", "AMBITIONS", "COMMERCIAUX", "PROFESSIONNELS"}


class Subtitles:
    def __init__(self):
        self.font = F_SUB(66)
        self.lines = []
        tmp = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
        for text, a, b, wt in SUBS:
            words = re.sub(r" ([?!:;])", "\u00a0\\1", text.upper()).split(" ")
            times = list(wt or [])
            while len(times) < len(words):
                last = times[-1] if times else a
                times.append(min(b - 0.1, last + 0.18))
            # wrap into rows of max width
            rows, cur = [], []
            for w in words:
                test = " ".join(cur + [w])
                if cur and tmp.textbbox((0, 0), test, font=self.font)[2] > 900:
                    rows.append(cur)
                    cur = [w]
                else:
                    cur.append(w)
            rows.append(cur)
            self.lines.append((rows, times, a, b))

    def draw(self, canvas, t, cy):
        for rows, times, a, b in self.lines:
            if not (a - 0.05 <= t <= b + 0.15):
                continue
            fade = clamp((b + 0.15 - t) / 0.15)
            idx = 0
            layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
            d = ImageDraw.Draw(layer)
            line_h = 84
            y0 = cy - (len(rows) * line_h) // 2
            for r, row in enumerate(rows):
                widths = [d.textbbox((0, 0), w, font=self.font)[2] for w in row]
                space = 20
                total = sum(widths) + space * (len(row) - 1)
                x = (W - total) // 2
                y = y0 + r * line_h
                for w, ww in zip(row, widths):
                    ts = times[idx]
                    idx += 1
                    p = prog(t, ts, 0.18)
                    if p <= 0:
                        x += ww + space
                        continue
                    sc = 0.6 + 0.4 * ease_out_back(p)
                    active = ts <= t < (times[idx] if idx < len(times) else b + 1)
                    key = re.sub(r"[^\wÀ-ÿ+]", "", w)
                    col = GOLD_L if (key in HILITE or active) else WHITE
                    # draw word on its own tile so it can scale
                    tile = Image.new("RGBA", (ww + 40, line_h + 40), (0, 0, 0, 0))
                    td = ImageDraw.Draw(tile)
                    td.text((20, 18), w, font=self.font, fill=col, stroke_width=7, stroke_fill=(10, 20, 14))
                    if sc != 1:
                        tile = tile.resize((max(1, int(tile.width * sc)), max(1, int(tile.height * sc))), Image.BICUBIC)
                    al = clamp(p * 2) * fade
                    if al < 1:
                        tile.putalpha(tile.split()[-1].point(lambda v: int(v * al)))
                    cx_w = x + ww // 2
                    layer.alpha_composite(tile, (int(cx_w - tile.width / 2), int(y + line_h / 2 - tile.height / 2 + (1 - p) * 20)))
                    x += ww + space
            sh = layer.split()[-1].filter(ImageFilter.GaussianBlur(10)).point(lambda v: int(v * 0.6))
            shl = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
            shl.putalpha(sh)
            canvas.alpha_composite(shl, (0, 8))
            canvas.alpha_composite(layer)


# ---------------------------------------------------------------- scene graphics
class Graphics:
    def __init__(self):
        self.prof = [("stethoscope", "Médecin", 0.12), ("hard-hat", "Ingénieur", 0.62),
                     ("scale", "Avocat", 1.16), ("drafting-compass", "Architecte", 1.72),
                     ("building-2", "Société", 2.26), ("rocket", "Projet", 3.28)]
        self.prof_badges = [gold_badge(i, 132) for i, _, _ in self.prof]
        self.need_items = [("briefcase", "Bureaux", 5.3), ("stethoscope", "Cabinets", 6.1), ("store", "Commerces", 6.9)]
        self.need_badges = [gold_badge(i, 120) for i, _, _ in self.need_items]
        self.pin = icon("map-pin", 96, GOLD_L, 2.2)
        self.logo_small = make_logo(0.55)
        self.logo_big = make_logo(1.15)
        self.star = icon("star", 70, GOLD_L, 2.0)
        self.star_fill = self._filled_star(70)
        self.sparkles = icon("sparkles", 80, GOLD_L, 2.0)
        self.feat = [("store", "Locaux commerciaux", 15.24), ("briefcase", "Espaces professionnels", 16.42)]
        self.feat_cards = [self._card(i, txt) for i, txt, _ in self.feat]
        self.web_chips = [("camera", "Photos", 24.06), ("video", "Vidéos", 24.78), ("layout-grid", "Plans", 25.6)]
        self.web_chip_imgs = [self._chip(i, t) for i, t, _ in self.web_chips]
        self.globe = icon("globe", 44, GREEN, 2.4)
        self.cal = icon("calendar-check", 48, GREEN_D, 2.4)
        self.house = icon("bed-double", 64, WHITE, 2.0)

    def _filled_star(self, s):
        svg = open(os.path.join(ICONS, "star.svg")).read().replace('fill="none"', 'fill="#%02x%02x%02x"' % GOLD_L)
        svg = svg.replace("currentColor", "#%02x%02x%02x" % GOLD_L)
        return Image.open(io.BytesIO(cairosvg.svg2png(bytestring=svg.encode(), output_width=s, output_height=s))).convert("RGBA")

    def _card(self, icon_name, text):
        f = F_BOLD(44)
        tw = ImageDraw.Draw(Image.new("RGBA", (1, 1))).textbbox((0, 0), text, font=f)[2]
        w, h = tw + 190, 130
        im = rounded((w, h), 36, (10, 40, 27, 225))
        ImageDraw.Draw(im).rounded_rectangle([0, 0, w - 1, h - 1], 36, outline=GOLD + (255,), width=3)
        b = gold_badge(icon_name, 92)
        im.alpha_composite(b, (20, (h - 92) // 2))
        ImageDraw.Draw(im).text((132, h // 2), text, font=f, fill=WHITE, anchor="lm")
        return im

    def _chip(self, icon_name, text):
        f = F_BOLD(40)
        tw = ImageDraw.Draw(Image.new("RGBA", (1, 1))).textbbox((0, 0), text, font=f)[2]
        w, h = tw + 120, 92
        im = rounded((w, h), 46, CREAM + (255,))
        ic = icon(icon_name, 46, GREEN, 2.4)
        im.alpha_composite(ic, (26, (h - 46) // 2))
        ImageDraw.Draw(im).text((86, h // 2), text, font=f, fill=GREEN, anchor="lm")
        return im

    # -- helpers
    @staticmethod
    def put(canvas, img, cx, cy, scale=1.0, alpha=1.0, shadow=True):
        if alpha <= 0.01 or scale <= 0.01:
            return
        if scale != 1.0:
            img = img.resize((max(1, int(img.width * scale)), max(1, int(img.height * scale))), Image.BICUBIC)
        if alpha < 1:
            img = img.copy()
            img.putalpha(img.split()[-1].point(lambda v: int(v * alpha)))
        if shadow:
            sh, pad = shadow_of(img, 14, 0.5)
            canvas.alpha_composite(sh, (int(cx - img.width / 2 - pad), int(cy - img.height / 2 - pad + 10)))
        canvas.alpha_composite(img, (int(cx - img.width / 2), int(cy - img.height / 2)))

    def text(self, canvas, s, f, cx, cy, fill=WHITE, alpha=1.0, stroke=0, anchor="mm", spacing=0):
        layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
        d = ImageDraw.Draw(layer)
        if spacing:
            widths = [d.textbbox((0, 0), ch, font=f)[2] for ch in s]
            total = sum(widths) + spacing * (len(s) - 1)
            x = cx - total / 2
            for ch, w in zip(s, widths):
                d.text((x, cy), ch, font=f, fill=fill + (int(255 * alpha),), anchor="lm",
                       stroke_width=stroke, stroke_fill=(0, 0, 0, int(200 * alpha)))
                x += w + spacing
        else:
            d.text((cx, cy), s, font=f, fill=fill + (int(255 * alpha),), anchor=anchor,
                   stroke_width=stroke, stroke_fill=(0, 0, 0, int(200 * alpha)))
        canvas.alpha_composite(layer)

    # -- scenes
    def professions(self, c, t):
        a = window(t, 0.0, 4.55, 0.1, 0.35)
        if a <= 0:
            return
        for i, ((_, label, ts), b) in enumerate(zip(self.prof, self.prof_badges)):
            p = prog(t, ts, 0.45)
            if p <= 0:
                continue
            side = -1 if i % 2 == 0 else 1
            cx = W / 2 + side * 375 + side * (1 - ease_out_cubic(p)) * 200
            cy = 760 + (i // 2) * 250
            s = ease_out_back(p, 2.2)
            self.put(c, b, cx, cy, s, a)
            self.text(c, label.upper(), F_BOLD(32), cx, cy + 96, WHITE, a * clamp(p * 2), stroke=4)

    def need(self, c, t):
        a = window(t, 5.0, 11.3, 0.2, 0.35)
        if a <= 0:
            return
        for i, ((_, label, ts), b) in enumerate(zip(self.need_items, self.need_badges)):
            p = prog(t, ts, 0.45)
            if p <= 0:
                continue
            cx = W / 2 + (i - 1) * 300
            cy = 1190
            bob = math.sin((t - ts) * 2.4 + i) * 6
            self.put(c, b, cx, cy + bob, ease_out_back(p, 2.0), a)
            self.text(c, label.upper(), F_BOLD(34), cx, cy + 100 + bob, WHITE, a * clamp(p * 2), stroke=4)

    def title_card(self, c, t):
        a = window(t, 11.62, 14.25, 0.05, 0.3)
        if a <= 0:
            return
        # dark band
        p = ease_out_cubic(prog(t, 11.62, 0.5))
        band_h = int(330 * p)
        if band_h > 2:
            band = gradient((W, band_h), (8, 38, 26), (14, 60, 40))
            band.putalpha(int(215 * a))
            c.alpha_composite(band, (0, 1080 - band_h // 2))
            ImageDraw.Draw(c).rectangle([0, 1080 - band_h // 2, int(W * p), 1080 - band_h // 2 + 5], fill=GOLD + (int(255 * a),))
            ImageDraw.Draw(c).rectangle([W - int(W * p), 1080 + band_h // 2 - 5, W, 1080 + band_h // 2], fill=GOLD + (int(255 * a),))
        # letters reveal
        title = "YESSINE CENTRE"
        f = F_SERIF(112)
        d = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
        widths = [d.textbbox((0, 0), ch, font=f)[2] for ch in title]
        total = sum(widths)
        x = W / 2 - total / 2
        layer = Image.new("RGBA", c.size, (0, 0, 0, 0))
        ld = ImageDraw.Draw(layer)
        for i, (ch, w) in enumerate(zip(title, widths)):
            pp = ease_out_back(prog(t, 11.9 + i * 0.04, 0.4))
            if pp > 0:
                ld.text((x, 1040 + (1 - pp) * 50), ch, font=f, fill=WHITE + (int(255 * a * clamp(pp)),), anchor="lm")
            x += w
        c.alpha_composite(layer)
        # pin + location
        pp = prog(t, 12.6, 0.6)
        if pp > 0:
            drop = (1 - ease_out_elastic(pp)) * -120
            self.put(c, self.pin, W / 2 - 320, 1150 + drop, 0.7, a, shadow=False)
            self.text(c, "RADÈS · BEN AROUS", F_BOLD(44), W / 2 + 40, 1150, GOLD_L, a * clamp(pp * 2), spacing=4)

    def features(self, c, t):
        a = window(t, 15.1, 17.65, 0.1, 0.3)
        if a <= 0:
            return
        for i, ((_, _, ts), card) in enumerate(zip(self.feat, self.feat_cards)):
            p = ease_out_back(prog(t, ts - 0.1, 0.55), 1.2)
            if p <= 0:
                continue
            side = -1 if i == 0 else 1
            cx = W / 2 + side * (1 - p) * 900
            self.put(c, card, cx, 1130 + i * 170, 1.0, a)

    def standing(self, c, t):
        a = window(t, 17.6, 19.45, 0.15, 0.3)
        if a <= 0:
            return
        p0 = ease_out_cubic(prog(t, 17.6, 0.4))
        panel = rounded((720, 230), 40, (10, 40, 27, 215))
        ImageDraw.Draw(panel).rounded_rectangle([0, 0, 719, 229], 40, outline=GOLD + (255,), width=3)
        self.put(c, panel, W / 2, 1190, 0.85 + 0.15 * p0, a * p0)
        for i in range(5):
            p = prog(t, 17.8 + i * 0.12, 0.35)
            if p > 0:
                self.put(c, self.star_fill, W / 2 + (i - 2) * 100, 1140, ease_out_back(p, 3), a, shadow=False)
        pt = prog(t, 18.3, 0.4)
        self.text(c, "HAUT STANDING", F_BOLD(54), W / 2, 1240, WHITE, a * pt, spacing=6)
        # sparkles twinkle
        for k, (sx, sy) in enumerate([(220, 1080), (870, 1100), (830, 1290)]):
            tw = 0.5 + 0.5 * math.sin(t * 7 + k * 2)
            self.put(c, self.sparkles, sx, sy, 0.5 + 0.2 * tw, a * p0 * (0.4 + 0.6 * tw), shadow=False)

    def apartments(self, c, t):
        a = window(t, 19.5, 23.95, 0.2, 0.25)
        if a <= 0:
            return
        p0 = ease_out_cubic(prog(t, 19.5, 0.45))
        self.text(c, "APPARTEMENTS", F_BOLD(58), W / 2, 960 - (1 - p0) * 40, WHITE, a * p0, stroke=5, spacing=8)
        ImageDraw.Draw(c).rectangle([W / 2 - 160 * p0, 1005, W / 2 + 160 * p0, 1011], fill=GOLD + (int(255 * a),))
        for i, (lab, ts) in enumerate([("S+1", 20.66), ("S+2", 21.48), ("S+3", 22.96)]):
            p = prog(t, ts, 0.5)
            if p <= 0:
                continue
            tile = Image.new("RGBA", (240, 240), (0, 0, 0, 0))
            g = gradient((240, 240), GOLD_L, (170, 126, 52))
            m = Image.new("L", (240, 240), 0)
            ImageDraw.Draw(m).rounded_rectangle([0, 0, 239, 239], 44, fill=255)
            tile.paste(g, (0, 0), m)
            td = ImageDraw.Draw(tile)
            td.rounded_rectangle([8, 8, 231, 231], 38, outline=(255, 255, 255, 120), width=3)
            tile.alpha_composite(self.house, (88, 34))
            td.text((120, 160), lab, font=F_SUB(76), fill=GREEN_D, anchor="mm")
            pulse = 1 + 0.04 * math.sin((t - ts) * 6) * clamp(1 - (t - ts) / 1.5)
            self.put(c, tile, W / 2 + (i - 1) * 290, 1175, ease_out_back(p, 2.4) * pulse, a)

    def corner_logo(self, c, t):
        a = window(t, 0.6, WEB_T - 0.2, 0.5, 0.3)
        if a <= 0:
            return
        p = ease_out_cubic(prog(t, 0.6, 0.6))
        img = self.logo_small
        pill = rounded((img.width + 44, img.height + 30), (img.height + 30) // 2, (8, 38, 26, 190))
        pill.alpha_composite(img, (22, 15))
        self.put(c, pill, 50 + pill.width / 2 - (1 - p) * 500, 78, 0.9, a)


# ---------------------------------------------------------------- frame source
class Source:
    def __init__(self, path):
        self.proc = subprocess.Popen(
            ["ffmpeg", "-v", "error", "-i", path, "-vf", f"fps={FPS}", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
            stdout=subprocess.PIPE)
        self.last = None

    def next(self):
        buf = self.proc.stdout.read(SRC_W * SRC_H * 3)
        if len(buf) == SRC_W * SRC_H * 3:
            self.last = Image.fromarray(np.frombuffer(buf, np.uint8).reshape(SRC_H, SRC_W, 3), "RGB")
        return self.last


def camera_frame(src, t):
    """Fill 1080x1920 from the letterboxed 9:16 content, Ken Burns + punch-in at cuts."""
    content = src.crop((0, 77, SRC_W, 773))  # 392x696 ≈ 9:16
    prev = max([0.0] + [c for c in CUTS if c <= t])
    nxt = min([c for c in CUTS if c > t] + [WEB_T])
    seg = max(0.5, nxt - prev)
    kb = 1.0 + 0.07 * ((t - prev) / seg)
    punch = 0.10 * (1 - ease_out_cubic(prog(t, prev, 0.35))) if prev > 0 else 0
    z = kb + punch
    cw, ch = content.width / z, content.height / z
    # gentle drift alternating direction per scene
    k = CUTS.index(prev) if prev in CUTS else -1
    dx = (1 if k % 2 else -1) * (content.width - cw) * 0.3 * ((t - prev) / seg)
    x0 = (content.width - cw) / 2 + dx
    y0 = (content.height - ch) / 2
    img = content.resize((W, H), Image.LANCZOS, box=(x0, y0, x0 + cw, y0 + ch))
    img = img.filter(ImageFilter.UnsharpMask(radius=2, percent=70, threshold=2))
    return img.convert("RGBA")


def vignette():
    yy, xx = np.mgrid[0:H, 0:W]
    r = np.sqrt(((xx - W / 2) / (W * 0.75)) ** 2 + ((yy - H / 2) / (H * 0.7)) ** 2)
    a = np.clip((r - 0.55) * 1.2, 0, 1) * 170
    # extra bottom/top darkening for text legibility
    a += np.clip((yy - H * 0.62) / (H * 0.38), 0, 1) * 120
    a += np.clip((H * 0.12 - yy) / (H * 0.12), 0, 1) * 90
    a = np.clip(a, 0, 220).astype(np.uint8)
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    im.putalpha(Image.fromarray(a, "L"))
    return im


class Branded:
    """Green branded background with drifting gold particles."""

    def __init__(self):
        self.bg = gradient((W, H), (16, 70, 46), (5, 26, 18))
        glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        ImageDraw.Draw(glow).ellipse([-300, -200, W + 300, 900], fill=GOLD + (60,))
        self.bg.alpha_composite(glow.filter(ImageFilter.GaussianBlur(160)))
        rng = np.random.default_rng(7)
        self.parts = [(rng.uniform(0, W), rng.uniform(0, H), rng.uniform(2, 7), rng.uniform(15, 60), rng.uniform(0, 6.28))
                      for _ in range(45)]
        # subtle diagonal line pattern
        pat = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        pd = ImageDraw.Draw(pat)
        for x in range(-H, W, 90):
            pd.line([(x, H), (x + H, 0)], fill=GOLD + (14,), width=2)
        self.bg.alpha_composite(pat)

    def frame(self, t):
        im = self.bg.copy()
        d = ImageDraw.Draw(im)
        for x, y, r, sp, ph in self.parts:
            yy = (y - t * sp) % H
            xx = x + math.sin(t * 0.8 + ph) * 20
            al = int(90 + 80 * math.sin(t * 2 + ph))
            d.ellipse([xx - r, yy - r, xx + r, yy + r], fill=GOLD_L + (max(0, al),))
        return im


def phone(src_img, w):
    """Screen recording framed as a phone with bezel and rounded corners."""
    h = int(w * SRC_H / SRC_W)
    scr = src_img.resize((w, h), Image.LANCZOS).filter(ImageFilter.UnsharpMask(1.5, 60, 2)).convert("RGBA")
    r = int(w * 0.08)
    m = Image.new("L", (w, h), 0)
    ImageDraw.Draw(m).rounded_rectangle([0, 0, w - 1, h - 1], r, fill=255)
    scr.putalpha(m)
    b = 16
    body = rounded((w + 2 * b, h + 2 * b), r + b, (14, 14, 16, 255))
    ImageDraw.Draw(body).rounded_rectangle([1, 1, w + 2 * b - 2, h + 2 * b - 2], r + b, outline=(90, 90, 96, 255), width=3)
    body.alpha_composite(scr, (b, b))
    return body


# ---------------------------------------------------------------- main
def render(src_path, out_dir, preview=None):
    os.makedirs(out_dir, exist_ok=True)
    subs, gfx, brand, vig = Subtitles(), Graphics(), Branded(), vignette()
    src = Source(src_path)
    n = int(round(DUR * FPS))
    targets = set(int(round(p * FPS)) for p in preview) if preview else None
    enc = None
    if not preview:
        enc = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
                                "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-preset", "medium", "-crf", "18",
                                "-pix_fmt", "yuv420p", os.path.join(out_dir, "video_only.mp4")], stdin=subprocess.PIPE)
    for i in range(n):
        t = i / FPS
        s = src.next() if t < SRC_DUR else src.last
        if targets is not None and i not in targets:
            if i > max(targets):
                break
            continue
        frame = draw_frame(t, s, subs, gfx, brand, vig)
        if enc:
            enc.stdin.write(frame.convert("RGB").tobytes())
        else:
            frame.convert("RGB").save(os.path.join(out_dir, f"prev_{t:05.2f}.jpg"), quality=88)
        if i % 60 == 0:
            print(f"{t:5.1f}s", flush=True)
    if enc:
        enc.stdin.close()
        enc.wait()


def draw_frame(t, s, subs, gfx, brand, vig):
    if t < WEB_T:
        c = camera_frame(s, t)
        c.alpha_composite(vig)
        gfx.corner_logo(c, t)
        gfx.professions(c, t)
        gfx.need(c, t)
        gfx.title_card(c, t)
        gfx.features(c, t)
        gfx.standing(c, t)
        gfx.apartments(c, t)
        subs.draw(c, t, 1560)
        # green diagonal wipe into the website section
        wp = prog(t, WEB_T - 0.35, 0.35)
        if wp > 0:
            wipe(c, ease_in_out(wp), cover=True)
    elif t < SRC_DUR:
        c = brand.frame(t)
        web_section(c, t, s, gfx, subs)
        wp = prog(t, WEB_T, 0.35)
        if wp < 1:
            wipe(c, ease_in_out(wp), cover=False)
    else:
        c = brand.frame(t)
        outro(c, t, s, gfx)
    return c


def wipe(c, p, cover):
    """Diagonal green/gold panel. cover=True: sweeping in; False: sweeping out."""
    poly_layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(poly_layer)
    span = W + H * 0.6
    if cover:
        edge = -H * 0.6 + p * span * 1.05
        d.polygon([(-10, -10), (edge + H * 0.6, -10), (edge, H + 10), (-10, H + 10)], fill=GREEN + (255,))
        d.line([(edge + H * 0.6, -10), (edge, H + 10)], fill=GOLD, width=14)
    else:
        edge = -H * 0.6 + p * span * 1.05
        d.polygon([(edge + H * 0.6, -10), (W + 10, -10), (W + 10, H + 10), (edge, H + 10)], fill=GREEN + (255,))
        d.line([(edge + H * 0.6, -10), (edge, H + 10)], fill=GOLD, width=14)
    c.alpha_composite(poly_layer)


def web_section(c, t, s, gfx, subs):
    lt = t - WEB_T
    # header: logo
    p = ease_out_cubic(prog(lt, 0.2, 0.5))
    gfx.put(c, gfx.logo_small, W / 2, 110 - (1 - p) * 80, 1.0, p, shadow=False)
    # phone
    pw = 560
    ph = phone(s, pw)
    pp = ease_out_back(prog(lt, 0.15, 0.7), 1.1)
    out = prog(t, 28.75, 0.45)
    float_y = math.sin(lt * 1.6) * 8
    cy = 200 + ph.height / 2 + (1 - pp) * 1400 + float_y
    gfx.put(c, ph, W / 2, cy, 1.0 - 0.3 * ease_in_out(out), 1 - out)
    # chips on both sides of the phone, alternating
    pos = [(W / 2 - 330, 560), (W / 2 + 330, 860), (W / 2 - 330, 1160)]
    for (img, (_, _, ts), (x, y)) in zip(gfx.web_chip_imgs, gfx.web_chips, pos):
        q = prog(t, ts, 0.45)
        if q > 0:
            a = window(t, ts, 28.9, 0.2, 0.3)
            gfx.put(c, img, x, y + math.sin(t * 2 + x) * 6, ease_out_back(q, 2), a)
    # URL pill typing
    url = "immobilierelwahra.com"
    q = prog(t, 26.3, 1.2)
    if q > 0:
        n = int(len(url) * q)
        f = F_BOLD(42)
        pill_w = 700
        pill = rounded((pill_w, 96), 48, CREAM + (255,))
        pd = ImageDraw.Draw(pill)
        pill.alpha_composite(gfx.globe, (28, 26))
        caret = "|" if (int(t * 4) % 2 == 0 and q < 1) else ""
        pd.text((90, 48), url[:n] + caret, font=f, fill=GREEN, anchor="lm")
        a = window(t, 26.3, 30.0, 0.25, 0.2)
        gfx.put(c, pill, W / 2, 1560, ease_out_back(prog(t, 26.3, 0.4)), a)
    # Bienvenue
    q = prog(t, 28.9, 0.5)
    if q > 0:
        a = clamp((30.05 - t) / 0.2)
        sc = ease_out_back(q, 2.0)
        tile = Image.new("RGBA", (1000, 260), (0, 0, 0, 0))
        ImageDraw.Draw(tile).text((500, 130), "BIENVENUE !", font=F_SERIF(140), fill=GOLD_L, anchor="mm")
        gfx.put(c, tile, W / 2, 880, 0.5 + 0.5 * sc, a * clamp(q * 2))
        hand = prog(t, 29.15, 0.4)
        if hand > 0:
            gfx.text(c, "MARHBA BIKOM", F_BOLD(46), W / 2, 1030, CREAM, a * hand, spacing=10)
    subs.draw(c, t, 1730)


def outro(c, t, s, gfx):
    lt = t - SRC_DUR
    p = ease_out_back(prog(lt, 0.0, 0.7), 1.4)
    gfx.put(c, gfx.logo_big, W / 2, 640, 0.6 + 0.4 * p, clamp(p * 1.5))
    q = ease_out_cubic(prog(lt, 0.5, 0.6))
    ImageDraw.Draw(c).rectangle([W / 2 - 260 * q, 760, W / 2 + 260 * q, 766], fill=GOLD)
    q = prog(lt, 0.7, 0.5)
    gfx.text(c, "YESSINE CENTRE", F_SERIF(84), W / 2, 880, WHITE, clamp(q * 2), spacing=3)
    gfx.text(c, "RADÈS · BEN AROUS", F_SEMI(40), W / 2, 970, GOLD_L, clamp(q * 2), spacing=5)
    q = prog(lt, 1.1, 0.5)
    if q > 0:
        f = F_BOLD(38)
        lines = ["Locaux commerciaux · Espaces pros", "Appartements S+1 · S+2 · S+3"]
        for k, l in enumerate(lines):
            qq = prog(lt, 1.1 + k * 0.15, 0.5)
            gfx.text(c, l, f, W / 2, 1090 + k * 64 + (1 - ease_out_cubic(qq)) * 30, CREAM, clamp(qq * 2))
    q = prog(lt, 1.6, 0.6)
    if q > 0:
        btn = rounded((760, 130), 65, GOLD + (255,))
        bd = ImageDraw.Draw(btn)
        btn.alpha_composite(gfx.cal, (60, 41))
        bd.text((420, 65), "RÉSERVEZ VOTRE VISITE", font=F_SUB(40), fill=GREEN_D, anchor="mm")
        pulse = 1 + 0.03 * math.sin(lt * 6) * (1 if lt > 2.3 else 0)
        gfx.put(c, btn, W / 2, 1340, ease_out_back(q, 2) * pulse, 1)
    q = prog(lt, 2.0, 0.5)
    if q > 0:
        pill = rounded((700, 96), 48, (255, 255, 255, 30))
        ImageDraw.Draw(pill).rounded_rectangle([0, 0, 699, 95], 48, outline=CREAM + (120,), width=2)
        g = icon("globe", 44, CREAM, 2.2)
        pill.alpha_composite(g, (40, 26))
        ImageDraw.Draw(pill).text((375, 48), "immobilierelwahra.com", font=F_BOLD(40), fill=WHITE, anchor="mm")
        gfx.put(c, pill, W / 2, 1490, 1, clamp(q * 2), shadow=False)
    # final fade to black
    f = prog(t, DUR - 0.4, 0.4)
    if f > 0:
        blk = Image.new("RGBA", (W, H), (0, 0, 0, int(255 * f)))
        c.alpha_composite(blk)


if __name__ == "__main__":
    src_path, out_dir = sys.argv[1], sys.argv[2]
    prev = None
    if len(sys.argv) > 3 and sys.argv[3] == "--preview":
        prev = [float(x) for x in sys.argv[4].split(",")]
    render(src_path, out_dir, prev)
