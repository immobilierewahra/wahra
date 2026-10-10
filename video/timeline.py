"""Shared timing: where each voice-over cue, scene and transition sits on the clock.

Several cuts of the video can coexist; pick one with the VIDEO_VARIANT environment variable:
  (unset)  -> script.json,     vo/,     build/,     output/riadh_el_andalous_ar.mp4      (long version)
  30s      -> script_30s.json, vo_30s/, build/30s/, output/riadh_el_andalous_ar_30s.mp4
  voix     -> script_voix.json (recorded voice-over assets/voix_off.mp3, see import_voice.py)
"""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))

W, H, FPS = 1456, 732, 30   # same size as the building render
SCENES = ["intro", "location", "standing", "features", "plan", "contact", "outro"]
DEFAULTS = dict(lead=1.3, tail=3.8, target=None, min_tail=3.0, trans=0.6, scene_lead=0.35)

VARIANT = os.environ.get("VIDEO_VARIANT", "")
SUFFIX = f"_{VARIANT}" if VARIANT else ""
SCRIPT = os.path.join(HERE, f"script{SUFFIX}.json")
VO_DIR = os.path.join(HERE, f"vo{SUFFIX}")
BUILD = os.path.join(HERE, "build", VARIANT) if VARIANT else os.path.join(HERE, "build")
OUTPUT = os.path.join(HERE, "output", f"riadh_el_andalous_ar{SUFFIX}.mp4")


def read_script():
    return json.load(open(SCRIPT, encoding="utf-8"))


def settings(script=None):
    script = script or read_script()
    return dict(DEFAULTS, **script.get("settings", {}))


def load():
    script = read_script()
    st = settings(script)
    timing = json.load(open(os.path.join(VO_DIR, "timing.json")))
    durs = {t["i"]: t["dur"] for t in timing}
    placed = {t["i"]: t["at"] for t in timing if "at" in t}   # recorded voice: keep its own timing

    cues, t = [], st["lead"]
    for i, c in enumerate(script["cues"]):
        d = durs[i]
        if i in placed:
            t = st["lead"] + placed[i]
        cues.append(dict(c, i=i, start=t, end=t + d, dur=d, file=os.path.join(VO_DIR, f"cue_{i:02d}.wav")))
        if i in placed and "src" in c:   # word_at is measured from the phrase onset, the clip starts a bit earlier
            cues[-1]["word_offset"] = c["src"][0] - placed[i]
        t += d + c.get("pause", 0.0)
    for c, nxt in zip(cues, cues[1:]):
        c["pause"] = max(0.0, nxt["start"] - c["end"])
    cues[-1]["pause"] = 0.0
    vo_end = cues[-1]["end"]
    total = st["target"] if st["target"] else vo_end + st["tail"]

    starts = {}
    for c in cues:
        starts.setdefault(c["scene"], c["start"])
    bounds = [0.0] + [starts[s] - st["scene_lead"] for s in SCENES[1:]] + [total]
    scenes = [dict(name=s, start=bounds[k], end=bounds[k + 1]) for k, s in enumerate(SCENES)]
    for s in scenes:
        s["cues"] = [c for c in cues if c["scene"] == s["name"]]
    tl = dict(cues=cues, scenes=scenes, transitions=bounds[1:-1], vo_end=vo_end, total=total,
              trans=st["trans"], screen=script.get("screen", {}))
    tl["roles"] = roles(tl)
    return tl


def word_times(cue):
    """Rough start time of each spoken word, proportional to its length."""
    words = cue["sub"].replace("،", " ").replace("–", " ").replace("!", " ").split()
    lens = [len(w) + 1.5 for w in words]
    tot, acc, out = sum(lens), 0.0, []
    for w, n in zip(words, lens):
        out.append((w, cue["start"] + cue["dur"] * acc / tot))
        acc += n
    return out


def at(cue, word, frac=None):
    """Time at which `word` is spoken in `cue`; falls back to a fraction of the cue when it is not said."""
    if word in cue.get("word_at", {}):          # measured on a recorded voice
        return cue["start"] + cue.get("word_offset", 0.0) + cue["word_at"][word]
    for w, t in word_times(cue):
        if w == word:
            return t
    if frac is None:
        raise KeyError(word)
    return cue["start"] + cue["dur"] * frac


def group_times(cue):
    """Start time of each comma-separated group inside a spoken phone number."""
    parts = [p for p in cue["tts"].replace("،", ",").split(",") if p.strip(" .:")]
    lens = [len(p.strip()) for p in parts]
    out, acc = [], 0
    for n in lens:
        out.append(cue["start"] + cue["dur"] * acc / sum(lens))
        acc += n
    return out


def roles(tl):
    """Times of every animated beat, derived from the cues so any script length works."""
    sc = {s["name"]: s for s in tl["scenes"]}
    R = {}
    c = sc["intro"]["cues"][0]
    R["intro"] = dict(cue=c, l2=at(c, "شقة", 0.45), shine=at(c, "راقية", 0.7) + 0.4, l3=at(c, "في", 0.92))
    c = sc["location"]["cues"][0]
    R["location"] = dict(cue=c, word=at(c, "رياض", 0.45))
    cs = sc["standing"]["cues"]
    R["standing"] = dict(cue=cs[0], t1=at(cs[0], "إقامة", 0.0), t2=at(cs[0], "بتصميم", 0.55),
                         shine=cs[0]["start"] + min(2.6, cs[0]["dur"] * 0.6),
                         chips=[at(cs[1], w) for w in ("الراحة", "الأمان", "وجودة")] if len(cs) > 1 else [])
    S = sc["features"]
    head = [c for c in S["cues"] if c.get("header")]
    rows = {}
    for c in S["cues"]:
        if "feature" in c:
            rows[c["feature"]] = c["start"]
        for word, k in c.get("features_at", {}).items():
            rows[k] = at(c, word)
    rows = [rows[k] for k in sorted(rows)]
    R["features"] = dict(header=head[0]["start"] if head else S["start"] + 0.15, rows=rows,
                         ends=rows[1:] + [S["end"] + 1])
    cs = sc["plan"]["cues"]
    R["plan"] = dict(title=cs[0], pick=cs[1], invest=cs[2] if len(cs) > 2 else None)
    S = sc["contact"]
    head = S["cues"][0]
    wa = next((c for c in S["cues"] if c.get("wa")), None)
    spoken = {c["phone"]: c for c in S["cues"] if "phone" in c}
    call = next((c for c in S["cues"] if "اتصلوا" in c["sub"]), head)
    appear = [at(call, "اتصلوا", 0.3) - 0.1]
    appear += [wa["start"] - 0.1, wa["start"] + 0.1] if wa else [appear[0] + 0.3, appear[0] + 0.5]
    groups, windows = [], []
    for k in range(3):
        c = spoken.get(k)
        groups.append(group_times(c) if c else [appear[k] + 0.35 + 0.22 * g for g in range(4)])
        windows.append((c["start"], c["end"]) if c else None)
    R["contact"] = dict(head=head, appear=appear, groups=groups, windows=windows)
    cs = sc["outro"]["cues"]
    R["outro"] = dict(l1=cs[0], l2=cs[1] if len(cs) > 1 else None, endcard=tl["vo_end"] + 0.25)
    return R


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
