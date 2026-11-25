"""Caption verification workflow.

Captions are never declared accurate automatically. The status is:
  NOT VERIFIED -> (verify-captions: evidence report) -> human listens and runs
  approve-captions -> VERIFIED (bound to the exact audio file and script text).
Changing the audio or the script invalidates the approval automatically.
"""
import os, json, datetime
from .render import work_dir, out_dir, file_hash, script_hash, build_timing
from .config import resolve


def approval_path(cfg):
    return os.path.join(cfg["_dir"], f"{cfg['output']['name']}.captions_approval.json")


def status(cfg):
    audio = resolve(cfg, cfg["narration"]["audio"])
    if not audio: return "NO NARRATION (no SRT is produced)"
    p = approval_path(cfg)
    if not os.path.exists(p): return "NOT VERIFIED"
    a = json.load(open(p))
    if a.get("audio_sha256") != file_hash(audio) or a.get("script_sha256") != script_hash(cfg):
        return "NOT VERIFIED (approval is out of date: audio or script changed since approval)"
    return f"VERIFIED by {a['approved_by']} on {a['approved_at']}"


def srt_path(cfg):
    base = os.path.join(out_dir(cfg), cfg["output"]["name"])
    return base + (".srt" if status(cfg).startswith("VERIFIED") else ".UNVERIFIED.srt")


def verify(cfg, log=print):
    from . import align
    audio = resolve(cfg, cfg["narration"]["audio"])
    if not audio: raise SystemExit("verify-captions needs narration.audio in the project file.")
    T = build_timing(cfg, log)
    wav = os.path.join(work_dir(cfg), "narration_16k.wav")
    if not os.path.exists(wav): align.to_wav(audio, wav)
    raw = {k: [(w, a - T.audio_offset, b - T.audio_offset) for w, a, b in v] for k, v in T.words.items()}
    ev = align.verify(cfg["narration"]["script"], wav, raw)
    rep = [f"# Caption review: {cfg['title']}", "",
           f"**Status: {status(cfg)}**", "",
           "Captions are only accurate if the script matches what is said, word for word.",
           "The checks below look for evidence of mismatch; **a person must still listen.**", "",
           "## 1. Possible missing words (voiced speech no script word accounts for)"]
    if ev["possible_mismatch"]:
        for r in ev["possible_mismatch"]:
            rep.append(f"- ⚠ {r['start']:.2f}–{r['end']:.2f} s in the recording (voicing {r['voicing']}). "
                       "Listen here: if a word is said that is not in the script, add it to narration.script.")
    else:
        rep.append("- None found. (Short unvoiced gaps, i.e. breaths, are listed below for completeness.)")
    for r in ev["uncovered_speech"]:
        if r not in ev["possible_mismatch"]:
            rep.append(f"  - {r['start']:.2f}–{r['end']:.2f} s: {r['likely']} (voicing {r['voicing']})")
    rep += ["", "## 2. Script vs what a small offline recogniser heard",
            "The recogniser is rough (accents confuse it). Look for *extra or different words*, not spelling."]
    for s in cfg["narration"]["script"]:
        rep.append(f"- **{s['id']}** script: {s['text']}\n  - heard: {ev['heard'].get(str(s['id']), '')}")
    rep += ["", "## 3. Captions with timings (film time)"]
    for c, a, b in T.caption_windows():
        rep.append(f"- {a:6.2f}–{b:6.2f}  {' '.join(w for w, _, _ in c)}")
    rep += ["", "## 4. Human approval",
            "Watch the rendered video with sound and read every caption. If they all match, run:",
            "", f"    python3 scripts/make_video.py approve-captions {os.path.relpath(cfg['_path'])} --name \"Your Name\"", "",
            "Approval is tied to this exact recording and script; editing either resets the status."]
    p = os.path.join(out_dir(cfg), f"{cfg['output']['name']}.captions_review.md")
    open(p, "w").write("\n".join(rep) + "\n")
    log(f"Wrote {p}")
    return p, ev


def approve(cfg, name):
    audio = resolve(cfg, cfg["narration"]["audio"])
    if not audio: raise SystemExit("Nothing to approve: no narration.audio.")
    rec = {"approved_by": name, "approved_at": datetime.datetime.now().isoformat(timespec="seconds"),
           "audio_file": os.path.basename(audio), "audio_sha256": file_hash(audio), "script_sha256": script_hash(cfg),
           "statement": "I listened to the narration and confirm every caption matches what is said."}
    json.dump(rec, open(approval_path(cfg), "w"), indent=1)
    old = os.path.join(out_dir(cfg), cfg["output"]["name"] + ".UNVERIFIED.srt")
    if os.path.exists(old):
        os.replace(old, os.path.join(out_dir(cfg), cfg["output"]["name"] + ".srt"))
    return approval_path(cfg)
