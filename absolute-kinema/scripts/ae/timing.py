"""Narration-driven timing: word times (estimated, or aligned to a recording),
scene spans, element cue times, caption chunks and SRT output."""
import re

FUNCTION_WORDS = {"a", "an", "the", "to", "of", "or", "and", "with", "for", "in", "on", "at", "by", "my",
                  "your", "its", "it", "is", "are", "how", "what", "that", "this", "as", "from", "but"}


def syllables(w):
    w = re.sub(r"[^a-z]", "", w.lower())
    if not w: return 1
    n = len(re.findall(r"[aeiouy]+", w))
    if w.endswith("e") and n > 1 and not w.endswith("le"): n -= 1
    return max(1, n)


def estimate_words(script, start=0.6):
    """Natural speaking-rate estimate when no recording exists."""
    words = {}; t = start
    for s in script:
        out = []
        for w in str(s["text"]).split():
            d = 0.075 + 0.17 * syllables(w)
            out.append((w, t, t + d)); t += d
            if w[-1] in ",;:": t += 0.18
        words[str(s["id"])] = out
        t += 0.45
    return words


class Timing:
    def __init__(self, cfg, aligned_words=None, offset=None):
        """aligned_words: {sid: [(word, t0, t1), ...]} in *audio* time (from align.py)."""
        self.cfg = cfg
        self.fps = cfg["output"]["fps"]
        script = cfg["narration"]["script"] or []
        off = cfg["narration"]["offset"] if offset is None else offset
        if aligned_words:
            self.words = {k: [(w, a + off, b + off) for w, a, b in v] for k, v in aligned_words.items()}
            self.source = "aligned to recording"
        else:
            self.words = estimate_words(script, off) if script else {}
            self.source = "estimated (no recording)" if script else "no narration"
        self.audio_offset = off
        self._scenes()

    # ------------------------------------------------------------ scenes
    def _scenes(self):
        scs = self.cfg["scenes"]; spans = []; t = 0.0
        lead = 0.3
        starts = []
        for sc in scs:
            nar = sc.get("narration") or []
            if isinstance(nar, str): nar = [nar]
            if nar and self.words:
                starts.append(max(0.0, min(self.words[str(n)][0][1] for n in nar) - lead))
            else:
                starts.append(None)
        for i, sc in enumerate(scs):
            s0 = t if i else 0.0
            if starts[i] is not None and i:
                s0 = max(t, starts[i]) if starts[i] > t else t
            if sc.get("duration") and not (sc.get("narration")):
                s1 = s0 + float(sc["duration"])
            else:
                nxt = next((x for x in starts[i + 1:] if x is not None), None)
                nar = sc.get("narration") or []
                if isinstance(nar, str): nar = [nar]
                last = max(self.words[str(n)][-1][2] for n in nar) if (nar and self.words) else s0 + float(sc.get("duration", 3))
                if sc.get("duration"):
                    last = max(last, s0 + float(sc["duration"]))
                s1 = max(last + 0.25, nxt) if (nxt is not None and i + 1 < len(scs)) else last + 0.25
            spans.append([s0, s1]); t = s1
        if spans:
            spans[-1][1] += float(self.cfg.get("outro_hold", 1.5))
        self.spans = spans
        self.duration = spans[-1][1] if spans else 1.0
        self.nframes = int(round(self.duration * self.fps))

    def scene_at(self, t):
        for i, (a, b) in enumerate(self.spans):
            if a <= t < b: return i
        return len(self.spans) - 1

    def scene_words(self, si):
        nar = self.cfg["scenes"][si].get("narration") or []
        if isinstance(nar, str): nar = [nar]
        out = []
        for n in nar: out += self.words.get(str(n), [])
        return out

    def cue(self, si, spec, default=0.0):
        """Resolve an element time to absolute seconds.
        spec: number (seconds after scene start) | "word" (the word in this scene's narration,
        if it appears exactly once) | "s2" (sentence start) | "word+0.3" (word, offset by 0.3s) |
        "word#2" (the 2nd occurrence of a word that appears more than once in the scene).

        A plain word cue ("at: one") that matches more than one word in the scene's narration is
        rejected rather than silently resolved to the first match - repeated words like "one" or
        "year" are a common source of cues silently landing on the wrong moment. Use a sentence id
        (preferred - it can never become ambiguous as the script changes) or "word#N" instead."""
        sid = self.cfg["scenes"][si].get("id", si)
        a, _ = self.spans[si]
        if spec is None: return a + default
        if isinstance(spec, (int, float)): return a + float(spec)
        s = str(spec).strip(); delta = 0.0
        m = re.match(r"^(.*?)([+-]\d+(\.\d+)?)$", s)
        if m and m.group(1): s, delta = m.group(1).strip(), float(m.group(2))
        occurrence = None
        m = re.match(r"^(.*)#(\d+)$", s)
        if m and m.group(1):
            s, occurrence = m.group(1).strip(), int(m.group(2))
            if occurrence < 1:
                raise ValueError(f"cue '{spec}' in scene {sid}: occurrence number after '#' must be 1 or higher.")
        if occurrence is None and s in self.words:
            return self.words[s][0][1] + delta

        def norm(w): return re.sub(r"[^\w']", "", w.lower())

        exact = [(w, t0, t1) for w, t0, t1 in self.scene_words(si) if norm(w) == norm(s)]
        matches = exact or [(w, t0, t1) for w, t0, t1 in self.scene_words(si) if s.lower() in w.lower()]
        if not matches:
            raise ValueError(f"cue '{spec}' not found in the narration of scene {sid}")
        if occurrence is not None:
            if occurrence > len(matches):
                raise ValueError(
                    f"cue '{spec}' in scene {sid}: '{s}' only appears {len(matches)} time(s) in this "
                    f"scene's narration, so '#{occurrence}' doesn't exist.")
            return matches[occurrence - 1][1] + delta
        if len(matches) > 1:
            nar = self.cfg["scenes"][si].get("narration") or []
            if isinstance(nar, str): nar = [nar]
            first_id = nar[0] if nar else None
            hint = f"a sentence id (e.g. at: {first_id!r})" if first_id else "a sentence id"
            raise ValueError(
                f"cue '{spec}' in scene {sid} is ambiguous: '{s}' appears {len(matches)} times in this "
                f"scene's narration. Use {hint}, or pick one with an occurrence number, e.g. "
                f"'at: \"{s}#2\"' for the second occurrence.")
        return matches[0][1] + delta

    # ------------------------------------------------------------ captions
    def caption_chunks(self):
        maxc = int(self.cfg["captions"]["max_chars"]); chunks = []
        for s in self.cfg["narration"]["script"] or []:
            ws = self.words.get(str(s["id"]), [])
            cur = []
            for i, x in enumerate(ws):
                cur.append(x)
                text = " ".join(w for w, _, _ in cur)
                nxt = ws[i + 1][0] if i + 1 < len(ws) else None
                punct = x[0][-1] in ",;:.?!…" and len(cur) >= 3
                too_long = nxt is not None and len(text) + 1 + len(nxt) > maxc
                dangling = re.sub(r"[^\w']", "", x[0].lower()) in FUNCTION_WORDS
                if nxt is None or punct or (too_long and not dangling) or len(text) > maxc + 8:
                    rest = len(ws) - 1 - i
                    if 0 < rest < 2 and not punct: continue   # avoid a one-word orphan line
                    chunks.append(cur); cur = []
            if cur: chunks.append(cur)
        return chunks

    def caption_windows(self):
        ch = self.caption_chunks(); out = []
        for i, c in enumerate(ch):
            a = c[0][1] - 0.1; b = c[-1][2] + 0.45
            if i + 1 < len(ch): b = min(b, ch[i + 1][0][1] - 0.1)
            out.append((c, a, b))
        return out

    def write_srt(self, path):
        def ts(x):
            x = max(0.0, x); h = int(x // 3600); m = int(x % 3600 // 60)
            return ("%02d:%02d:%06.3f" % (h, m, x % 60)).replace(".", ",")
        with open(path, "w", encoding="utf-8") as f:
            for i, (c, a, b) in enumerate(self.caption_windows(), 1):
                f.write(f"{i}\n{ts(a)} --> {ts(b)}\n{' '.join(w for w, _, _ in c)}\n\n")
