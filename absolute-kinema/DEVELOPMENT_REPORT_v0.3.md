# animated-explainer v0.3 — development report

**Scope:** enable the skill to generate a complete educational animation with AI narration,
synchronised visuals and subtitles, without requiring the user to record their own voice — building
on v0.2 (21 passing tests, silent-animation production confirmed working). Work was done in a
separate copy (`dev_v03/animated-explainer/`), started from `animated-explainer-v0.2.zip`; v0.1, v0.2
and the original video project were not touched (see "What was preserved").

**Not done in this pass:** publishing, GitHub, any paid service, or bundling any voice model — none
were used, per instructions.

## 1. Inspection (before changing anything)

Read `scripts/ae/align.py`, `captions.py`, `render.py` and `qa.py` in full. Two facts shaped every
decision below:
- `render.build_timing()` already runs real forced alignment **whenever `narration.audio` resolves to
  an existing file**, with no branch for how that file was produced. This meant AI narration could be
  added by making it produce a plain WAV and pointing `narration.audio` at it — reusing the entire
  existing alignment/mux/caption-approval pipeline with **zero changes needed** to `captions.py` and
  only an additive change to `align.py`/`render.py` (see §5).
- `captions.status()`/`verify()`/`approve()` read `cfg["narration"]["audio"]` directly from the config
  dict, not from a file on disk. Because Python dicts are mutable and the same `cfg` object is reused
  through one command's whole lifetime, resolving AI narration once inside `config.load()` (before
  `cfg` is handed to anything else) makes every downstream function see it automatically, with no
  special-casing anywhere else in the codebase.

## 2. TTS engine research (verified, not assumed)

Per the explicit instruction to select an engine "based on verified evidence," every claim below was
checked directly in this project's own sandbox, not taken from documentation alone.

