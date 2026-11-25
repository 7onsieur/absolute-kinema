"""Local, free text-to-speech narration generation.

Two engines are supported:

  - "espeak" (default) - eSpeak NG, a free (GPL-3.0), fully offline, rule-based formant
    synthesiser (https://github.com/espeak-ng/espeak-ng). Verified working end-to-end in this
    project's own development and test environment. Several British English variants are
    available (en-gb, en-gb-x-rp "Received Pronunciation", en-gb-scotland, en-gb-x-gbclan
    "Lancaster", en-gb-x-gbcwmd "West Midlands"). Voice quality is mechanical/robotic, not
    neural - this is the always-available, verified fallback. Install: `apt-get install
    espeak-ng` (see README.md).

  - "piper" - Piper, a free (MIT), local, CPU-fast *neural* TTS engine with much more
    natural-sounding voices, including several good British English ones
    (https://github.com/rhasspy/piper). The `piper-tts` Python package installs cleanly from
    PyPI. Its voice *model* files (.onnx + .onnx.json) are, as far as this project could
    verify, only distributed from Hugging Face (huggingface.co) - see VOICES.md at
    https://github.com/rhasspy/piper/blob/master/VOICES.md for the current list and links.
    huggingface.co was NOT reachable from this project's own development sandbox (confirmed:
    direct requests were rejected by the sandbox's network policy, independently of Piper
    itself) - see DEVELOPMENT_REPORT_v0.3.md for how this was checked. This code path is
    fully implemented and will work in an environment that can reach Hugging Face: download a
    voice's two files, keep them together, and point narration.tts.voice at the .onnx file.
    It is UNTESTED beyond that verification in this project's own environment - say so
    plainly if you use it and haven't verified it yourself.

Both engines produce one mono WAV file for the whole narration script (one synthesis call per
sentence, concatenated with a fixed silence gap), which the rest of the pipeline then treats
exactly like a user's own recording: forced-aligned (ae.align), muxed and captioned
(ae.render, ae.captions) with no special-casing. Caption approval is NOT affected by which
engine produced the audio - see ae/captions.py; this module never marks anything verified.
"""
import json, os, re, shutil, subprocess, wave

import numpy as np

SR_FALLBACK = 22050
SENTENCE_GAP_S = 0.35
ENGINES = ("espeak", "piper", "kokoro")

PIPER_VOICE_HELP = (
    "Piper needs a downloaded voice: get the .onnx and .onnx.json for one voice from "
    "https://github.com/rhasspy/piper/blob/master/VOICES.md (links resolve to Hugging Face), "
    "save them next to each other, and set narration.tts.voice to the .onnx file's path. "
    "If your environment can't reach huggingface.co, use engine: espeak instead - it needs no "
    "download."
)


def apply_spoken_overrides(text, spoken):
    """Replace words with their `spoken:` override, using the same whitespace-token/key
    derivation as ae.align.spoken_tokens, so a TTS engine gets exactly the same hint a human
    aligner does for a tricky word, e.g. spoken: {GitHub: "git hub"}."""
    if not spoken:
        return text
    over = {k.lower(): v for k, v in spoken.items()}
    out = []
    for w in text.split():
        key = re.sub(r"[^\w'.]", "", w.lower()).strip(".")
        say = over.get(key) or over.get(w.lower())
        out.append(say if say else w)
    return " ".join(out)


# ---------------------------------------------------------------- engine discovery
def espeak_available():
    return shutil.which("espeak-ng") is not None


def piper_available():
    return shutil.which("piper") is not None


def espeak_voices():
    """Installed eSpeak NG voices whose language code starts with 'en' -> {voice_id: description}.
    voice_id is the Language column (e.g. "en-gb-x-rp") - what -v expects - not the VoiceName
    column, which espeak-ng also accepts but which is a less standard identifier to document."""
    if not espeak_available():
        return {}
    out = subprocess.run(["espeak-ng", "--voices=en"], capture_output=True, text=True).stdout
    voices = {}
    for line in out.splitlines()[1:]:
        parts = line.split()
        if len(parts) >= 4 and parts[1].startswith("en"):
            voices[parts[1]] = parts[3].replace("_", " ")
    return voices


