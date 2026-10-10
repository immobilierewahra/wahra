"""Generate the voice-over, one clip per cue, plus a timing file.

Two engines:
  piper (default, offline)  python3 tts.py --voice-dir <arabic voice> --fr-voice-dir <french voice> [--asr-dir <whisper>]
  elevenlabs                python3 tts.py --engine elevenlabs [--asr-dir <whisper>]
                            reads ELEVENLABS_API_KEY, optional ELEVENLABS_VOICE_ID / ELEVENLABS_MODEL
                            (one voice speaks both the Arabic and the French cues)

Piper voices are packaged for sherpa-onnx, e.g.
https://github.com/k2-fsa/sherpa-onnx/releases/download/tts-models/vits-piper-ar_JO-kareem-medium.tar.bz2
https://github.com/k2-fsa/sherpa-onnx/releases/download/tts-models/vits-piper-fr_FR-upmc-medium.tar.bz2
A cue with "lang": "fr" in the script is spoken in French.

Synthesis is stochastic, so with --asr-dir (a sherpa-onnx Whisper model, e.g.
.../releases/download/asr-models/sherpa-onnx-whisper-turbo.tar.bz2) several takes of
each phrase are generated and the one Whisper transcribes most faithfully is kept.

When the script sets a target length (settings.target), every clip is sped up by the same
factor if the voice-over does not fit (pitch-preserving time stretch).
VIDEO_VARIANT selects the script / output folder (see timeline.py).
"""
import argparse
import glob
import json
import os
import re

import subprocess
import urllib.request

import numpy as np
import sherpa_onnx
import soundfile as sf

import timeline as T

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


class ElevenLabs:
    """ElevenLabs text-to-speech over its REST API (needs network access to api.elevenlabs.io)."""
    URL = "https://api.elevenlabs.io/v1/text-to-speech/{voice}?output_format=mp3_44100_128"

    def __init__(self, voice_id, model, speed):
        self.key = os.environ["ELEVENLABS_API_KEY"]
        self.voice, self.model, self.speed = voice_id, model, speed

    @staticmethod
    def plain(text):
        return re.sub(r"[\u064B-\u0652\u0670\u0640]", "", text)   # ElevenLabs reads undiacritized Arabic best

    def generate(self, text, speed, prev_text=None, next_text=None):
        body = {"text": self.plain(text), "model_id": self.model,
                "voice_settings": {"stability": 0.45, "similarity_boost": 0.8, "style": 0.25,
                                   "use_speaker_boost": True, "speed": max(0.7, min(1.2, speed))}}
        if prev_text:
            body["previous_text"] = self.plain(prev_text)
        if next_text:
            body["next_text"] = self.plain(next_text)
        req = urllib.request.Request(self.URL.format(voice=self.voice), data=json.dumps(body).encode(),
                                     headers={"xi-api-key": self.key, "Content-Type": "application/json",
                                              "Accept": "audio/mpeg"})
        mp3 = urllib.request.urlopen(req, timeout=120).read()
        pcm = subprocess.run(["ffmpeg", "-loglevel", "error", "-i", "pipe:0", "-ac", "1", "-ar", "44100",
                              "-f", "f32le", "pipe:1"], input=mp3, capture_output=True, check=True).stdout
        return np.frombuffer(pcm, np.float32).copy(), 44100


