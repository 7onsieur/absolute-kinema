"""Forced alignment of the narration script to a recording (PocketSphinx, offline)
and evidence-gathering for caption verification.

Alignment *trusts the script*: if the speaker ad-libbed, aligned times are still
produced, but are wrong. verify() therefore looks for evidence of mismatch:
  1. voiced speech not covered by any aligned word  -> probable missing words
  2. per-sentence free recognition for a human to compare with the script
A human must listen and approve before captions are called accurate.
"""
import os, re, subprocess, wave, json
import numpy as np

SR = 16000


def to_wav(src, dst):
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", src, "-ac", "1", "-ar", str(SR), dst], check=True)
    return dst


def _read(wav):
    with wave.open(wav) as w:
        return np.frombuffer(w.readframes(w.getnframes()), np.int16)


def spoken_tokens(script):
    """(sid, word_index, token) — `spoken:` in a sentence overrides how a word is said,
    e.g. spoken: {"SKILL.md": "skill dot m d", "AI": "a i"}"""
    out = []
    for s in script:
        over = {k.lower(): v for k, v in (s.get("spoken") or {}).items()}
        for i, w in enumerate(str(s["text"]).split()):
            key = re.sub(r"[^\w'.]", "", w.lower()).strip(".")
            say = over.get(key) or over.get(w.lower())
            toks = say.split() if say else [re.sub(r"[^a-z']", "", key.replace(".", " "))]
            for t in toks:
                t = re.sub(r"[^a-z']", "", t.lower())
                if t: out.append((str(s["id"]), i, t))
    return out


def align(script, wav):
    from pocketsphinx import Decoder
    d = Decoder(bestpath=False)
    toks = spoken_tokens(script)
    oov = sorted({t for _, _, t in toks if not d.lookup_word(t)})
    if oov:
        raise ValueError("These words are not in the pronunciation dictionary: " + ", ".join(oov) +
                         ". Add a 'spoken:' entry to the sentence, writing each word as it sounds "
                         "(e.g. spoken: {GitHub: git hub}).")
    d.set_align_text(" ".join(t for _, _, t in toks))
    x = _read(wav)
    d.start_utt(); d.process_raw(x.tobytes(), full_utt=True); d.end_utt()
    segs = [(re.sub(r"\(\d+\)$", "", s.word), s.start_frame / 100, (s.end_frame + 1) / 100) for s in d.seg()
            if s.word not in ("<s>", "</s>", "<sil>", "[NOISE]")]
    if len(segs) != len(toks):
        raise RuntimeError(f"alignment returned {len(segs)} tokens for {len(toks)} script tokens")
    res = {}
    for (sid, i, _), (_, a, b) in zip(toks, segs):
        if (sid, i) in res: res[(sid, i)][1] = b
        else: res[(sid, i)] = [a, b]
    words = {}
    for s in script:
        ws = []
        for i, w in enumerate(str(s["text"]).split()):
            a, b = res[(str(s["id"]), i)]
            ws.append((w, a, b))
        ws[-1] = (ws[-1][0], ws[-1][1], min(ws[-1][2], ws[-1][1] + 0.6))  # don't swallow pauses
        words[str(s["id"])] = ws
    return words


