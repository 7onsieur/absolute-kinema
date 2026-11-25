"""Kokoro-ONNX narration: a neural TTS engine with real British voices, much less "robotic"
than espeak-ng, with EXACT word-level caption timing recovered from the model's own per-phoneme
duration output - no separate forced-alignment step, and so none of PocketSphinx's British-voice
failures (see DEVELOPMENT_REPORT_v0.3.md: 12/12 espeak-ng British voices failed PocketSphinx
alignment in this project's own testing).

Distribution and licensing (verified directly, not assumed - see V0.4_RELEASE_REPORT.md):
  - the `kokoro-onnx` PyPI package is MIT-licensed and wraps an ONNX export of the Kokoro model.
  - the Kokoro model itself is Apache-2.0 (stated in kokoro-onnx's own README/LICENSE).
  - both licenses permit redistribution, but this skill does NOT bundle the ~140MB of model
    weights in its own package, to keep the skill small. They are downloaded once, on first use,
    from kokoro-onnx's own GitHub Releases - NOT Hugging Face, which this project's development
    sandbox could not reach - and cached locally (see ensure_model()). If your network can't
    reach GitHub Releases either, this raises a clear, specific error with the exact URLs and a
    manual-download alternative, rather than failing silently or falling back to a paid service.

Voice IDs: British voices start with 'b' (bf_* = British female, bm_* = British male); the
default, bf_emma, is the one a human reviewer listened to and judged acceptable for this skill
during its v0.4 development (see V0.4_RELEASE_REPORT.md). American voices (af_*, am_*) are
listed for completeness but were not part of that review.

Caveat, found and measured directly during v0.4 development: the phonemizer Kokoro uses
sometimes runs two adjacent words together with no audible gap in natural connected speech
(e.g. "far more" -> one phoneme group, not two). When that happens, sentence_word_timing()
localizes the estimate to just the words that actually share a group - using only in-context
phonemization (never an isolated word's own form, which can be pronounced differently in
context, e.g. "has" alone vs. reduced next to other words - a real, measured effect, not a
guess) - instead of discarding the whole sentence's real timing. See _find_runs() below and
CAPTION_DRIFT_FIX_v0.4.md for the investigation that produced this.
"""
import json
import os
import re
import urllib.error
import urllib.request
import wave
from dataclasses import dataclass

import numpy as np

MODEL_RELEASE = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.1"
MODEL_FILE = "kokoro-v1.0.int8.onnx"
VOICES_FILE = "voices-v1.0.bin"
DEFAULT_MODEL_DIR = os.environ.get("AE_KOKORO_MODEL_DIR") or os.path.expanduser("~/.cache/animated-explainer/kokoro")
DEFAULT_VOICE = "bf_emma"
SENTENCE_GAP_S = 0.35  # matches ae.tts.SENTENCE_GAP_S, for a consistent pace across engines

BRITISH_VOICES = {
    "bf_emma": "British female (default; reviewed and accepted for this skill)",
    "bf_isabella": "British female (untested in this skill's own review)",
    "bf_alice": "British female (untested in this skill's own review)",
    "bf_lily": "British female (untested in this skill's own review)",
    "bm_george": "British male (untested in this skill's own review)",
    "bm_fable": "British male (untested in this skill's own review)",
    "bm_lewis": "British male (untested in this skill's own review)",
    "bm_daniel": "British male (untested in this skill's own review)",
}
AMERICAN_VOICES = {
    "af_heart": "American female (untested in this skill's own review)",
    "af_bella": "American female (untested in this skill's own review)",
    "am_michael": "American male (untested in this skill's own review)",
}


def list_voices():
    return {**BRITISH_VOICES, **AMERICAN_VOICES}


def lang_for(voice):
    return "en-gb" if str(voice)[:1] == "b" else "en-us"


def model_paths(model_dir=None):
    d = model_dir or DEFAULT_MODEL_DIR
    return os.path.join(d, MODEL_FILE), os.path.join(d, VOICES_FILE)


