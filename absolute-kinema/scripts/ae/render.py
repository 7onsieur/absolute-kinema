"""Memory-bounded, resumable rendering.

Design (lessons from the original project's V1/V2 renders, where long-lived pool
workers leaked memory, were OOM-killed and deadlocked multiprocessing.Pool):
  * the film is split into short segments (default 2 s)
  * each segment is rendered by a *fresh* subprocess that exits afterwards, with a
    memory ceiling (RLIMIT_AS) and single-threaded maths libraries
  * frames are piped straight into ffmpeg -> one small MP4 per segment
    (no gigabytes of PNG frames)
  * a segment is written to a temp name and renamed only when complete, so a rerun
    skips finished segments (resume) and retries failed ones (up to 2 retries)
  * timing / alignment is computed once and cached for all workers
"""
import os, sys, json, time, subprocess, hashlib, wave

HERE = os.path.dirname(os.path.abspath(__file__))


def _prepend_silence_wav(in_path, offset_s, out_path):
    """Prepend `offset_s` seconds of true zero-valued PCM samples to the WAV at `in_path`,
    writing the result to `out_path`. This bakes the narration lead-in into the actual audio
    data, so it is real silence any decoder will play back, rather than an MP4 container-level
    start_time/edit-list trick that a decoder which ignores container timestamps (and plenty of
    real-world tools do) could skip straight past - found and fixed as a v0.4-rc1 release
    blocker from an independent fresh-session test. See test_lead_in_silence_is_real_audio_
    samples_not_a_container_trick in tests/test_ae.py, which verifies this by reading raw decoded
    samples rather than trusting any timestamp."""
    with wave.open(in_path, "rb") as r:
        params = r.getparams()
        sr, ch, sw = r.getframerate(), r.getnchannels(), r.getsampwidth()
        frames = r.readframes(r.getnframes())
    n_silence_frames = max(0, int(round(offset_s * sr)))
    silence = b"\x00" * (n_silence_frames * ch * sw)
    with wave.open(out_path, "wb") as w:
        w.setparams(params)
        w.writeframes(silence + frames)
    return out_path


def work_dir(cfg):
    d = os.path.join(cfg["_dir"], "work", cfg["output"]["name"]); os.makedirs(d, exist_ok=True); return d


def out_dir(cfg):
    d = os.path.join(cfg["_dir"], "output"); os.makedirs(d, exist_ok=True); return d


def file_hash(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""): h.update(b)
    return h.hexdigest()


def script_hash(cfg):
    return hashlib.sha256(json.dumps(cfg["narration"]["script"], sort_keys=True).encode()).hexdigest()


def _audio_duration_s(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                           "-of", "csv=p=0", path], capture_output=True, text=True).stdout.strip()
    try:
        return float(out)
    except ValueError:
        return None


