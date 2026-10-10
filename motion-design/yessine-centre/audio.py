#!/usr/bin/env python3
"""Synthesised music bed + SFX for the promo. Usage: audio.py OUT_DIR"""
import os, sys, wave
import numpy as np

SR = 44100
DUR = 33.5
rng = np.random.default_rng(3)


def tvec(d):
    return np.arange(int(d * SR)) / SR


def lowpass(x, cutoff):
    a = np.exp(-2 * np.pi * cutoff / SR)
    y = np.empty_like(x)
    acc = 0.0
    for i in range(len(x)):  # small signals only
        acc = (1 - a) * x[i] + a * acc
        y[i] = acc
    return y


def lp_fast(x, cutoff, passes=2):
    # FFT brick-ish low-pass with smooth roll-off
    X = np.fft.rfft(x)
    f = np.fft.rfftfreq(len(x), 1 / SR)
    X *= 1 / (1 + (f / cutoff) ** (2 * passes))
    return np.fft.irfft(X, len(x))


def hp_fast(x, cutoff, passes=2):
    X = np.fft.rfft(x)
    f = np.fft.rfftfreq(len(x), 1 / SR)
    X *= 1 - 1 / (1 + (f / max(cutoff, 1)) ** (2 * passes))
    return np.fft.irfft(X, len(x))


def note(n):
    return 440.0 * 2 ** ((n - 69) / 12)


def add(buf, sig, at):
    i = int(at * SR)
    if i >= len(buf):
        return
    j = min(len(buf), i + len(sig))
    buf[i:j] += sig[: j - i]


# ------------------------------------------------------------- music
BPM = 100
BEAT = 60 / BPM
BAR = 4 * BEAT
# Am9 – Fmaj7 – Cmaj7 – G6 (warm, "real-estate" mood)
CHORDS = [[57, 60, 64, 67, 71], [53, 57, 60, 64, 69], [48, 55, 59, 64, 67], [55, 59, 62, 64, 67]]
BASS = [45, 41, 48, 43]


def pad_chord(notes, d):
    t = tvec(d)
    s = np.zeros_like(t)
    for n in notes:
        for det in (-0.12, 0.0, 0.12):
            f = note(n + det)
            s += np.sin(2 * np.pi * f * t) + 0.25 * np.sin(4 * np.pi * f * t + 0.3)
    env = np.minimum(1, t / 0.6) * np.minimum(1, (d - t) / 0.5)
    return s * env / (len(notes) * 3)


def pluck(n, d=0.6):
    t = tvec(d)
    f = note(n)
    s = np.sin(2 * np.pi * f * t) + 0.4 * np.sin(4 * np.pi * f * t) + 0.15 * np.sin(6 * np.pi * f * t)
    return s * np.exp(-t * 7) * np.minimum(1, t / 0.004)


def kick():
    t = tvec(0.35)
    f = 50 + 90 * np.exp(-t * 30)
    ph = 2 * np.pi * np.cumsum(f) / SR
    return np.sin(ph) * np.exp(-t * 9)


def hat():
    t = tvec(0.08)
    return hp_fast(rng.standard_normal(len(t)), 7000) * np.exp(-t * 60) * 0.5


def bass(n, d):
    t = tvec(d)
    f = note(n)
    s = np.sin(2 * np.pi * f * t) + 0.3 * np.sin(4 * np.pi * f * t)
    return s * np.minimum(1, t / 0.01) * np.exp(-t * 1.2) * np.minimum(1, (d - t) / 0.05)


def music():
    L = np.zeros(int(DUR * SR))
    R = np.zeros(int(DUR * SR))
    nbars = int(np.ceil(DUR / BAR))
    arp_pat = [0, 2, 4, 2, 1, 3, 4, 3]
    for b in range(nbars):
        t0 = b * BAR
        ch = CHORDS[b % 4]
        p = pad_chord(ch, BAR + 0.4)
        add(L, p * 0.55, t0)
        add(R, p * 0.55, t0)
        bs = bass(BASS[b % 4], BAR)
        add(L, bs * 0.35, t0)
        add(R, bs * 0.35, t0)
        for k in range(8):
            n = ch[arp_pat[k]] + 12
            pl = pluck(n) * 0.16
            pan = 0.5 + 0.35 * np.sin(k)
            add(L, pl * (1 - pan), t0 + k * BEAT / 2)
            add(R, pl * pan, t0 + k * BEAT / 2)
        if t0 >= 0.0:
            for k in range(4):
                add(L, kick() * 0.45, t0 + k * BEAT)
                add(R, kick() * 0.45, t0 + k * BEAT)
                hh = hat() * 0.12
                add(L, hh, t0 + k * BEAT + BEAT / 2)
                add(R, hh * 0.8, t0 + k * BEAT + BEAT / 2)
    # gentle intro fade-in and outro fade-out
    t = np.arange(len(L)) / SR
    env = np.minimum(1, t / 0.8) * np.clip((DUR - t) / 1.2, 0, 1)
    return L * env, R * env