| Engine | Licence | Install | Verified working | Voices |
|---|---|---|---|---|
| **espeak-ng** | GPL-3.0 | `apt-get install espeak-ng` (reachable: `archive.ubuntu.com`) | **Yes** — installed, CLI tested, produces valid WAV output, confirmed real British English variants | `en-gb`, `en-gb-x-rp` (Received Pronunciation), `en-gb-scotland`, `en-gb-x-gbclan` (Lancaster), `en-gb-x-gbcwmd` (West Midlands), `en-us`, more |
| **Piper** | MIT | `pip install piper-tts` (reachable: PyPI) | **Package: yes.** `piper` CLI installs and runs correctly. **Voices: no** — see blocker below | en_GB voices exist (per the project's official `VOICES.md`) but could not be downloaded here |

**Piper voice-download blocker (documented, not worked around):** every Piper voice, for every
language including all `en_GB` voices, is hosted exclusively on `huggingface.co` per the official
`VOICES.md` (fetched directly from `raw.githubusercontent.com/rhasspy/piper/master/VOICES.md`, which
*was* reachable). Three independent checks confirmed `huggingface.co` itself was not reachable from
this sandbox:
1. A direct request to `huggingface.co` returned a 403 from the sandbox's own network proxy.
2. The proxy's own status endpoint (`$HTTPS_PROXY/__agentproxy/status`) listed this as a non-retriable
   policy denial, not a transient failure.
3. No mirror exists elsewhere: `rhasspy/piper-voices` does not exist as a GitHub repository (404 on
   `raw.githubusercontent.com`, itself reachable, confirming this is an absence of a mirror, not
   another block) and no PyPI package bundles the weights.

**Decision:** implement both engines in `scripts/ae/tts.py`. Use **espeak-ng as the default and the
one used for this report's own test deliverables**, since it is the one verified fully working
end-to-end here. Piper is fully implemented and documented as the better-quality option for an
environment that *can* reach Hugging Face, with this limitation stated plainly rather than silently
substituting a paid TTS API — which was never considered, per instructions.

## 3. A second, deeper verified finding: British-voice alignment

Once espeak-ng narration was wired into the existing PocketSphinx forced-alignment pipeline
(`align.py`), a new, independent problem appeared: **forced alignment failed outright** on espeak-ng's
British English voices (`PocketSphinx: "Final result does not match the grammar"`), even on isolated,
clean, single-sentence clips with no concatenation involved.

This was tracked down systematically, not patched blindly:
1. Confirmed it was not about concatenation/silence gaps — a single isolated British-voice sentence
   failed alignment on its own.
2. Tested the same 4 real sentences from the demo script across 4 voices: `en-gb-x-rp`, `en-gb`,
   `en-gb-scotland` **all failed on all 4 sentences (12/12 failures)**; `en-us` **succeeded on all 4**.
3. Root cause confirmed directly: `pocketsphinx.get_model_path()` shows the installed PocketSphinx
   package ships **only an `en-us` (American English) acoustic model** — there is no bundled British
   English model for forced alignment to use, which the strict grammar/FSG alignment mode (unlike free
   decoding) is unforgiving of.

This is a genuine architectural mismatch between "the voice engine" (espeak-ng, which does British
English well) and "the alignment engine" (PocketSphinx, bundled with American English only), not a
bug introduced by this pass's own code, and not something in scope to fix by replacing PocketSphinx
(the existing, already-tested v0.1/v0.2 alignment dependency).

**Response, in order of preference:**
1. **Never crash.** `render.build_timing()` now catches an alignment failure, falls back to the
   existing estimated-word-timing algorithm (same one already used for "no recording"), and surfaces
   this loudly — in the render log, `validate`'s output (`timing: estimated (alignment failed - see
   warning)`), and the QA report — rather than silently claiming sync it doesn't have.
2. **Never cut off real speech even in the fallback.** A new safety net in `build_timing()` compares
   the real narration audio's own measured length (via `ffprobe`, independent of any alignment or
   estimate) against the computed timing, and extends the final scene if needed — this also caught and
   fixed a few small real cases during testing (see §6), not just the fallback path.
3. **Document the limitation plainly** in `SKILL.md`'s new "AI narration" section and the template,
   with a concrete recommendation (`voice: en-us` for guaranteed alignment; a British voice for a
   natural accent at the cost of estimated-only timing) rather than picking silently on the user's
   behalf.

## 4. Per-sentence alignment for AI narration

A second, complementary improvement: because AI narration is synthesized **one sentence at a time and
then concatenated by this skill's own code** (`tts.py`), the exact start/end of each sentence's audio
is already known precisely — unlike a human recording, where it must be inferred. `tts.synth_script()`
now records these as `<audio>.spans.json`, and a new `align.align_segments()` uses them to align each
sentence on its own isolated audio slice, rather than risking one whole-file forced alignment across
the silences inserted between sentences. `render.build_timing()` uses this path automatically whenever
a `.spans.json` file is found next to the narration audio; human recordings are unaffected and still
use the original whole-file `align.align()`.

## 5. What was built

| File | Change |
|---|---|
| `scripts/ae/tts.py` | **New.** `synth_script()` (espeak-ng and Piper backends, per-sentence synthesis + concatenation + silence gaps + `.spans.json`), `ensure_narration_audio()` (the one integration point: called from `config.load()`, resolves `narration.tts` into a real, cached WAV and sets `narration.audio` in-memory), `list_voices()`/`espeak_voices()`, `apply_spoken_overrides()` (reuses the existing `spoken:` pronunciation-override mechanism for TTS input text, not just alignment) |
| `scripts/ae/config.py` | `DEFAULTS`/`validate()`: new `narration.tts` block (`enabled`, `engine`, `voice`, `speed`) with full validation (engine must be known, speed 0.5–2.0, Piper requires a voice path, `audio` and `tts.enabled` are mutually exclusive); `load()` calls `tts.ensure_narration_audio()` after validation, wrapping its errors as the usual friendly `ConfigError` |
| `scripts/ae/align.py` | New `align_segments()` for per-sentence alignment (§4); `align()` (whole-file, for recordings) is unchanged |
| `scripts/ae/render.py` | `build_timing()`: uses `align_segments()` when a `.spans.json` sidecar exists; catches alignment failures and falls back to estimated timing with a loud, recorded warning (§3); new duration safety net comparing real audio length to computed timing |
| `scripts/ae/qa.py` | New checks: missing audio stream when narration was expected; possible missing words (reuses the existing `align.verify()` evidence, now surfaced automatically in every QA report, not only via `verify-captions`); malformed/overlapping/backwards `.srt` timestamps (`_check_srt()`); the alignment-fallback warning is now a QA issue too |
| `scripts/make_video.py` | New `voices [--engine espeak|piper]` command |
| `templates/project_template.yaml`, `SKILL.md`, `README.md` | Document `narration.tts`, the engine choice, the British-voice alignment limitation, the new `voices` command, and the new QA checks |

**Caption approval is unchanged and was specifically re-verified against AI narration:** `captions.py`
was not modified. A project using `narration.tts.enabled: true` starts at `NOT VERIFIED` exactly like
a recording, and only becomes `VERIFIED` when a human explicitly runs `approve-captions` — confirmed
by `test_tts_narration_generated_and_treated_like_a_recording`. No code path anywhere marks AI-sourced
captions as verified automatically.

## 6. Testing performed

1. **Full automated suite:** `python3 -m pytest -q tests/` → **37 passed, 1 skipped** (same optional
   real-recording test as v0.1/v0.2, unaffected). 16 new tests cover: TTS input validation (bad
   engine/speed, empty script, missing Piper voice file), `apply_spoken_overrides`, espeak-ng voice
   listing (skipped if espeak-ng isn't installed), sentence concatenation + `.spans.json` correctness,
   every new `narration.tts` config-validation error, AI narration resolving into `narration.audio`
   exactly like a recording, AI narration aligning to real timings (via `en-us`), a full TTS render
   producing an audible MP4 + SRT with zero missing-word flags, alignment-failure fallback (simulated,
   not accent-dependent, so the test doesn't flake), the duration safety net, `_check_srt()` on good
   and deliberately corrupted subtitle files, and missing-audio-stream detection.
2. **Manual end-to-end demo**, "Why is the sky blue?" (4 scenes, 61 words), built and rendered twice:
   - **British voice** (`engine: espeak, voice: en-gb-x-rp`), the brief's stated preference: narration
     generated successfully; MP4 (23.6s, 1920x1080/30fps) has a real audible British-accented audio
     stream (loudness −17.2 LUFS, true peak −1.4 dBFS, no clipping); captions/cues use **estimated**
     timing because alignment failed as described in §3, and this is stated plainly in the QA report
     and `validate` output; `verify-captions` flagged 3 possible missing-word spots, consistent with
     the estimated (not audio-verified) timing caveat — not approved, per instructions (no human
     listened).
   - **American voice** (`engine: espeak, voice: en-us`), same script/scenes, to prove the full
     alignment-dependent feature set end-to-end: alignment **succeeded**; `validate` reported `timing:
     aligned to recording`; render produced a 21.0s MP4 with 0 QA issues; `verify-captions` found **0**
     possible missing-word spots; the generated `.srt` file's captions were checked by hand against the
     script and match exactly, in order, with non-overlapping timestamps.
3. **Deliberate-error detection** (explicit testing requirement), each confirmed directly:
   - **Missing audio stream:** stripped audio from a rendered MP4 with `ffmpeg -an` → QA correctly
     reported `"narration.audio is set, but the rendered file has no audio stream at all"`.
   - **Audio clipping:** boosted a rendered MP4's audio by +12 dB → QA correctly reported `"audio may
     clip"`.
   - **Subtitle timing:** corrupted one `.srt` block's timestamps (end before start) → `_check_srt()`
     correctly reported `"a subtitle's end time is not after its start time"`; a separate deliberately
     overlapping pair was correctly flagged `"a subtitle overlaps the previous one"`.
   - **Missing/extra words:** pointed a project's `narration.audio` at the already-generated (correct)
     TTS WAV but removed one sentence's words from `narration.script` (simulating a caption that
     doesn't match what's actually said) → `verify-captions` correctly flagged 3 possible missing-word
     spots where the un-transcribed speech was; the same script/audio pair with the full, correct
     script produces 0 flags.