# ---------------------------------------------------------------- timing cache
def build_timing(cfg, log=print):
    """Compute (or load cached) timing. Alignment runs only when audio is supplied."""
    from .timing import Timing
    from .config import resolve
    wd = work_dir(cfg); cache = os.path.join(wd, "timing.json")
    audio = resolve(cfg, cfg["narration"]["audio"])
    key = {"script": script_hash(cfg), "audio": file_hash(audio) if audio else None,
           "offset": cfg["narration"]["offset"]}
    if os.path.exists(cache):
        c = json.load(open(cache))
        if c.get("key") == key:
            T = Timing(cfg, c.get("aligned"), c.get("offset"))
            T.alignment_warning = c.get("alignment_warning")
            # Restore the specific provenance label (e.g. "exact (from TTS engine's own
            # duration output)") from the cache. Timing.__init__ always sets self.source to the
            # generic "aligned to recording" whenever aligned_words is truthy, which would
            # otherwise silently overwrite a more specific label on every cache hit - found and
            # fixed during v0.4 development (see CAPTION_DRIFT_FIX_v0.4.md §4). The underlying
            # word times are unaffected either way; this only fixes what the label says.
            if c.get("source"): T.source = c["source"]
            if T.alignment_warning: T.source = "estimated (alignment failed - see warning)"
            return T
    aligned = None
    alignment_warning = None
    if audio:
        from . import align
        # If a sidecar with word timing already computed exists next to the audio - e.g. read
        # straight from a neural TTS engine's own duration predictor (ae.kokoro_tts), rather
        # than inferred after the fact by a separate alignment tool - use it directly and skip
        # alignment entirely. This is exact by construction: the timing comes from the same
        # forward pass that produced the audio, not a recognition step that can mis-hear it, and
        # it sidesteps PocketSphinx's British-voice alignment failures entirely (see
        # DEVELOPMENT_REPORT_v0.3.md and V0.4_RELEASE_REPORT.md).
        word_timing_file = audio + ".word_timing.json"
        if os.path.exists(word_timing_file):
            log("Using precomputed word timing from the TTS engine's own duration output "
                "(no forced alignment needed) …")
            raw = json.load(open(word_timing_file))
            # Each word entry is [word, t0, t1] or, from ae.kokoro_tts, [word, t0, t1, confidence]
            # where confidence is "exact" or "estimated (...)" (see kokoro_tts.sentence_word_timing).
            # Timing() only wants the first three fields; the confidence (when present) is used
            # below to distinguish FULLY exact timing from timing where a merged-phoneme-group
            # pair/run got a localized estimate - a v0.4-rc1 validation gap (both cases claimed
            # plain "exact" in validate's output) found by an independent fresh-session test.
            aligned = {sid: [tuple(w[:3]) for w in ws] for sid, ws in raw.items()}
            confidences = [w[3] if len(w) > 3 else "exact" for ws in raw.values() for w in ws]
            T = Timing(cfg, aligned)
            T.alignment_warning = None
            n_total = len(confidences); n_exact = sum(1 for c in confidences if c == "exact")
            if n_total and n_exact < n_total:
                T.source = (f"exact for {n_exact}/{n_total} words (from TTS engine's own duration "
                            f"output); {n_total - n_exact} word(s) partially estimated - see SKILL.md "
                            f"'AI narration' (merged phoneme groups)")
            else:
                T.source = "exact (from TTS engine's own duration output)"
            real_dur = _audio_duration_s(audio)
            outro = float(cfg.get("outro_hold", 1.5))
            if real_dur is not None:
                needed = real_dur + T.audio_offset + outro
                if needed > T.duration + 0.05:
                    extra = needed - T.duration
                    T.spans[-1][1] += extra; T.duration += extra
                    T.nframes = int(round(T.duration * T.fps))
            json.dump({"key": key, "aligned": aligned, "offset": T.audio_offset, "source": T.source,
                       "spans": T.spans, "duration": T.duration, "alignment_warning": None},
                       open(cache, "w"), indent=1)
            return T
        wav = align.to_wav(audio, os.path.join(wd, "narration_16k.wav"))
        spans_file = audio + ".spans.json"
        try:
            if os.path.exists(spans_file):
                # AI-generated narration (ae/tts.py) knows exactly where each sentence's audio
                # is, so align each sentence separately rather than risk a whole-file forced
                # alignment across the silences it inserted between sentences - see
                # align.align_segments.
                log("Aligning the script to the AI narration, sentence by sentence (PocketSphinx)…")
                boundaries = json.load(open(spans_file))
                aligned = align.align_segments(cfg["narration"]["script"], wav, boundaries)
            else:
                log("Aligning the script to the recording (PocketSphinx)…")
                aligned = align.align(cfg["narration"]["script"], wav)
        except (RuntimeError, TypeError) as e:
            # Verified finding (see DEVELOPMENT_REPORT_v0.3.md): PocketSphinx's forced-alignment
            # grammar can fail outright on some TTS voices - in testing, every espeak-ng British
            # English voice tried failed forced alignment against PocketSphinx's (American
            # English) acoustic model, while an American voice aligned reliably. Falling back to
            # estimated word timing keeps the pipeline usable rather than crashing, but this is
            # NOT the same guarantee as real alignment - say so loudly, in the render log, the QA
            # report and the caption status, rather than silently pretending captions are
            # audio-verified. The audio itself (what is actually spoken) is unaffected.
            alignment_warning = (f"Could not align the narration audio to the script ({type(e).__name__}: {e}). "
                                 "Falling back to ESTIMATED word timing for captions/cues - captions may drift "
                                 "out of sync with the real audio. See SKILL.md 'Limitations'. Known trigger: "
                                 "espeak-ng British English voices with this project's PocketSphinx version.")
            log(f"⚠ {alignment_warning}")
    T = Timing(cfg, aligned)
    if alignment_warning:
        T.source = "estimated (alignment failed - see warning)"
    T.alignment_warning = alignment_warning
    # Safety net for requirement "don't cut off speech": if the real narration audio is longer
    # than the timing we ended up with (estimate or alignment can both under-shoot), extend the
    # last scene so the final mux (which trims audio to T.duration) never truncates real speech.
    if audio:
        real_dur = _audio_duration_s(audio)
        outro = float(cfg.get("outro_hold", 1.5))
        if real_dur is not None:
            needed = real_dur + T.audio_offset + outro
            if needed > T.duration + 0.05:
                extra = needed - T.duration
                T.spans[-1][1] += extra; T.duration += extra; T.nframes = int(round(T.duration * T.fps))
                log(f"  extended duration by {extra:.2f}s so the narration audio ({real_dur:.2f}s) isn't cut off")
    json.dump({"key": key, "aligned": aligned, "offset": T.audio_offset, "source": T.source,
               "spans": T.spans, "duration": T.duration, "alignment_warning": alignment_warning},
               open(cache, "w"), indent=1)
    return T


