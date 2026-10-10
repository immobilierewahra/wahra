"""Build the soundtrack: synthesized ambient music bed + sound design + processed voice-over.

python3 audio.py -> build/mix.wav
"""
import math
import os
import re
import subprocess

import numpy as np
import soundfile as sf
from scipy.signal import butter, fftconvolve, resample_poly, sosfilt

import timeline as T

HERE = os.path.dirname(os.path.abspath(__file__))
BUILD = os.path.join(HERE, "build")
SR = 48000
TARGET_LUFS = -15.0
rng = np.random.default_rng(3)


def midi(n):
    return 440.0 * 2 ** ((n - 69) / 12)


def filt(x, kind, f, order=2):
    sos = butter(order, f, btype=kind, fs=SR, output="sos")
    return sosfilt(sos, x, axis=0)


def env_adsr(n, a, d, s, r):
    t = np.arange(n) / SR
    e = np.where(t < a, t / max(a, 1e-6), np.maximum(s, 1 - (1 - s) * (t - a) / max(d, 1e-6)))
    return e * np.clip((n / SR - t) / max(r, 1e-6), 0, 1)


def add(buf, sig, t, gain=1.0, pan=0.0):
    """Mix mono or stereo `sig` into stereo `buf` at time t (s)."""
    i = int(round(t * SR))
    if sig.ndim == 1:
        l, r = math.cos((pan + 1) * math.pi / 4), math.sin((pan + 1) * math.pi / 4)
        sig = np.stack([sig * l, sig * r], 1) * math.sqrt(2)
    j0, j1 = max(0, i), min(len(buf), i + len(sig))
    if j1 > j0:
        buf[j0:j1] += sig[j0 - i:j1 - i] * gain


def reverb(x, seconds=2.4, damp=5000, wet=0.3):
    n = int(seconds * SR)
    t = np.arange(n) / SR
    ir = np.stack([rng.standard_normal(n), rng.standard_normal(n)], 1) * np.exp(-t * 6.5 / seconds)[:, None]
    ir = filt(ir, "lowpass", damp)
    ir[: int(0.012 * SR)] = 0
    ir /= np.sqrt((ir ** 2).sum(0, keepdims=True))
    wetsig = np.stack([fftconvolve(x[:, k], ir[:, k])[: len(x)] for k in range(2)], 1)
    return x * (1 - wet) + wetsig * wet * 2.2


# ---------------------------------------------------------------------- music
CHORDS = [  # (bass, pad voicing, arp notes)  D - Bm - G - A
    (38, [54, 57, 61, 64], [69, 73, 76, 78]),
    (35, [54, 57, 61, 62], [66, 69, 73, 74]),
    (43, [54, 57, 59, 62], [67, 71, 74, 78]),
    (45, [52, 57, 59, 64], [64, 69, 71, 76]),
]
BPM = 84
BEAT = 60 / BPM
BAR = 4 * BEAT


def pad_note(f, dur):
    n = int(dur * SR)
    t = np.arange(n) / SR
    out = np.zeros(n)
    for det in (-0.0018, 0.0021):
        ff = f * (1 + det)
        for h in range(1, 9):
            if ff * h > 5000:
                break
            out += np.sin(2 * np.pi * ff * h * t + rng.uniform(0, 6.28)) / h ** 1.6
    trem = 1 + 0.08 * np.sin(2 * np.pi * 0.23 * t + rng.uniform(0, 6.28))
    return out * trem * env_adsr(n, 1.2, 0.5, 0.85, 1.4)


def pluck(f, dur=1.6):
    n = int(dur * SR)
    t = np.arange(n) / SR
    out = np.zeros(n)
    for h, amp in enumerate([1, 0.45, 0.25, 0.12, 0.07, 0.04], 1):
        out += amp * np.sin(2 * np.pi * f * h * (1 + 0.0004 * h * h) * t) * np.exp(-t * (2.6 + 1.6 * h))
    out *= np.minimum(1, t / 0.004)
    return out


def kick():
    n = int(0.45 * SR)
    t = np.arange(n) / SR
    f = 46 + 80 * np.exp(-t * 28)
    ph = 2 * np.pi * np.cumsum(f) / SR
    return np.sin(ph) * np.exp(-t * 7.5) * np.minimum(1, t / 0.002)


