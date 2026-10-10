"""Shared timing: where each voice-over cue, scene and transition sits on the clock."""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))

W, H, FPS = 1456, 732, 30   # same size as the building render
LEAD = 1.3                  # logo sting before the voice starts
TAIL = 3.8                  # end card after the voice stops
TRANS = 0.6                 # transition length
SCENE_LEAD = 0.35           # scene changes slightly before its first phrase

SCENES = ["intro", "location", "standing", "features", "plan", "contact", "outro"]


def load():
    script = json.load(open(os.path.join(HERE, "script.json"), encoding="utf-8"))["cues"]
    timing = json.load(open(os.path.join(HERE, "vo", "timing.json")))
    durs = {t["i"]: t["dur"] for t in timing}

    cues, t = [], LEAD
    for i, c in enumerate(script):
        d = durs[i]
        cues.append(dict(c, i=i, start=t, end=t + d, dur=d, file=os.path.join(HERE, "vo", f"cue_{i:02d}.wav")))
        t += d + c["pause"]
    vo_end = cues[-1]["end"]
    total = vo_end + TAIL

    starts = {}
    for c in cues:
        starts.setdefault(c["scene"], c["start"])
    bounds = [0.0] + [starts[s] - SCENE_LEAD for s in SCENES[1:]] + [total]
    scenes = [dict(name=s, start=bounds[k], end=bounds[k + 1]) for k, s in enumerate(SCENES)]
    for s in scenes:
        s["cues"] = [c for c in cues if c["scene"] == s["name"]]
    transitions = [b for b in bounds[1:-1]]
    return dict(cues=cues, scenes=scenes, transitions=transitions, vo_end=vo_end, total=total)


def word_times(cue):
    """Rough start time of each spoken word, proportional to its length."""
    words = cue["sub"].replace("،", " ").replace("–", " ").split()
    lens = [len(w) + 1.5 for w in words]
    tot, acc, out = sum(lens), 0.0, []
    for w, n in zip(words, lens):
        out.append((w, cue["start"] + cue["dur"] * acc / tot))
        acc += n
    return out


def at(cue, word):
    """Time at which `word` is spoken in `cue` (first occurrence)."""
    for w, t in word_times(cue):
        if w == word:
            return t
    raise KeyError(word)


def group_times(cue):
    """Start time of each comma-separated group inside a spoken phone number."""
    parts = [p for p in cue["tts"].replace("،", ",").split(",") if p.strip(" .:")]
    lens = [len(p.strip()) for p in parts]
    out, acc = [], 0
    for n in lens:
        out.append(cue["start"] + cue["dur"] * acc / sum(lens))
        acc += n
    return out


def srt(tl, path):
    def ts(x):
        ms = int(round(x * 1000))
        return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"
    with open(path, "w", encoding="utf-8") as f:
        for n, c in enumerate(tl["cues"], 1):
            end = c["end"] + min(c["pause"], 0.25)
            f.write(f"{n}\n{ts(c['start'])} --> {ts(end)}\n{c['sub']}\n\n")


if __name__ == "__main__":
    tl = load()
    for s in tl["scenes"]:
        print(f"{s['name']:9s} {s['start']:6.2f} -> {s['end']:6.2f}  ({s['end'] - s['start']:.2f}s)")
    print("total", round(tl["total"], 2), "vo_end", round(tl["vo_end"], 2))