def ensure_model(model_dir=None, log=print):
    """Download the Kokoro model/voice files once, if not already cached at model_dir. Raises
    RuntimeError with manual-download instructions on failure - never retries with a different
    (e.g. paid) source."""
    model_path, voices_path = model_paths(model_dir)
    if os.path.exists(model_path) and os.path.exists(voices_path):
        return model_path, voices_path
    os.makedirs(os.path.dirname(model_path), exist_ok=True)
    for name, path in ((MODEL_FILE, model_path), (VOICES_FILE, voices_path)):
        if os.path.exists(path):
            continue
        url = f"{MODEL_RELEASE}/{name}"
        log(f"Downloading Kokoro model file {name} (one-time, free, open download) from {url} ...")
        try:
            urllib.request.urlretrieve(url, path + ".part")
            os.replace(path + ".part", path)
        except (urllib.error.URLError, OSError) as e:
            if os.path.exists(path + ".part"):
                os.remove(path + ".part")
            raise RuntimeError(
                f"Could not download {name} from {url} ({type(e).__name__}: {e}). This is a "
                f"free, open download (kokoro-onnx wrapper: MIT license; Kokoro model: "
                f"Apache-2.0 license) - no paid service is involved or offered as a fallback. "
                f"If your network can't reach GitHub Releases, download the file yourself from "
                f"that URL on a machine that can, then place it at {path} (or point "
                f"narration.tts.kokoro_model_dir at a folder that already has both {MODEL_FILE} "
                f"and {VOICES_FILE}).")
    return model_path, voices_path


# ---------------------------------------------------------------- native word timing
@dataclass
class WordTiming:
    word: str
    start: float
    end: float
    confidence: str   # "exact" | "estimated (...)"


@dataclass
class SentenceResult:
    text: str
    words: list
    audio_duration: float
    method: str        # "exact" | "partial" | "estimated"
    note: str = ""


def _group_phonemes_by_word(spoken):
    groups, cur = [], []
    for t in spoken:
        if t.phoneme == " ":
            if cur:
                groups.append(cur)
                cur = []
        else:
            cur.append(t)
    if cur:
        groups.append(cur)
    return groups


def _syllables(w):
    w = re.sub(r"[^a-z]", "", w.lower())
    if not w:
        return 1
    n = len(re.findall(r"[aeiouy]+", w))
    if w.endswith("e") and n > 1 and not w.endswith("le"):
        n -= 1
    return max(1, n)


def _estimate_within_sentence(words, total_duration):
    weights = [0.075 + 0.17 * _syllables(w) for w in words]
    total_w = sum(weights) or 1.0
    out, t = [], 0.0
    for w, wt in zip(words, weights):
        dur = total_duration * (wt / total_w)
        out.append(WordTiming(w, t, t + dur, "estimated (whole-sentence syllable-weighted fallback)"))
        t += dur
    return out


def _find_runs(kokoro, words, lang):
    """Localize exactly which words share a merged phoneme group, using only in-context
    phonemization. See module docstring and CAPTION_DRIFT_FIX_v0.4.md."""
    runs, prev_groups = [], 0
    for i in range(len(words)):
        prefix = " ".join(words[:i + 1])
        ph = kokoro.tokenizer.phonemize(prefix, lang=lang)
        g = len([x for x in ph.split(" ") if x])
        if g == prev_groups and runs:
            runs[-1].append(i)
        else:
            runs.append([i])
        prev_groups = g
    return runs


def _realign_merged_groups(kokoro, words, groups, lang):
    runs = _find_runs(kokoro, words, lang)
    if len(runs) != len(groups):
        return None
    out = []
    for run, g in zip(runs, groups):
        if len(run) == 1:
            out.append(WordTiming(words[run[0]], g[0].start, g[-1].end, "exact"))
            continue
        dur = g[-1].end - g[0].start
        ws = [words[i] for i in run]
        weights = [0.075 + 0.17 * _syllables(w) for w in ws]
        total_w = sum(weights) or 1.0
        tag = (f"estimated (shares a merged phoneme group with {len(run) - 1} adjacent "
               f"word(s); split by syllable weight within their real combined duration)")
        t = g[0].start
        for w, wt in zip(ws, weights):
            d = dur * wt / total_w
            out.append(WordTiming(w, t, t + d, tag))
            t += d
    return out


def sentence_word_timing(kokoro, text, voice, lang="en-gb", speed=1.0):
    """Synthesize one sentence and return (audio, sample_rate, SentenceResult)."""
    audio, sr, spoken = kokoro.create_timed(text, voice=voice, speed=speed, lang=lang)
    duration = len(audio) / sr
    words = text.split()
    groups = _group_phonemes_by_word(spoken)
    if len(groups) == len(words):
        wt = [WordTiming(w, g[0].start, g[-1].end, "exact") for w, g in zip(words, groups)]
        return audio, sr, SentenceResult(text, wt, duration, "exact")

    realigned = _realign_merged_groups(kokoro, words, groups, lang)
    if realigned is not None:
        n_est = sum(1 for w in realigned if w.confidence != "exact")
        note = (f"phoneme groups ({len(groups)}) != words ({len(words)}) - recovered exact "
                f"timing for {len(words) - n_est}/{len(words)} words; {n_est} shared a merged "
                f"group with a neighbour and had their real combined duration split between "
                f"them by syllable weight.")
        return audio, sr, SentenceResult(text, realigned, duration, "partial", note)

    note = (f"phoneme groups ({len(groups)}) != words ({len(words)}) and the mismatch did not "
            f"match the single verified merge-localization pattern this module checks for. "
            f"Falling back to a same-sentence, syllable-weighted estimate scaled to this "
            f"sentence's own real audio duration.")
    return audio, sr, SentenceResult(text, _estimate_within_sentence(words, duration), duration, "estimated", note)