# ------------------------------------------------------------- sfx
def whoosh(d=0.5, f0=400, f1=4000):
    n = int(d * SR)
    t = np.arange(n) / SR
    noise = rng.standard_normal(n)
    # sweep band by mixing progressively filtered copies
    lo, hi = lp_fast(noise, f0), lp_fast(noise, f1)
    x = t / d
    s = lo * (1 - x) + hi * x
    env = np.sin(np.pi * x) ** 2
    return s * env * 0.35


def pop(f=880):
    t = tvec(0.14)
    fr = f * (1 + 0.6 * np.exp(-t * 40))
    ph = 2 * np.pi * np.cumsum(fr) / SR
    return np.sin(ph) * np.exp(-t * 28) * 0.35


def ding(f=1320):
    t = tvec(0.9)
    s = np.sin(2 * np.pi * f * t) + 0.5 * np.sin(2 * np.pi * f * 2.01 * t) + 0.2 * np.sin(2 * np.pi * f * 3.02 * t)
    return s * np.exp(-t * 5) * 0.18


def impact():
    t = tvec(1.2)
    f = 40 + 60 * np.exp(-t * 8)
    ph = 2 * np.pi * np.cumsum(f) / SR
    body = np.sin(ph) * np.exp(-t * 3)
    nz = lp_fast(rng.standard_normal(len(t)), 1500) * np.exp(-t * 6) * 0.3
    return (body + nz) * 0.6


def riser(d=1.0):
    t = tvec(d)
    nz = hp_fast(rng.standard_normal(len(t)), 1500)
    return nz * (t / d) ** 2 * 0.12


def tick():
    t = tvec(0.03)
    return hp_fast(rng.standard_normal(len(t)), 3000) * np.exp(-t * 200) * 0.25


def sfx():
    S = np.zeros(int(DUR * SR))
    for k, ts in enumerate([0.12, 0.62, 1.16, 1.72, 2.26, 3.28]):
        add(S, pop(700 + 90 * k), ts)
    for ts in [5.3, 6.1, 6.9]:
        add(S, pop(620), ts)
    for ts in [4.654, 6.823, 8.941, 13.412, 15.581, 17.733, 22.139]:
        add(S, whoosh(0.35, 300, 3000) * 0.6, ts - 0.2)
    add(S, riser(0.9), 11.62 - 0.9)
    add(S, impact(), 11.62)
    add(S, ding(1568), 12.6)
    for ts in [15.14, 16.32]:
        add(S, whoosh(0.4, 500, 5000), ts - 0.15)
    for i in range(5):
        add(S, ding(1760 + i * 120) * 0.6, 17.8 + i * 0.12)
    for k, ts in enumerate([20.66, 21.48, 22.96]):
        add(S, pop(660 + 140 * k) * 1.2, ts)
    add(S, whoosh(0.7, 200, 6000) * 1.3, 23.72 - 0.1)
    add(S, whoosh(0.6, 3000, 300), 24.15)
    for ts in [24.06, 24.78, 25.6]:
        add(S, pop(980), ts)
    url_len = 21
    for i in range(url_len):
        add(S, tick(), 26.3 + i * 1.2 / url_len)
    add(S, ding(1318), 28.9)
    add(S, ding(1976) * 0.7, 29.0)
    add(S, impact() * 0.7, 30.0)
    add(S, pop(880), 31.6)
    return S


def write(path, L, R):
    st = np.stack([L, R], 1)
    st = np.clip(st, -1, 1)
    with wave.open(path, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes((st * 32767).astype(np.int16).tobytes())


if __name__ == "__main__":
    out = sys.argv[1]
    L, R = music()
    peak = max(np.abs(L).max(), np.abs(R).max())
    write(os.path.join(out, "music.wav"), L / peak * 0.8, R / peak * 0.8)
    S = sfx()
    S = S / np.abs(S).max() * 0.8
    write(os.path.join(out, "sfx.wav"), S, S)
    print("ok")
