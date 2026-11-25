"""Automated checks on a rendered MP4. Writes <name>.qa_report.md next to it."""
import json, os, re, subprocess


def _err(cmd):
    return subprocess.run(cmd, capture_output=True, text=True).stderr


def _check_srt(path):
    """Look for malformed, non-monotonic or overlapping timestamps in an .srt file."""
    if not os.path.exists(path):
        return [f"subtitle file is missing: {os.path.basename(path)}"]
    txt = open(path, encoding="utf-8").read()
    problems = []
    prev_end = -1.0
    blocks = [b for b in txt.strip().split("\n\n") if b.strip()]
    if not blocks:
        return ["subtitle file is empty"]
    for b in blocks:
        m = re.search(r"(\d\d):(\d\d):(\d\d),(\d\d\d)\s*-->\s*(\d\d):(\d\d):(\d\d),(\d\d\d)", b)
        if not m:
            problems.append("a subtitle block has a malformed or missing timestamp line")
            continue
        h1, m1, s1, ms1, h2, m2, s2, ms2 = (int(x) for x in m.groups())
        a = h1 * 3600 + m1 * 60 + s1 + ms1 / 1000
        bnd = h2 * 3600 + m2 * 60 + s2 + ms2 / 1000
        if bnd <= a:
            problems.append(f"a subtitle's end time is not after its start time ({a:.2f}-{bnd:.2f}s)")
        if a < prev_end - 0.01:
            problems.append(f"a subtitle overlaps the previous one (starts at {a:.2f}s)")
        prev_end = bnd
    return problems


def check(cfg, mp4, T=None):
    from .captions import status, srt_path
    from .config import resolve
    r = {"file": os.path.basename(mp4)}
    pr = json.loads(subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                                    "format=duration:stream=codec_type,width,height,r_frame_rate,nb_frames",
                                    "-of", "json", mp4], capture_output=True, text=True).stdout)
    v = [s for s in pr["streams"] if s["codec_type"] == "video"][0]
    r["resolution"] = f"{v['width']}x{v['height']}"; r["fps"] = v["r_frame_rate"]
    r["duration_s"] = round(float(pr["format"]["duration"]), 2)
    r["has_audio"] = any(s["codec_type"] == "audio" for s in pr["streams"])
    dec = subprocess.run(["ffmpeg", "-v", "error", "-i", mp4, "-f", "null", "-"], capture_output=True, text=True)
    r["decodes_cleanly"] = dec.returncode == 0 and not dec.stderr.strip()
    fz = re.findall(r"freeze_duration: ([\d.]+)", _err(["ffmpeg", "-i", mp4, "-vf", "scale=480:-1,freezedetect=n=0.0005:d=2.0",
                                                     "-map", "0:v", "-f", "null", "-"]))
    r["frozen_spans_over_2s"] = [float(x) for x in fz]
    issues = []
    if r["resolution"] != "1920x1080" and "preview" not in mp4: issues.append("resolution is not 1920x1080")
    if not r["decodes_cleanly"]: issues.append("decode errors")
    if r["frozen_spans_over_2s"]: issues.append("frozen picture for over 2 s (intended holds are fine; check them)")
    narration_audio = resolve(cfg, cfg["narration"]["audio"])
    if narration_audio and not r["has_audio"]:
        issues.append("narration.audio is set, but the rendered file has no audio stream at all")
    if r["has_audio"]:
        a = _err(["ffmpeg", "-i", mp4, "-af", "ebur128=peak=true", "-f", "null", "-"])
        I = re.findall(r"I:\s+([-\d.]+) LUFS", a); P = re.findall(r"Peak:\s+([-\d.]+) dBFS", a)
        r["loudness_lufs"] = float(I[-1]) if I else None; r["true_peak_dbfs"] = float(P[-1]) if P else None
        if r["true_peak_dbfs"] is not None and r["true_peak_dbfs"] > -0.5: issues.append("audio may clip")
        sil = re.findall(r"silence_start: ([\d.]+)", _err(["ffmpeg", "-i", mp4, "-af", "silencedetect=n=-45dB:d=1.5",
                                                           "-f", "null", "-"]))
        r["silences_over_1_5s_start"] = [float(x) for x in sil]
    if T is not None and abs(T.duration - r["duration_s"]) > 0.2:
        issues.append(f"duration {r['duration_s']} s differs from the plan ({T.duration:.2f} s) "
                       "- narration may have been cut off or padded")
    if T is not None and getattr(T, "alignment_warning", None):
        issues.append(f"timing is ESTIMATED, not aligned to real audio: {T.alignment_warning}")
    r["caption_status"] = status(cfg)
    if narration_audio and cfg["narration"]["script"] and T is not None:
        try:
            from . import align
            from .render import work_dir
            wav = os.path.join(work_dir(cfg), "narration_16k.wav")
            if not os.path.exists(wav):
                align.to_wav(narration_audio, wav)
            raw = {k: [(w, a - T.audio_offset, b - T.audio_offset) for w, a, b in v] for k, v in T.words.items()}
            ev = align.verify(cfg["narration"]["script"], wav, raw)
            r["possible_missing_words"] = len(ev["possible_mismatch"])
            if ev["possible_mismatch"]:
                issues.append(f"{len(ev['possible_mismatch'])} possible missing word(s) in the narration audio "
                              "- run verify-captions for details")
        except Exception as e:
            r["missing_word_check_error"] = str(e)
    srt = srt_path(cfg)
    if os.path.exists(srt):
        srt_problems = _check_srt(srt)
        r["subtitle_file"] = os.path.basename(srt)
        issues += [f"subtitle timing: {sp}" for sp in srt_problems]
    r["issues"] = issues
    lines = [f"# QA report: {r['file']}", ""] + [f"- **{k}**: {v}" for k, v in r.items() if k != "issues"]
    lines += ["", "## Issues", *(f"- ⚠ {i}" for i in issues)] if issues else ["", "## Issues", "- none detected automatically"]
    lines += ["", "Automated checks cannot judge meaning, accuracy or taste: **watch the whole video with sound.**"]
    if r["has_audio"] and not r["caption_status"].startswith("VERIFIED"):
        lines += ["", "⚠ **Captions are NOT verified.** Run `verify-captions`, listen, then `approve-captions`."]
    p = os.path.splitext(mp4)[0] + ".qa_report.md"
    open(p, "w").write("\n".join(lines) + "\n")
    return r, p