def stretch(path, factor):
    """Pitch-preserving speed-up of a wav file in place."""
    x, sr = sf.read(path, dtype="float32")
    x = np.concatenate([x, np.zeros(int(0.4 * sr), np.float32)])   # atempo drops the last ~0.1 s: pad first
    out = subprocess.run(["ffmpeg", "-loglevel", "error", "-f", "f32le", "-ar", str(sr), "-ac", "1", "-i", "pipe:0",
                          "-af", f"atempo={factor:.4f}", "-f", "f32le", "pipe:1"],
                         input=x.tobytes(), capture_output=True, check=True).stdout
    y = trim(np.frombuffer(out, np.float32).copy(), sr)
    sf.write(path, y, sr)
    return len(y) / sr


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--engine", choices=["piper", "elevenlabs"], default="piper")
    ap.add_argument("--voice-dir", help="Arabic Piper voice")
    ap.add_argument("--speed", type=float,
                    help="voice pace (default: settings.speed for piper, settings.el_speed or 1.15 for elevenlabs)")
    ap.add_argument("--fr-voice-dir", help="French Piper voice for cues with \"lang\": \"fr\"")
    ap.add_argument("--fr-sid", type=int, default=1, help="speaker id in the French voice (upmc: 1 = pierre)")
    ap.add_argument("--out", default=T.VO_DIR)
    ap.add_argument("--only", type=int, nargs="*", help="cue indices to render")
    ap.add_argument("--asr-dir", help="Whisper model dir used to pick the clearest take")
    ap.add_argument("--takes", type=int, help="takes per phrase (default 5 with piper, 1 with elevenlabs)")
    args = ap.parse_args()

    script = T.read_script()
    st = T.settings(script)
    cues = script["cues"]
    os.makedirs(args.out, exist_ok=True)
    el = args.engine == "elevenlabs"
    piper_speed = st.get("speed", 1.35)
    speed = args.speed or (st.get("el_speed", 1.15) if el else piper_speed)
    takes = args.takes or (1 if el else 5)
    if el:
        engine = ElevenLabs(os.environ.get("ELEVENLABS_VOICE_ID", "JBFqnCBsd6RMkjVDRZzb"),
                            os.environ.get("ELEVENLABS_MODEL", "eleven_multilingual_v2"), speed)
        langs = sorted({c.get("lang", "ar") for c in cues})
    else:
        voices = {"ar": (load_tts(args.voice_dir), 0)}
        if args.fr_voice_dir:
            voices["fr"] = (load_tts(args.fr_voice_dir), args.fr_sid)
        langs = list(voices)
    asrs = {lang: load_asr(args.asr_dir, language=lang) for lang in langs} if args.asr_dir else {}

    timing_path = os.path.join(args.out, "timing.json")
    timing = json.load(open(timing_path)) if args.only and os.path.exists(timing_path) else []
    timing = [t for t in timing if t["i"] not in (args.only or [])]
    for i, cue in enumerate(cues):
        if args.only and i not in args.only:
            continue
        lang = cue.get("lang", "ar")
        # per-cue "speed" is a Piper pace; for ElevenLabs keep it as a ratio to the script's default pace
        pace = speed * cue.get("speed", piper_speed) / piper_speed if el else cue.get("speed", speed)
        asr = asrs.get(lang)
        best = None
        for _ in range(takes if asr else 1):
            if el:
                same = lambda j: 0 <= j < len(cues) and cues[j].get("lang", "ar") == lang
                x, sr = engine.generate(cue["tts"], pace, cues[i - 1]["tts"] if same(i - 1) else None,
                                        cues[i + 1]["tts"] if same(i + 1) else None)
            else:
                tts, sid = voices[lang]
                audio = tts.generate(cue["tts"], sid=sid, speed=pace)
                x, sr = np.asarray(audio.samples, dtype=np.float32), audio.sample_rate
            x = trim(x, sr)
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
    timing.sort(key=lambda t: t["i"])

    if st["target"] and not args.only:
        speech = sum(t["dur"] for t in timing)
        room = st["target"] - st["lead"] - st["min_tail"] - sum(c["pause"] for c in cues)
        factor = speech / room
        if factor > 1.005:
            factor = min(factor, 1.35)
            print(f"voice-over {speech:.1f}s > {room:.1f}s available: speeding every phrase up x{factor:.3f}")
            for t in timing:
                t["dur"] = round(stretch(os.path.join(args.out, t["file"]), factor), 4)
    json.dump(timing, open(timing_path, "w"), indent=1, ensure_ascii=False)


if __name__ == "__main__":
    main()