# ---------------------------------------------------------------- segment worker
def _limit_memory(gb):
    try:
        import resource
        b = int(gb * 1024 ** 3); resource.setrlimit(resource.RLIMIT_AS, (b, b))
    except Exception:
        pass   # not available on this OS; segments are still short-lived


def segment_main(project, idx, f0, f1, out_path, scale):
    """Entry point of a worker subprocess: render frames [f0, f1) to out_path."""
    from .config import load
    cfg = load(project)
    _limit_memory(float(cfg["render"]["memory_limit_gb"]))
    import cv2; cv2.setNumThreads(1)
    from . import scene
    T = build_timing(cfg, log=lambda *a: None)
    windows = T.caption_windows() if cfg["narration"]["script"] else []
    fps = cfg["output"]["fps"]; W, H = int(1920 * scale), int(1080 * scale)
    tmp = out_path + ".part.mp4"
    p = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
                          "-r", str(fps), "-i", "-", "-c:v", "libx264", "-preset", "medium", "-crf", "15",
                          "-pix_fmt", "yuv420p", "-g", str(fps), "-bf", "0", tmp], stdin=subprocess.PIPE)
    for fi in range(f0, f1):
        p.stdin.write(scene.frame(cfg, T, windows, fi / fps, scale).tobytes())
    p.stdin.close()
    if p.wait() != 0: raise RuntimeError("ffmpeg failed")
    os.replace(tmp, out_path)


# ---------------------------------------------------------------- orchestration
def _render_key(cfg, T, scale):
    """Everything that can change what a rendered segment should contain: the project file
    itself (scenes, style, captions, narration settings - any of it), the actual narration audio
    bytes (covers re-synthesizing with the same script but a different voice/engine/model), the
    resolved timing (source label + duration), the render scale and the fps. Segment caching
    (render()'s resumable-render feature, by design) is keyed on this rather than on file
    existence alone, so a changed narration, timing or config can never silently reuse an
    outdated video segment - found and fixed during v0.4 development after it happened in this
    project's own testing (see CAPTION_DRIFT_FIX_v0.4.md §4)."""
    from .config import resolve
    audio = resolve(cfg, cfg["narration"]["audio"])
    return {"project_file": file_hash(cfg["_path"]), "audio": file_hash(audio) if audio else None,
            "timing_source": T.source, "duration": round(T.duration, 3), "scale": scale,
            "fps": cfg["output"]["fps"]}