4. **Existing functionality unaffected:**
   - Silent videos (`examples/water_cycle/`, no `narration.audio`, no `tts`) still `validate` and
     behave exactly as in v0.2 (`timing estimated (no recording)`).
   - All 21 pre-existing v0.1/v0.2 tests still pass unchanged.
   - The duration safety net also exercised itself (not just in the fallback case) during normal
     testing: the `en-us` sky-is-blue render was extended by 0.08s automatically because the real
     synthesized audio ran slightly longer than the aligned-timing estimate — confirming the net
     protects the aligned path too, not only the fallback path.

## What was preserved

- `dev/animated-explainer/` (v0.2) and `animated-explainer-v0.2.zip` were not modified; this pass's
  work lives entirely in a separate `dev_v03/animated-explainer/` copy, verified byte-identical to the
  v0.2 source at the start of this pass (`diff -rq`, exit code 0).
- `scripts/ae/captions.py` was not modified at all (§5).
- No personal recordings, no private project files, and no paid service of any kind were used. No
  voice model weights are bundled in the package — Piper voices must be downloaded by the user
  themselves, from the official source, if they choose to use that engine.
- Nothing was published to GitHub.

## Remaining limitations

- **espeak-ng British voices do not currently align reliably** with this project's PocketSphinx
  installation (§3) — the render still succeeds and produces real British narration, but captions/cues
  fall back to estimated (not audio-verified) timing, and this is surfaced to the user every time, not
  hidden. `voice: en-us` is the only combination verified to align reliably in this testing.
