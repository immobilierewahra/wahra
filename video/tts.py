"""Generate the voice-over (Arabic, plus French cues), one clip per cue, plus a timing file.

Usage:  python3 tts.py --voice-dir <arabic voice> --fr-voice-dir <french voice> [--asr-dir <whisper dir>]
                       [--takes 5] [--only 3 7]

Voices are Piper/VITS models packaged for sherpa-onnx, e.g.
https://github.com/k2-fsa/sherpa-onnx/releases/download/tts-models/vits-piper-ar_JO-kareem-medium.tar.bz2
https://github.com/k2-fsa/sherpa-onnx/releases/download/tts-models/vits-piper-fr_FR-upmc-medium.tar.bz2
A cue with "lang": "fr" in script.json is spoken by the French voice (speaker --fr-sid).

VITS synthesis is stochastic, so with --asr-dir (a sherpa-onnx Whisper model, e.g.
.../releases/download/asr-models/sherpa-onnx-whisper-turbo.tar.bz2) several takes of
each phrase are generated and the one Whisper transcribes most faithfully is kept.
"""
import argparse
import glob
import json
import os
import re

import numpy as np
import sherpa_onnx
import soundfile as sf

HERE = os.path.dirname(os.path.abspath(__file__))


def load_tts(voice_dir, threads=4):
    model = glob.glob(os.path.join(voice_dir, "*.onnx"))[0]
    cfg = sherpa_onnx.OfflineTtsConfig(
        model=sherpa_onnx.OfflineTtsModelConfig(
            vits=sherpa_onnx.OfflineTtsVitsModelConfig(
                model=model,
                lexicon="",
                data_dir=os.path.join(voice_dir, "espeak-ng-data"),
                tokens=os.path.join(voice_dir, "tokens.txt"),
                noise_scale=0.6,
                noise_scale_w=0.7,
            ),
            provider="cpu",
            num_threads=threads,
        ),
        max_num_sentences=1,
    )
    return sherpa_onnx.OfflineTts(cfg)


def trim(x, sr, thresh=0.005, pad=0.08):
    """Strip leading/trailing silence, keep a short natural pad."""
    idx = np.where(np.abs(x) > thresh)[0]
    if len(idx) == 0:
        return x
    a = max(0, idx[0] - int(pad * sr))
    b = min(len(x), idx[-1] + int(pad * sr))
    return x[a:b]


def load_asr(asr_dir, threads=4, language="ar"):
    pick = lambda pat: sorted(glob.glob(os.path.join(asr_dir, pat)))[0]
    return sherpa_onnx.OfflineRecognizer.from_whisper(
        encoder=pick("*encoder*.onnx"), decoder=pick("*decoder*.onnx"),
        tokens=pick("*tokens.txt"), language=language, task="transcribe", num_threads=threads)


def norm(s, lang="ar"):
    if lang != "ar":
        return re.sub(r"[^a-zà-ÿ0-9]", "", s.lower())
    s = re.sub(r"[\u064B-\u0652\u0670\u0640]", "", s)
    s = re.sub(r"[إأآٱ]", "ا", s).replace("ة", "ه").replace("ى", "ي")
    return re.sub(r"[^\u0621-\u064A0-9]", "", s)


def cer(ref, hyp):
    d = list(range(len(hyp) + 1))
    for i, a in enumerate(ref, 1):
        p, d[0] = d[0], i
        for j, b in enumerate(hyp, 1):
            p, d[j] = d[j], min(d[j] + 1, d[j - 1] + 1, p + (a != b))
    return d[len(hyp)] / max(1, len(ref))


def score(asr, cue, x, sr):
    s = asr.create_stream()
    s.accept_waveform(sr, x)
    asr.decode_stream(s)
    lang = cue.get("lang", "ar")
    hyp = norm(s.result.text, lang)
    err = cer(norm(cue["tts"], lang), hyp)
    if "phone" in cue:  # Whisper may write the spoken number as digits
        digits = re.sub(r"\D", "", cue["sub"].replace("+216", ""))
        err = min(err, cer(digits, re.sub(r"\D", "", hyp)))
    return err, s.result.text.strip()


def robust_score(asr, cue, x, sr, seed=0):
    """Worst-case score of a take, clean and with a music-like noise bed underneath (~14 dB below)."""
    err, hyp = score(asr, cue, x, sr)
    rng = np.random.default_rng(seed)
    noise = np.cumsum(rng.standard_normal(len(x))).astype(np.float32)   # brown-ish, like a pad + bass
    noise -= np.convolve(noise, np.ones(200) / 200, "same")
    noise *= np.sqrt(np.mean(x ** 2)) / (np.sqrt(np.mean(noise ** 2)) + 1e-9) * 0.2
    err2, _ = score(asr, cue, x + noise, sr)
    return max(err, err2), hyp


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--voice-dir", required=True)
    ap.add_argument("--speed", type=float, default=1.35)
    ap.add_argument("--fr-voice-dir", help="French voice for cues with \"lang\": \"fr\"")
    ap.add_argument("--fr-sid", type=int, default=1, help="speaker id in the French voice (upmc: 1 = pierre)")
    ap.add_argument("--out", default=os.path.join(HERE, "vo"))
    ap.add_argument("--only", type=int, nargs="*", help="cue indices to render")
    ap.add_argument("--asr-dir", help="Whisper model dir used to pick the clearest take")
    ap.add_argument("--takes", type=int, default=5)
    args = ap.parse_args()

    script = json.load(open(os.path.join(HERE, "script.json"), encoding="utf-8"))
    os.makedirs(args.out, exist_ok=True)
    voices = {"ar": (load_tts(args.voice_dir), 0)}
    if args.fr_voice_dir:
        voices["fr"] = (load_tts(args.fr_voice_dir), args.fr_sid)
    asrs = {lang: load_asr(args.asr_dir, language=lang) for lang in voices} if args.asr_dir else {}

    timing_path = os.path.join(args.out, "timing.json")
    timing = json.load(open(timing_path)) if args.only and os.path.exists(timing_path) else []
    timing = [t for t in timing if t["i"] not in (args.only or [])]
    for i, cue in enumerate(script["cues"]):
        if args.only and i not in args.only:
            continue
        lang = cue.get("lang", "ar")
        tts, sid = voices[lang]
        asr = asrs.get(lang)
        best = None
        for _ in range(args.takes if asr else 1):
            audio = tts.generate(cue["tts"], sid=sid, speed=cue.get("speed", args.speed))
            sr = audio.sample_rate
            x = trim(np.asarray(audio.samples, dtype=np.float32), sr)
            err, hyp = robust_score(asr, cue, x, sr) if asr else (0.0, "")
            if best is None or err < best[0]:
                best = (err, hyp, x)
            if err == 0:
                break
        err, hyp, x = best
        path = os.path.join(args.out, f"cue_{i:02d}.wav")
        sf.write(path, x, sr)
        timing.append({"i": i, "file": os.path.basename(path), "dur": round(len(x) / sr, 4), "asr": hyp, "cer": round(err, 3)})
        print(f"{i:02d} {len(x) / sr:5.2f}s  cer={err:.2f}  {hyp}")
    json.dump(sorted(timing, key=lambda t: t["i"]), open(timing_path, "w"), indent=1)


if __name__ == "__main__":
    main()