def list_voices(engine):
    if engine == "espeak":
        return espeak_voices()
    if engine == "piper":
        if not piper_available():
            return {}
        return {"<path-to-voice.onnx>": "point narration.tts.voice at a downloaded Piper "
                                         "voice's .onnx file - see README.md's 'Piper voices'"}
    if engine == "kokoro":
        from . import kokoro_tts
        return kokoro_tts.list_voices()
    raise ValueError(f"unknown TTS engine '{engine}' (use one of {ENGINES}).")


# ---------------------------------------------------------------- synthesis
def _synth_sentence_espeak(text, voice, speed, out_wav):
    if not espeak_available():
        raise RuntimeError("the 'espeak-ng' command was not found. Install it: "
                            "apt-get install espeak-ng (see README.md).")
    wpm = max(80, min(300, int(175 * speed)))
    p = subprocess.run(["espeak-ng", "-v", voice or "en-gb", "-s", str(wpm), "-w", out_wav, text],
                        capture_output=True, text=True)
    if p.returncode != 0 or not os.path.exists(out_wav):
        raise RuntimeError(f"espeak-ng failed on voice '{voice}': {p.stderr.strip()[-500:]}")


def _synth_sentence_piper(text, voice_onnx, speed, out_wav):
    if not piper_available():
        raise RuntimeError("the 'piper' command was not found (pip install piper-tts). " + PIPER_VOICE_HELP)
    if not voice_onnx or not os.path.exists(voice_onnx):
        raise RuntimeError(f"Piper voice file not found: {voice_onnx!r}. " + PIPER_VOICE_HELP)
    cfg_path = voice_onnx + ".json"
    if not os.path.exists(cfg_path):
        raise RuntimeError(f"Piper voice config not found: {cfg_path!r} (expected next to the .onnx). "
                            + PIPER_VOICE_HELP)
    length_scale = 1.0 / max(0.5, min(2.0, speed))
    p = subprocess.run(["piper", "-m", voice_onnx, "-c", cfg_path, "--length-scale", str(length_scale),
                         "-f", out_wav], input=text, capture_output=True, text=True)
    if p.returncode != 0 or not os.path.exists(out_wav):
        raise RuntimeError(f"piper failed: {p.stderr.strip()[-500:]}")


def _wav_rate(path):
    with wave.open(path) as w:
        return w.getframerate()


def _concat_wavs(paths, out_wav, gap_s=SENTENCE_GAP_S):
    """Concatenate per-sentence clips with a fixed silence gap. Returns (out_wav, spans) where
    spans is [(start_s, end_s), ...] in the OUTPUT file's own timeline - exact, because we just
    built it. This is the key fact that lets align.align_segments() align each sentence's audio
    separately instead of a risky whole-file forced alignment across our own inserted silences."""
    if not paths:
        raise ValueError("no audio clips to concatenate")
    rate = _wav_rate(paths[0])
    chunks = []
    spans = []
    t = 0.0
    for i, p in enumerate(paths):
        with wave.open(p) as w:
            if w.getframerate() != rate:
                raise RuntimeError(f"sentence clips have inconsistent sample rates ({w.getframerate()} vs {rate}) "
                                    "- this should not happen with a single engine/voice; report it as a bug.")
            data = np.frombuffer(w.readframes(w.getnframes()), np.int16)
        chunks.append(data)
        dur = len(data) / rate
        spans.append((t, t + dur))
        t += dur
        if i < len(paths) - 1:
            chunks.append(np.zeros(int(gap_s * rate), np.int16))
            t += gap_s
    audio = np.concatenate(chunks)
    with wave.open(out_wav, "w") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(rate)
        w.writeframes(audio.tobytes())
    return out_wav, spans