- **Piper's voice-download path is implemented but unverified end-to-end** in this project's own
  environment (§2) — it should work in an environment that can reach Hugging Face, but that has not
  been directly confirmed here.
- **The missing-word QA check inherits the alignment it runs against:** when alignment has failed and
  fallen back to estimates, its flags are noisier and less trustworthy — this caveat is now stated in
  `SKILL.md`.
- **TTS pacing is uniform** between sentences (a fixed silence gap); it does not model natural
  variation in a human reader's pacing, breathing, or emphasis.
- **No independent fresh-session usability test of v0.3 itself** — same caveat as v0.2's report: this
  pass was developed and tested by the same session that wrote it, not by a reader starting cold.
- Everything in v0.2's own "Limitations" section still applies unchanged (platform: Ubuntu 24.04 x86_64
  only; 1920x1080 only; no character lip-sync; small icon set; the skill cannot check facts).

## Files changed

```
scripts/ae/tts.py             NEW: AI narration (espeak-ng + Piper), voice listing, spoken: reuse
scripts/ae/config.py          narration.tts defaults + validation; load() calls ensure_narration_audio()
scripts/ae/align.py           NEW align_segments(): per-sentence alignment for AI narration
scripts/ae/render.py          build_timing(): per-sentence alignment path, alignment-failure fallback,
                               duration safety net against cutting off real narration audio
scripts/ae/qa.py              missing-audio-stream, possible-missing-words, and subtitle-timing checks
scripts/make_video.py         new `voices` command
templates/project_template.yaml   narration.tts documented, with the British-voice caveat
SKILL.md                      version bump, "What's new in v0.3", "AI narration" section, troubleshooting,
                               limitations
README.md                     version bump, install step for espeak-ng, Piper note, file-layout update
tests/test_ae.py              16 new tests (see "Testing performed")
DEVELOPMENT_REPORT_v0.3.md    This file
```