def align_segments(script, wav16k, boundaries):
    """Like align(), but `boundaries` ({sid: [start_s, end_s]}, already known exactly - see
    ae/tts.py's spans.json) lets each sentence's audio be aligned on its own slice, instead of
    one whole-file forced alignment across the whole script. Used for AI-generated narration:
    PocketSphinx's forced-alignment grammar can fail ("Final result does not match the
    grammar") when it hits the silences inserted between synthesized sentences, which a
    whole-file pass has to cross but a per-sentence pass never sees. Human recordings don't
    have this problem (natural pauses are shorter and the grammar tolerates them), so align()
    is still used for those."""
    from pocketsphinx import Decoder
    d0 = Decoder(bestpath=False)
    oov = sorted({t for _, _, t in spoken_tokens(script) if not d0.lookup_word(t)})
    if oov:
        raise ValueError("These words are not in the pronunciation dictionary: " + ", ".join(oov) +
                         ". Add a 'spoken:' entry to the sentence, writing each word as it sounds "
                         "(e.g. spoken: {GitHub: git hub}).")
    x = _read(wav16k)
    words = {}
    for s in script:
        sid = str(s["id"])
        if sid not in boundaries:
            raise RuntimeError(f"no AI-narration audio boundary recorded for sentence '{sid}' - "
                                "the narration may need regenerating (delete the work/ cache and re-run).")
        a0, b0 = boundaries[sid]
        pad = 0.25
        lo = max(0, int((a0 - pad) * SR)); hi = min(len(x), int((b0 + pad) * SR))
        triples = spoken_tokens([s])
        toks = [t for (_, _, t) in triples]
        d = Decoder(bestpath=False)
        d.set_align_text(" ".join(toks))
        d.start_utt(); d.process_raw(x[lo:hi].tobytes(), full_utt=True); d.end_utt()
        segs = [(re.sub(r"\(\d+\)$", "", sg.word), lo / SR + sg.start_frame / 100, lo / SR + (sg.end_frame + 1) / 100)
                for sg in d.seg() if sg.word not in ("<s>", "</s>", "<sil>", "[NOISE]")]
        if len(segs) != len(toks):
            raise RuntimeError(f"alignment returned {len(segs)} tokens for {len(toks)} script tokens "
                                f"in sentence '{sid}' (AI-narration per-sentence alignment)")
        res = {}
        for (_, i, _), (_, a, b) in zip(triples, segs):
            if i in res: res[i][1] = b
            else: res[i] = [a, b]
        ws = []
        for i, w in enumerate(str(s["text"]).split()):
            a, b = res[i]
            ws.append((w, a, b))
        ws[-1] = (ws[-1][0], ws[-1][1], min(ws[-1][2], ws[-1][1] + 0.6))
        words[sid] = ws
    return words


def _voicing(y):
    y = y.astype(float); y -= y.mean()
    if np.abs(y).max() < 1: return 0.0
    ac = np.correlate(y, y, "full")[len(y) - 1:]; ac /= ac[0] + 1e-9
    return float(ac[int(SR / 300):int(SR / 80)].max())


def verify(script, wav, words):
    """Return a dict of evidence for caption review."""
    x = _read(wav).astype(np.float32) / 32768
    hop = SR // 100; nfr = len(x) // hop
    rms = np.sqrt(np.convolve(x ** 2, np.ones(hop * 3) / (hop * 3), "same")[::hop][:nfr] + 1e-12)
    db = 20 * np.log10(rms + 1e-9)
    thr = np.percentile(db, 10) + 0.3 * (np.percentile(db, 97) - np.percentile(db, 10))
    speech = db > thr
    cov = np.zeros(nfr, bool)
    for ws in words.values():
        for _, a, b in ws: cov[int(a * 100):int(b * 100) + 1] = True
    unc = speech & ~cov; runs = []; i = 0
    while i < nfr:
        if unc[i]:
            j = i
            while j < nfr and unc[j]: j += 1
            if j - i >= 15:
                a, b = i / 100, j / 100
                v = _voicing((x[int(a * SR):int(b * SR)] * 32768).astype(np.int16))
                runs.append({"start": a, "end": b, "voicing": round(v, 2),
                             "likely": "missing word(s)" if v >= 0.22 and b - a >= 0.25 else "breath / noise"})
            i = j
        else:
            i += 1
    # per-sentence free recognition (rough; accent-sensitive)
    heard = {}
    try:
        from pocketsphinx import Decoder
        d = Decoder(); raw = _read(wav).tobytes()
        for s in script:
            ws = words[str(s["id"])]; a = max(0, ws[0][1] - 0.15); b = ws[-1][2] + 0.15
            d.start_utt(); d.process_raw(raw[int(a * SR) * 2:int(b * SR) * 2], full_utt=True); d.end_utt()
            heard[str(s["id"])] = d.hyp().hypstr if d.hyp() else ""
    except Exception as e:
        heard = {"error": str(e)}
    return {"uncovered_speech": runs, "heard": heard,
            "possible_mismatch": [r for r in runs if r["likely"] == "missing word(s)"]}
