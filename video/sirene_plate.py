"""Cut the Tesla out of the Résidence La Sirène render and rebuild the street behind it (used by tesla.py).

Writes build/sirene/car_sprite.npy (RGBA car) and build/sirene/plate.png (render without the car).
"""
import os
import numpy as np, cv2
from PIL import Image, ImageDraw
os.makedirs("build/sirene", exist_ok=True)
im = Image.open("assets/sirene/residence.jpg").convert("RGB")
a = np.asarray(im).astype(np.float32)
H, W = a.shape[:2]
# --- car mask (tightened along the hood so the white car's bumper shadow stays out)
poly = [(0,716),(30,715),(60,717),(100,721),(130,728),(158,739),(176,745),(205,747),(228,749),(242,752),(250,757),
        (256,767),(257,780),(255,789),(244,793),(220,796),(160,798),(110,802),(70,802),(55,798),(0,798)]
S = 4
m = Image.new("L", (W * S, H * S)); ImageDraw.Draw(m).polygon([(x * S, y * S) for x, y in poly], fill=255)
pm = np.asarray(m.resize((W, H), Image.LANCZOS)) > 127
k = lambda r: cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * r + 1, 2 * r + 1))
inner = cv2.erode(pm.astype(np.uint8), k(5)) > 0
band = (cv2.dilate(pm.astype(np.uint8), k(3)) > 0) & ~inner
luma = a @ np.array([0.299, 0.587, 0.114])
yy, xx = np.mgrid[0:H, 0:W]
dark = np.where(yy > 790, luma < 60, luma < 105)
dark &= ~((yy < 748) & (xx > 150) & (xx < 215) & (yy > 735))     # white car's rear underbody
mask = inner | (band & dark)
mask = cv2.morphologyEx(mask.astype(np.uint8), cv2.MORPH_CLOSE, k(2)) > 0
ff = mask.astype(np.uint8).copy(); fl = np.zeros((H + 2, W + 2), np.uint8); cv2.floodFill(ff, fl, (W - 1, 0), 1)
mask = mask | (ff == 0)
alpha = cv2.GaussianBlur(mask.astype(np.float32), (0, 0), 0.8)
ys, xs = np.where(mask)
x0, x1, y0, y1 = xs.min(), xs.max() + 1, ys.min(), ys.max() + 1
spr = np.dstack([a[y0:y1, x0:x1] / 255, alpha[y0:y1, x0:x1]]).astype(np.float32)
np.save("build/sirene/car_sprite.npy", spr)
print("car bbox", x0, y0, x1, y1)

# --- clean plate: each road row continued from the right edge of the hole, white car completed softly
hole = cv2.dilate(mask.astype(np.uint8), k(5)) > 0
hole = cv2.dilate(mask.astype(np.uint8), k(5)) > 0
rim = (cv2.dilate(mask.astype(np.uint8), k(9)) > 0) & (xx > 120) & (xx < 185) & (yy < 748)
hole = hole | rim
plate = a.copy()
rng = np.random.default_rng(3)
for y in range(H):
    xs_h = np.where(hole[y])[0]
    if len(xs_h) == 0:
        continue
    xr = xs_h.max() + 1
    ref = np.median(a[y, xr:xr + 24], axis=0)
    if 700 <= y < 750:                      # behind the white car: the far lane, sampled past its rear
        ref = np.median(a[y, 222:250], axis=0) if y >= 718 else np.median(a[y, 230:260], axis=0)
    plate[y, xs_h] = ref + rng.normal(0, 2.0, (len(xs_h), 3))
# white car lower body: vertical colour profile of its visible lower bumper, shaded towards the bottom
prof = a[:, 194:204].mean(1)
for x in range(22, 198):
    for y in range(704, 748):
        if hole[y, x]:
            t = (x - 22) / 176
            v = prof[y] * (0.92 + 0.08 * t)
            plate[y, x] = v
under = np.zeros((H, W), np.float32)
under[743:756, 24:198] = 1
under = cv2.GaussianBlur(under, (0, 0), 3)
plate = plate * (1 - 0.55 * under[..., None]) + np.array([40, 42, 46]) * 0.55 * under[..., None]
for cx in (58, 158):
    wm = np.zeros((H, W), np.float32)
    cv2.ellipse(wm, (cx, 746), (12, 11), 0, 0, 360, 1, -1)
    wm = cv2.GaussianBlur(wm, (0, 0), 1.2)[..., None]
    rim = np.zeros((H, W), np.float32)
    cv2.ellipse(rim, (cx, 746), (7, 7), 0, 0, 360, 1, -1)
    rim = cv2.GaussianBlur(rim, (0, 0), 1.0)[..., None]
    plate = plate * (1 - wm) + np.array([30, 30, 33]) * wm
    plate = plate * (1 - 0.8 * rim) + np.array([150, 152, 158]) * 0.8 * rim
fix = cv2.GaussianBlur(hole.astype(np.float32), (0, 0), 1.0)[..., None]
soft = cv2.GaussianBlur(plate, (0, 0), 0.7)
plate = plate * (1 - fix) + soft * fix
edge = cv2.GaussianBlur(hole.astype(np.float32), (0, 0), 2.0)[..., None]
plate = a * (1 - edge) + plate * edge
Image.fromarray(np.clip(plate, 0, 255).astype(np.uint8)).save("build/sirene/plate.png")
Image.fromarray(np.clip(plate, 0, 255).astype(np.uint8)).crop((0, 660, 320, 845)).resize((960, 555), Image.LANCZOS).save("build/sirene/prev_plate.png")