def synth_script(script, out_wav, engine="espeak", voice=None, speed=1.0, log=print, tmp_dir=None,
                  kokoro_model_dir=None):
    """Synthesize `script` ([{id, text, spoken?}, ...]) to a single mono WAV at out_wav.

    espeak/piper write out_wav + '.spans.json' (sentence audio boundaries - see
    align.align_segments(), which forced-aligns each sentence separately against that). kokoro
    writes out_wav + '.word_timing.json' instead (exact, model-native word timing straight from
    synthesis - see ae/kokoro_tts.py and ae/render.py's build_timing(), which prefers this
    sidecar over alignment whenever it exists). Raises ValueError/RuntimeError with a specific,
    actionable message on failure - never silently falls back to another engine, a paid
    service, or a different voice."""
    if not script:
        raise ValueError("narration.script is empty - nothing to narrate.")
    if engine not in ENGINES:
        raise ValueError(f"unknown TTS engine '{engine}' (use one of {ENGINES}).")
    if not (0.5 <= float(speed) <= 2.0):
        raise ValueError("narration.tts.speed must be between 0.5 and 2.0.")
    if engine == "kokoro":
        from . import kokoro_tts
        return kokoro_tts.synth_script_kokoro(script, out_wav, voice=voice, speed=speed, log=log,
                                               model_dir=kokoro_model_dir)
    tmp_dir = tmp_dir or os.path.dirname(os.path.abspath(out_wav)) or "."
    os.makedirs(tmp_dir, exist_ok=True)
    parts = []
    try:
        for i, s in enumerate(script):
            text = apply_spoken_overrides(str(s["text"]), s.get("spoken"))
            p = os.path.join(tmp_dir, f"_tts_sentence_{i:03d}.wav")
            log(f"  synthesising {s.get('id', i)} ({engine}): "
                f"{text[:60]}{'...' if len(text) > 60 else ''}")
            if engine == "espeak":
                _synth_sentence_espeak(text, voice, speed, p)
            else:
                _synth_sentence_piper(text, voice, speed, p)
            parts.append(p)
        _, spans = _concat_wavs(parts, out_wav)
    finally:
        for p in parts:
            if os.path.exists(p):
                os.remove(p)
    span_map = {str(s["id"]): list(sp) for s, sp in zip(script, spans)}
    json.dump(span_map, open(out_wav + ".spans.json", "w"))
    log(f"  wrote {out_wav}")
    return out_wav


# ---------------------------------------------------------------- pipeline integration
def ensure_narration_audio(cfg, log=print):
    """If narration.tts.enabled is set and narration.audio is not, synthesize the narration
    once (cached - regenerates only if script/engine/voice/speed changed) and point
    cfg['narration']['audio'] at the result. After this, every other part of the pipeline
    (ae.align forced alignment, ae.render muxing, ae.captions approval, ae.qa checks) treats
    AI-generated narration exactly like a user's own recording - there is no TTS-specific
    branch anywhere else in the codebase, including caption approval: it still requires a
    human to run approve-captions, same as for any other narration.audio file."""
    tts_cfg = (cfg.get("narration") or {}).get("tts") or {}
    if not tts_cfg.get("enabled") or cfg["narration"].get("audio"):
        return
    engine = tts_cfg.get("engine", "espeak")
    voice = tts_cfg.get("voice")
    speed = float(tts_cfg.get("speed", 1.0))
    kokoro_model_dir = tts_cfg.get("kokoro_model_dir")
    wd = os.path.join(cfg["_dir"], "work", cfg["output"]["name"])
    os.makedirs(wd, exist_ok=True)
    out_wav = os.path.join(wd, "tts_narration.wav")
    meta_path = out_wav + ".json"
    # Everything that can change what gets spoken or how it's timed goes in this key, so audio
    # and timing data (the .word_timing.json / .spans.json sidecar) always stay correctly
    # associated with the exact script, engine, voice and speed that produced them - a changed
    # key regenerates both together, never one without the other.
    key = {"engine": engine, "voice": voice, "speed": speed, "script": cfg["narration"]["script"],
           "kokoro_model_dir": kokoro_model_dir}
    if os.path.exists(out_wav) and os.path.exists(meta_path):
        try:
            if json.load(open(meta_path)) == key:
                cfg["narration"]["audio"] = os.path.relpath(out_wav, cfg["_dir"])
                return
        except Exception:
            pass   # cache unreadable/corrupt - regenerate
    # Regenerating: remove any stale sidecar from a previous engine/voice first, so a leftover
    # .word_timing.json (or .spans.json) from a different engine can never be read against new
    # audio it doesn't describe.
    for stale in (out_wav + ".word_timing.json", out_wav + ".spans.json"):
        if os.path.exists(stale):
            os.remove(stale)
    log(f"Generating narration with {engine} (voice={voice or 'default'}, speed={speed})...")
    synth_script(cfg["narration"]["script"], out_wav, engine=engine, voice=voice, speed=speed,
                 log=log, tmp_dir=wd, kokoro_model_dir=kokoro_model_dir)
    json.dump(key, open(meta_path, "w"))
    cfg["narration"]["audio"] = os.path.relpath(out_wav, cfg["_dir"])
