"""Use a recorded voice-over instead of synthesis.

The script names the recording ("voice_file") and gives each cue its [start, end] span in it ("src").
Each span is cut out (with a little air around it), written to the variant's vo folder, and its
position in the recording is kept, so the voice plays back exactly as recorded and the
animations follow its own rhythm.

VIDEO_VARIANT=voix python3 import_voice.py
"""
import json
import os
import subprocess

import numpy as np
import soundfile as sf

import timeline as T

PAD = 0.06  # seconds kept before / after each phrase (never past the middle of a pause)


def main():
    script = T.read_script()
    src = os.path.join(T.HERE, script["voice_file"])
    sr = 44100
    pcm = subprocess.run(["ffmpeg", "-loglevel", "error", "-i", src, "-ac", "1", "-ar", str(sr), "-f", "f32le", "pipe:1"],
                         capture_output=True, check=True).stdout
    x = np.frombuffer(pcm, np.float32)
    os.makedirs(T.VO_DIR, exist_ok=True)
    cues = script["cues"]
    timing = []
    for i, c in enumerate(cues):
        a, b = c["src"]
        prev_end = cues[i - 1]["src"][1] if i else 0.0
        next_start = cues[i + 1]["src"][0] if i + 1 < len(cues) else len(x) / sr
        a = max(a - PAD, (prev_end + a) / 2)
        b = min(b + PAD, (b + next_start) / 2)
        clip = x[int(a * sr):int(b * sr)]
        name = f"cue_{i:02d}.wav"
        sf.write(os.path.join(T.VO_DIR, name), clip, sr)
        timing.append({"i": i, "file": name, "at": round(a, 4), "dur": round(len(clip) / sr, 4)})
        print(f"{i:02d} {a:6.2f}-{b:6.2f}  {c['sub']}")
    json.dump(timing, open(os.path.join(T.VO_DIR, "timing.json"), "w"), indent=1, ensure_ascii=False)


if __name__ == "__main__":
    main()