def shaker():
    n = int(0.09 * SR)
    t = np.arange(n) / SR
    x = rng.standard_normal(n) * np.exp(-t * 55) * np.minimum(1, t / 0.006)
    return filt(x, "highpass", 6500)


def music(total, tl):
    N = int(total * SR) + SR
    pad = np.zeros((N, 2))
    plk = np.zeros((N, 2))
    low = np.zeros((N, 2))
    drums = np.zeros((N, 2))
    beat_in = tl["scenes"][1]["start"]          # percussion enters with the first transition
    beat_out = tl["vo_end"] + 0.2               # and drops for the end card
    calm = (tl["scenes"][5]["start"], tl["scenes"][6]["start"])  # lighter during the long contact scene
    nbars = int(total / BAR) + 2
    for b in range(nbars):
        t0 = b * BAR
        if t0 > total:
            break
        bass, voicing, arp = CHORDS[(b // 2) % 4]
        if b % 2 == 0:
            span = 2 * BAR + 1.4
            for k, m in enumerate(voicing):
                add(pad, pad_note(midi(m), span), t0, 0.05, pan=(-0.5 + k / 3))
            n = int(span * SR)
            tt = np.arange(n) / SR
            sub = np.sin(2 * np.pi * midi(bass) * tt) + 0.25 * np.sin(4 * np.pi * midi(bass) * tt)
            add(low, sub * env_adsr(n, 0.25, 0.4, 0.8, 1.2), t0, 0.16)
        for s in range(8):  # eighth-note arpeggio
            ts = t0 + s * BEAT / 2
            if ts < 0.9 or ts > total - 1.5:
                continue
            note = arp[[0, 1, 2, 3, 2, 1, 3, 2][s]] + (12 if s in (3, 6) else 0)
            vel = 0.85 if s % 2 == 0 else 0.6
            if calm[0] < ts < calm[1]:
                vel *= 0.7
            add(plk, pluck(midi(note)), ts, 0.07 * vel, pan=0.45 * math.sin(s * 1.3 + b))
        for s in range(4):
            tb = t0 + s * BEAT
            if beat_in <= tb < beat_out:
                if s in (0, 2) and not (calm[0] < tb < calm[1] and s == 2):
                    add(drums, kick(), tb, 0.33)
            for half in (0, 0.5):
                th = tb + half * BEAT
                if beat_in <= th < beat_out:
                    add(drums, shaker(), th, 0.05 if half else 0.028, pan=0.3)
    # gentle sidechain pump from the kick grid
    t = np.arange(N) / SR
    phase = (t % (2 * BEAT)) / (2 * BEAT)
    pump = 1 - 0.28 * np.exp(-phase * 9) * ((t > beat_in) & (t < beat_out))
    mix = (filt(pad, "lowpass", 2600) * pump[:, None] + plk) + low * pump[:, None]
    mix = reverb(mix, 2.8, 5200, 0.38) + drums
    fade_in = np.minimum(1, t / 1.0)
    fade_out = np.clip((total - t) / 2.5, 0, 1)
    # keep the phone numbers crystal clear: music sits ~6 dB lower during the contact scene
    dip = np.clip(np.minimum((t - calm[0] + 0.5) / 1.0, (calm[1] + 0.3 - t) / 1.0), 0, 1)
    gain = 1 - 0.5 * dip
    return mix * (fade_in * fade_out * gain)[:, None]


# ---------------------------------------------------------------------- sfx
def whoosh(dur=0.9, peak=0.6, up=True):
    n = int(dur * SR)
    t = np.arange(n) / SR
    x = rng.standard_normal(n)
    lo, hi = filt(x, "bandpass", [250, 900]), filt(x, "bandpass", [1500, 6000])
    k = t / dur
    mixk = k if up else 1 - k
    y = lo * (1 - mixk) + hi * mixk * 0.6
    e = np.where(k < peak, (k / peak) ** 2, np.exp(-(k - peak) / (1 - peak) * 4))
    return y * e


def boom():
    n = int(2.2 * SR)
    t = np.arange(n) / SR
    f = 38 + 50 * np.exp(-t * 6)
    s = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 2.4)
    nz = filt(rng.standard_normal(n), "lowpass", 900) * np.exp(-t * 9) * 0.5
    return (s + nz) * np.minimum(1, t / 0.003)


def chime(base=1318.5, dur=2.6):
    n = int(dur * SR)
    t = np.arange(n) / SR
    out = np.zeros(n)
    for r, a, d in [(1, 1, 2.2), (2.01, 0.5, 3.5), (2.76, 0.35, 4.5), (5.4, 0.18, 7), (8.93, 0.08, 9)]:
        out += a * np.sin(2 * np.pi * base * r * t) * np.exp(-t * d)
    sparkle = np.zeros(n)
    for k in range(10):
        st = int(rng.uniform(0, 0.5) * SR)
        f = rng.uniform(3000, 7000)
        m = min(n - st, int(0.4 * SR))
        tt = np.arange(m) / SR
        sparkle[st:st + m] += 0.08 * np.sin(2 * np.pi * f * tt) * np.exp(-tt * 12)
    return (out + sparkle) * np.minimum(1, t / 0.002)


def pop(f0=1100, f1=700, dur=0.09):
    n = int(dur * SR)
    t = np.arange(n) / SR
    f = f1 + (f0 - f1) * np.exp(-t * 60)
    return np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 45) * np.minimum(1, t / 0.001)