def measure_word_group_match_rate(kokoro, sentences, lang="en-gb"):
    """Diagnostic: how often phoneme-group count matches word count, with no audio synthesis."""
    exact, details = 0, []
    for text in sentences:
        ph = kokoro.tokenizer.phonemize(text, lang=lang)
        groups = len([g for g in ph.split(" ") if g])
        words = len(text.split())
        ok = groups == words
        exact += ok
        details.append((text, words, groups, ok))
    return exact, len(sentences), details


# ---------------------------------------------------------------- pipeline entry point
def synth_script_kokoro(script, out_wav, voice=None, speed=1.0, log=print, model_dir=None):
    """Synthesize `script` ([{id, text, spoken?}, ...]) to out_wav, and write
    out_wav + '.word_timing.json' ({sid: [[word, t0, t1], ...]}) with real, model-native word
    timing - see ae/render.py's build_timing(), which uses this sidecar directly instead of
    forced alignment whenever it exists next to the audio."""
    from .tts import apply_spoken_overrides  # local import: avoids a tts.py <-> kokoro_tts.py cycle
    if not script:
        raise ValueError("narration.script is empty - nothing to narrate.")
    if not (0.5 <= float(speed) <= 2.0):
        raise ValueError("narration.tts.speed must be between 0.5 and 2.0.")
    voice = voice or DEFAULT_VOICE
    if voice not in list_voices():
        raise ValueError(f"unknown Kokoro voice '{voice}' (use one of {sorted(list_voices())}).")
    lang = lang_for(voice)
    model_path, voices_path = ensure_model(model_dir, log)
    try:
        from kokoro_onnx import Kokoro
    except ImportError as e:
        raise RuntimeError(
            "the 'kokoro-onnx' package is not installed. Install it: "
            "pip install kokoro-onnx (see README.md's 'Kokoro voices')."
        ) from e
    kokoro = Kokoro(model_path, voices_path)

    chunks, word_timing, t_cursor, sr = [], {}, 0.0, None
    for i, s in enumerate(script):
        sid = str(s["id"])
        text = apply_spoken_overrides(str(s["text"]), s.get("spoken"))
        log(f"  synthesising {sid} (kokoro/{voice}): "
            f"{text[:60]}{'...' if len(text) > 60 else ''}")
        audio, this_sr, result = sentence_word_timing(kokoro, text, voice, lang=lang, speed=speed)
        if sr is None:
            sr = this_sr
        elif this_sr != sr:
            raise RuntimeError(f"Kokoro's sample rate changed mid-script ({this_sr} vs {sr}).")
        if i > 0:
            chunks.append(np.zeros(int(SENTENCE_GAP_S * sr), dtype=np.float32))
            t_cursor += SENTENCE_GAP_S
        sentence_start = t_cursor
        # 4th field ("exact" / "estimated (...)") lets render.build_timing() tell apart a
        # sentence that is fully exact from one where only a merged-phoneme-group pair/run got
        # a localized estimate - a v0.4-rc1 validation gap (the overall timing source claimed
        # plain "exact" even when some words weren't) found by an independent fresh-session test
        # and fixed for v0.4-rc2. Still readable as plain [word, t0, t1] by anything that only
        # looks at the first three fields.
        word_timing[sid] = [[w.word, round(sentence_start + w.start, 4), round(sentence_start + w.end, 4),
                              w.confidence] for w in result.words]
        chunks.append(audio)
        t_cursor += result.audio_duration
        if result.method != "exact":
            log(f"    note: {result.note}")

    combined = np.concatenate(chunks) if chunks else np.zeros(0, dtype=np.float32)
    pcm = (np.clip(combined, -1.0, 1.0) * 32767.0).astype(np.int16)
    with wave.open(out_wav, "w") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr or 24000)
        w.writeframes(pcm.tobytes())
    json.dump(word_timing, open(out_wav + ".word_timing.json", "w"), indent=1)
    log(f"  wrote {out_wav}")
    return out_wav
