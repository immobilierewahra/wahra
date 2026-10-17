"""Arabic voice-over for the La Sirène Tesla video (Piper ar_JO-kareem, best take chosen by Whisper).

python3 sirene_vo.py -> vo_sirene/line_XX.wav + vo_sirene/lines.json
"""
import json
import os

import numpy as np
import soundfile as sf

from tts import load_asr, load_tts, robust_score, trim

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "vo_sirene")
LINES = [  # (key, diacritized text for the voice, subtitle, pace)
    ("hook",   "حَتَّى تِسْلَا الجَدِيدَةْ... اِخْتَارَتْ عُنْوَانَهَا!", "حتّى تسلا الجديدة… اختارت عنوانها!", 1.1),
    ("power",  "لِأَنَّ القِمَّةَ تَسْتَحِقّْ.", "لأنّ القمّة تستحقّ", 1.05),
    ("climb",  "طَابِقًا بَعْدَ طَابِقْ...", "طابقًا بعد طابق…", 1.05),
    ("spin",   "طُمُوحٌ بِلَا حُدُودْ!", "طموح بلا حدود!", 1.05),
    ("land",   "إِقَامَةُ لَا سِيرِينْ... هُنَا تَبْدَأُ القِمَّةُ!", "إقامة La Sirène… هنا تبدأ القمّة!", 1.08),
    ("addr",   "عُنْوَانُكَ القَادِمُ... فِي الأَعْلَى!", "عنوانك القادم… في الأعلى!", 1.08),
    ("call",   "اِتَّصِلُوا بِنَا الآنْ!", "اتصلوا بنا الآن!", 1.05),
]


def main():
    os.makedirs(OUT, exist_ok=True)
    tts = load_tts(os.path.join(HERE, "models", "vits-piper-ar_JO-kareem-medium"))
    asr = load_asr(os.path.join(HERE, "models", "sherpa-onnx-whisper-turbo"))
    meta = []
    for k, (key, text, sub, pace) in enumerate(LINES):
        cue = {"tts": text, "sub": sub}
        best = None
        for _ in range(14):
            a = tts.generate(text, sid=0, speed=pace)
            x = trim(np.asarray(a.samples, np.float32), a.sample_rate)
            err, hyp = robust_score(asr, cue, x, a.sample_rate)
            if best is None or err < best[0]:
                best = (err, hyp, x)
            if err == 0:
                break
        err, hyp, x = best
        name = f"line_{k:02d}.wav"
        sf.write(os.path.join(OUT, name), x, a.sample_rate)
        meta.append({"key": key, "file": name, "dur": round(len(x) / a.sample_rate, 3), "sub": sub,
                     "asr": hyp, "cer": round(err, 3)})
        print(f"{key:6s} {len(x) / a.sample_rate:4.2f}s cer={err:.2f} | {hyp}")
    json.dump(meta, open(os.path.join(OUT, "lines.json"), "w"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