def ding():
    return np.concatenate([chime(1318.5, 0.42)[: int(0.42 * SR)] * 0.9, chime(1046.5, 2.0)])


def scan_sweep(dur=1.6):
    n = int(dur * SR)
    t = np.arange(n) / SR
    f = 300 + 2400 * (t / dur) ** 1.5
    tone = np.sin(2 * np.pi * np.cumsum(f) / SR) * 0.25
    nz = filt(rng.standard_normal(n), "bandpass", [2000, 8000]) * 0.4
    e = np.sin(np.pi * t / dur) ** 1.5
    return (tone + nz) * e


def sfx(total, tl):
    N = int(total * SR) + SR
    fx = np.zeros((N, 2))
    cue = tl["cues"]
    # intro: riser into the letterbox opening, boom + chime on the emblem
    add(fx, whoosh(1.1, 0.85, up=True), -0.2, 0.35)
    add(fx, boom(), 0.62, 0.55)
    add(fx, chime(1318.5), 0.98, 0.16)
    add(fx, chime(1760.0, 2.0), T.at(cue[0], "راقية") + 0.4, 0.07)
    # transitions
    for k, b in enumerate(tl["transitions"]):
        add(fx, whoosh(0.9, 0.62, up=k % 2 == 0), b - 0.56, 0.38, pan=(-0.3 if k % 2 else 0.3))
    # location: pin lands
    land = cue[1]["start"] - 0.15 + 0.9 * 0.364
    add(fx, pop(900, 320, 0.16), land, 0.28)
    add(fx, pop(700, 400, 0.08), land + 0.9 * 0.36, 0.1)
    # standing: badge chime + three chips
    add(fx, chime(1567.98, 2.2), cue[2]["start"] + 0.6, 0.09)
    for w in ["الراحة", "الأمان", "وجودة"]:
        add(fx, pop(), T.at(cue[3], w) - 0.1, 0.16)
    # features rows (+ elevator ding)
    for k in range(5):
        add(fx, pop(1250, 750), cue[5 + k]["start"] - 0.15, 0.16, pan=0.4)
    add(fx, ding(), cue[8]["end"] + 0.05, 0.09)
    # plan: stamp, blueprint scan, tag, chart
    stamp = boom()[: int(0.45 * SR)] * np.linspace(1, 0, int(0.45 * SR)) ** 2
    add(fx, stamp, cue[10]["start"] - 0.22, 0.24)   # lands just before "Vente sur plan", not on it
    add(fx, scan_sweep(1.7), cue[10]["end"] - 0.2, 0.18)
    add(fx, pop(1400, 900), T.at(cue[11], "شقتكم"), 0.18)
    add(fx, chime(2093.0, 1.5), cue[11]["start"] + 1.4, 0.05)
    add(fx, pop(), cue[12]["start"] + 0.3, 0.14)
    # contact: rows + digit groups
    for t0 in [T.at(cue[13], "اتصلوا") - 0.1, cue[15]["start"] - 0.1, cue[15]["start"] + 0.1]:
        add(fx, pop(1000, 600), t0, 0.16, pan=0.4)
    # outro + end card
    add(fx, chime(1760.0, 2.2), cue[18]["start"] + 0.9, 0.06)
    endc = tl["vo_end"] + 0.25
    add(fx, boom(), endc + 0.2, 0.5)
    add(fx, chime(1318.5, 3.0), endc + 0.35, 0.16)
    return reverb(fx, 1.8, 7000, 0.22)