def render(cfg, scale=1.0, log=print):
    t_start = time.time()
    T = build_timing(cfg, log)
    fps = cfg["output"]["fps"]; n = T.nframes
    seg = max(fps, int(float(cfg["render"]["segment_seconds"]) * fps))
    tag = "full" if scale >= 1 else f"s{scale:g}"
    wd = work_dir(cfg)
    sd = os.path.join(wd, f"segments_{tag}"); os.makedirs(sd, exist_ok=True)
    render_key = _render_key(cfg, T, scale)
    key_path = os.path.join(sd, "render_key.json")
    try:
        stale = json.load(open(key_path)) != render_key
    except Exception:
        stale = True
    if stale:
        existing = [f for f in os.listdir(sd) if f.endswith(".mp4")]
        if existing:
            for f in existing:
                os.remove(os.path.join(sd, f))
            log(f"  narration, timing or config changed since this project's last render here - "
                f"cleared {len(existing)} cached segment(s) so nothing stale is reused.")
        json.dump(render_key, open(key_path, "w"))
    jobs = [(i, f0, min(n, f0 + seg), os.path.join(sd, f"seg_{i:04d}.mp4")) for i, f0 in enumerate(range(0, n, seg))]
    todo = [j for j in jobs if not os.path.exists(j[3])]
    workers = int(cfg["render"]["workers"]) or max(1, min(4, (os.cpu_count() or 2)))
    log(f"Duration {T.duration:.2f} s, {n} frames, {len(jobs)} segments "
        f"({len(jobs) - len(todo)} already done), {workers} workers, timing: {T.source}")
    env = dict(os.environ, OMP_NUM_THREADS="1", OPENBLAS_NUM_THREADS="1", MKL_NUM_THREADS="1")
    running = {}; tries = {j[0]: 0 for j in todo}; failed = []
    queue = list(todo)
    while queue or running:
        while queue and len(running) < workers:
            j = queue.pop(0)
            cmd = [sys.executable, "-c",
                   f"import sys; sys.path.insert(0, {os.path.dirname(HERE)!r}); from ae.render import segment_main; "
                   f"segment_main({cfg['_path']!r}, {j[0]}, {j[1]}, {j[2]}, {j[3]!r}, {scale})"]
            running[j[0]] = (subprocess.Popen(cmd, env=env, stderr=subprocess.PIPE, text=True), j)
        time.sleep(0.2)
        for k in list(running):
            pr, j = running[k]
            if pr.poll() is None: continue
            err = pr.stderr.read(); del running[k]
            if pr.returncode != 0 or not os.path.exists(j[3]):
                tries[k] += 1
                if tries[k] <= 2:
                    log(f"  segment {k} failed (exit {pr.returncode}); retrying ({tries[k]}/2)"); queue.append(j)
                else:
                    failed.append((k, err[-600:]))
            else:
                done = sum(os.path.exists(x[3]) for x in jobs)
                log(f"  segment {k + 1}/{len(jobs)} done  ({done}/{len(jobs)})")
    if failed:
        raise RuntimeError("Segments failed after retries: " + "; ".join(f"#{k}: {e}" for k, e in failed) +
                           "\nRe-run the same command to resume; finished segments are kept.")
    # concatenate (stream copy) and mux narration
    lst = os.path.join(sd, "list.txt")
    open(lst, "w").write("".join(f"file '{os.path.basename(j[3])}'\n" for j in jobs))
    silent = os.path.join(work_dir(cfg), f"video_{tag}.mp4")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", silent], check=True)
    name = cfg["output"]["name"] + ("" if scale >= 1 else f"_preview{int(1080 * scale)}p")
    final = os.path.join(out_dir(cfg), name + ".mp4")
    from .config import resolve
    audio = resolve(cfg, cfg["narration"]["audio"])
    if audio:
        off = T.audio_offset; D = T.duration
        # Normalize the narration first (no delay yet - that step must only ever touch real PCM
        # samples, not a filter the container/encoder could optimize away as a timestamp).
        norm_wav = os.path.join(wd, f"narration_normalized_{tag}.wav")
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", audio,
                        "-af", "highpass=f=60,loudnorm=I=-16:TP=-1.5:LRA=11",
                        "-ar", "48000", "-sample_fmt", "s16", norm_wav], check=True)
        # Bake the lead-in silence into real samples (see _prepend_silence_wav) rather than
        # delaying the audio via a filter/container mechanism at mux time.
        leadin_wav = os.path.join(wd, f"narration_leadin_{tag}.wav")
        _prepend_silence_wav(norm_wav, off, leadin_wav)
        af = f"apad,atrim=0:{D:.3f},afade=t=out:st={max(0, D - 0.6):.3f}:d=0.6"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", silent, "-i", leadin_wav, "-filter_complex", f"[1:a]{af}[a]",
                        "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
                        "-movflags", "+faststart", "-shortest", final], check=True)
    else:
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", silent, "-c", "copy", "-movflags", "+faststart", final], check=True)
    srt = None
    if audio and cfg["narration"]["script"] and scale >= 1:
        from .captions import srt_path
        srt = srt_path(cfg); T.write_srt(srt)
    took = time.time() - t_start
    log(f"Wrote {final}" + (f" and {srt}" if srt else "") + f"  ({took:.0f} s)")
    return final, srt, took