# ---------------------------------------------------------------------- voice
def voice(total, tl):
    N = int(total * SR) + SR
    vo = np.zeros(N)
    for c in tl["cues"]:
        x, sr = sf.read(c["file"], dtype="float32")
        g = math.gcd(SR, sr)
        y = resample_poly(x, SR // g, sr // g)
        act = np.abs(y) > 0.02 * np.abs(y).max()
        y = y * 0.12 / np.sqrt(np.mean(y[act] ** 2))   # same loudness for every phrase / voice
        i = int(round(c["start"] * SR))
        vo[i:i + len(y)] += y[: max(0, N - i)]
    return vo / (np.abs(vo).max() + 1e-9) * 0.7


def main():
    tl = T.load()
    total = tl["total"]
    os.makedirs(BUILD, exist_ok=True)
    stems = {"vo": voice(total, tl), "music": music(total, tl), "sfx": sfx(total, tl)}
    db = lambda x: 10 ** (x / 20)
    vo = stems["vo"]
    active = np.abs(vo) > 0.02
    stems["vo"] = vo * db(-17) / np.sqrt(np.mean(vo[active] ** 2))
    stems["music"] *= db(-29) / np.sqrt(np.mean(stems["music"] ** 2))
    stems["sfx"] *= db(-5) / np.abs(stems["sfx"]).max()
    for k, v in stems.items():
        sf.write(os.path.join(BUILD, f"stem_{k}.wav"), np.clip(v, -1, 1).astype(np.float32), SR, subtype="FLOAT")
    pre, out = os.path.join(BUILD, "mix_pre.wav"), os.path.join(BUILD, "mix.wav")
    fc = ("[0:a]highpass=f=80,equalizer=f=200:t=q:w=1.0:g=1.5,equalizer=f=3000:t=q:w=1.4:g=1.5,"
          "acompressor=threshold=-22dB:ratio=2.5:attack=8:release=160:makeup=1.5,"
          "pan=stereo|c0=c0|c1=c0,asplit=2[vo][key];"
          "[1:a][key]sidechaincompress=threshold=0.025:ratio=7:attack=30:release=450[duck];"
          f"[vo][duck][2:a]amix=inputs=3:normalize=0,atrim=0:{total:.3f}[out]")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", os.path.join(BUILD, "stem_vo.wav"),
                    "-i", os.path.join(BUILD, "stem_music.wav"), "-i", os.path.join(BUILD, "stem_sfx.wav"),
                    "-filter_complex", fc, "-map", "[out]", "-ar", str(SR), "-c:a", "pcm_f32le", pre], check=True)
    # static loudness normalisation (a dynamic loudnorm rides the gain and blurs the voice)
    gain = TARGET_LUFS - integrated_loudness(pre)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", pre, "-af",
                    f"volume={gain:.2f}dB,alimiter=limit=0.84:attack=3:release=60:level=disabled",
                    "-ar", str(SR), "-c:a", "pcm_s16le", out], check=True)
    print(f"-> {out}  (gain {gain:+.1f} dB)")


def integrated_loudness(path):
    r = subprocess.run(["ffmpeg", "-hide_banner", "-i", path, "-af", "ebur128", "-f", "null", "-"],
                       capture_output=True, text=True)
    return float(re.findall(r"I:\s+(-?[\d.]+) LUFS", r.stderr)[-1])


if __name__ == "__main__":
    main()
