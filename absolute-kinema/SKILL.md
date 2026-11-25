---
name: absolute-kinema
description: Make a short (10–15 s) educational animated explainer video (1920x1080 MP4, plus SRT captions) from a plain-language brief, using a YAML project file and local, free tools (Python, Pillow, OpenCV, FFmpeg, PocketSphinx, and optionally espeak-ng/Piper/Kokoro-ONNX for AI narration). Narration can be the user's own recording, a free local AI-generated voice (including natural-sounding British Kokoro voices with exact word-level caption timing), or none at all. Use when a user asks for a short animated explainer, an educational animation, a motion-graphics clip that explains a concept, or captions synced to narration (recorded or AI-generated) for such a clip. Not for live-action editing, AI-generated video, animating a specific illustrated character with lip-sync, or videos longer than about a minute.
version: 0.4.0-rc2
---

# AbsoluteKinema (`absolute-kinema`, v0.4-rc2)

*Formerly `animated-explainer`. Renamed at release; behaviour is unchanged. The voice-model cache
folder (`~/.cache/animated-explainer/kokoro`), the `AE_KOKORO_MODEL_DIR` variable and the `ae` Python
module keep their original names for compatibility.*

**What's new in v0.4-rc2** (fixes for release-blocking issues an independent fresh-session test of
rc1 found — see `V0.4_RC2_RELEASE_REPORT.md` for full detail):
- **Real audio samples for the narration lead-in.** The configured `narration.offset` silence
  before the voice starts is now baked into the actual exported PCM data, so it survives even a
  decoder that ignores container-level timestamps — not something that depended on an MP4
  timestamp/edit-list mechanism in the first place, but now verified directly against raw decoded
  samples rather than only against container metadata.
- **`validate`/the render log now distinguish fully exact Kokoro timing from timing where a
  merged-phoneme-group pair/run got a localized estimate**, instead of reporting both cases as
  plain "exact."
- **Tests no longer hardcode a developer-specific model path.** Kokoro's tests now locate model
  weights the same way the skill itself does (the `AE_KOKORO_MODEL_DIR` environment variable, or
  the standard per-user cache), so they run correctly wherever the models are actually cached.
- Several documentation fixes: a long-broken reference to a file never actually bundled with any
  release, a missing `apt-get update` in the install instructions, and inconsistent narration
  word-count/duration guidance (see "AI narration" and the troubleshooting table below).
- All v0.4-rc1 functionality (Kokoro narration, merge-localization, render-cache invalidation,
  espeak-ng, Piper, recordings, silent video, caption approval) is unchanged and still fully
  supported — this release fixes defects, it does not add features.

**What's new in v0.4-rc1** (focus: a genuinely natural-sounding narration voice, with caption timing
that doesn't need forced alignment at all — see `V0.4_RELEASE_REPORT.md` for full evidence):
- **New engine: Kokoro-ONNX** (`engine: kokoro`) — a neural TTS model with real British voices
  (default `bf_emma`) that sound far less mechanical than espeak-ng. Unlike espeak-ng/Piper,
  Kokoro's word timing comes **directly from the model's own per-phoneme duration output**, not
  from forced alignment — so it sidesteps PocketSphinx's confirmed British-voice alignment
  failures (see v0.3 limitations below) entirely, for this engine.
- **Model weights are downloaded once, automatically, on first use**, from `kokoro-onnx`'s own
  GitHub Releases (not Hugging Face, which this project's sandbox could not reach) — no paid
  service, and a clear, specific error with manual-download instructions if the download fails.
  See "AI narration" below.
- **Connected-speech caveat, found and fixed during development:** Kokoro's phonemizer sometimes
  runs two adjacent words together with no gap (e.g. "far more"). The skill detects this and
  recovers exact timing for every unaffected word, only estimating the real, measured combined
  duration of the merged pair (never the whole sentence) — see `CAPTION_DRIFT_FIX_v0.4.md`.
- **Render-cache correctness fix:** changing narration, timing or project config between renders
  now always invalidates any previously-rendered video segments for that project, instead of
  potentially (and silently) reusing stale ones from before the change.
- `python3 scripts/make_video.py voices --engine kokoro` lists all Kokoro voices (British and
  American) and flags which one has actually been human-reviewed for this skill.
- All v0.3 behaviour (espeak-ng, Piper, user recordings, silent videos, caption approval) is
  unchanged and still fully supported — this is purely additive.

**What's new in v0.3** (focus: AI-generated narration, so a user without their own recording can
still get a fully narrated video — see `DEVELOPMENT_REPORT_v0.3.md` for the full findings):
- **Optional AI narration**: set `narration.tts.enabled: true` (with no `narration.audio`) and the
  narration is synthesized locally and automatically from `narration.script` — no paid service, no
  internet access needed at render time. User-recorded narration and silent videos both still work
  exactly as before; this is purely additive.
- Two engines: **espeak-ng** (default, verified working end-to-end, GPL, install with `apt-get
  install espeak-ng`) and **Piper** (optional, MIT, more natural neural voices — see "AI narration"
  below for why its voices could not be verified end-to-end in this project's own environment).
- `python3 scripts/make_video.py voices [--engine espeak|piper]` lists the installed voices.
- AI-generated narration is forced-aligned to the real synthesized audio exactly like a user's own
  recording (same `verify-captions`/`approve-captions` human checkpoint, same QA) — **except** for a
  verified limitation with espeak-ng's British English voices; see "AI narration" below.
- Rendering now has a duration safety net: if the real narration audio turns out longer than the
  planned timing (estimate or alignment), the last scene is extended automatically so speech is
  never cut off.
- Automated QA (`qa_report.md`) now also checks for: a missing audio stream when narration audio was
  expected, possible missing words in the AI/recorded narration, and malformed, overlapping or
  backwards-timed subtitles in the `.srt` file.

**What's new in v0.2** (from an independent fresh-session usability test of v0.1, summarized in
`DEVELOPMENT_REPORT_v0.2.md`; the original test-results write-up was a development-time record and
is not bundled with this skill package):
- A word cue (`at: "year"`) that matches more than one word in a scene's narration is now a
  **validation error**, not a silent first-match. Use a sentence id, or `"word#2"` for the Nth
  occurrence. See "Cues", below.
- `validate` now prints the narration's word count, the estimated pace, and a rule-of-thumb
  formula for hitting a different target duration.
- The preview contact sheet marks unused grid cells with a label and a distinct fill, instead of
  plain black that could be mistaken for a black video frame.
- The intro/outro fade is now documented and configurable (`intro_fade`, `outro_fade`), instead of
  a hardcoded, undocumented 0.3s/0.6s.
- `templates/project_template.yaml` documents every element type's full option set, not just two
  of them in full with the rest as one-line examples.
- All v0.1 behaviour is unchanged otherwise — the caption approval system (verify-captions /
  approve-captions, human checkpoint 2) is exactly as before.

Turn a short brief into an animated explainer: titles, cards, icons, step-by-step flows,
checklists, counters and the user's own images. Elements are cued to the words of the narration.
The user edits a YAML file, never Python. You (the agent) do the technical work and stop at the
human checkpoints.

## When to use
**Use it** for 10–15 s concept explainers (it can go up to about 60 s), captions for the user's own
narration, and quick animated summaries for teaching.

**Do not use it** for:
- videos that need a moving cartoon character with lip-sync. That needs a custom rig like the
  original project; say so instead of faking it;
- photorealistic or AI-generated footage;
- anything that requires paid services.

## Inputs to collect (ask, don't guess)
1. **Topic, audience, and the one thing to remember.** Use `templates/brief_template.md`.
2. **Narration text:** roughly 25–35 words as a starting point for a 10–15 s target, at the
   default pace (~0.35s/word) and default lead-in/outro overhead (~2.1s). The exact word count for
   your target duration depends on your project's actual `narration.offset` and `outro_hold`
   settings — always confirm with `validate`'s own word-count/pace output and rule-of-thumb formula
   (see "Production steps" below) rather than this rough starting range. Offer to draft it, then
   let the user edit it.
3. **How will it be narrated?** Ask, don't assume:
   - **The user's own voice recording** (any FFmpeg-readable format) — the script must match it
     **word for word**, including ad-libs.
   - **AI-generated narration** — only if the user asks for this (never generate a synthetic voice
     unless asked). See "AI narration", below, for engine/voice choice. For a natural-sounding
     British voice, prefer Kokoro (`engine: kokoro`, default voice `bf_emma`); espeak-ng remains the
     always-available, more mechanical-sounding fallback.
   - **No voice** (captions/narration text still drives pacing if a script is given, or the video can
     be driven purely by `duration:` on each scene).
4. **Optional images:** only the user's own or properly licensed artwork.
5. **Look:** theme (dusk, night, day, paper) and accent colour.

## AI narration
Set, under `narration:` (with `narration.audio` left `null`):
```yaml
narration:
  audio: null
  script: [ ... ]        # as usual - this is what gets spoken
  tts:
    enabled: true
    engine: kokoro          # kokoro (recommended, natural voice) | espeak (always-available fallback) | piper
    voice: bf_emma          # run: python3 scripts/make_video.py voices --engine kokoro
    speed: 1.0              # 0.5 (slower) to 2.0 (faster)
    kokoro_model_dir: null  # optional: a folder that already has the Kokoro model files (see below)
```
Narration is generated automatically the next time `validate`, `preview` or `render` is run (cached;
regenerated only if the script, engine, voice, speed or `kokoro_model_dir` changes). From then on the
pipeline treats it exactly like a user's own recording — same `verify-captions` / `approve-captions`
human checkpoint (**AI narration is never auto-approved**), same QA.

**Engine choice, verified in this project's own environment** (see `V0.4_RELEASE_REPORT.md` and
`DEVELOPMENT_REPORT_v0.3.md` for full evidence):
- **Kokoro-ONNX** (`engine: kokoro`, **recommended**) — a neural TTS model, far less
  mechanical-sounding than espeak-ng. Several British voices (`bf_emma` — the default, and the only
  one actually human-reviewed for this skill; `bf_isabella`, `bf_alice`, `bf_lily`, `bm_george`,
  `bm_fable`, `bm_lewis`, `bm_daniel`) and American voices (`af_heart`, `af_bella`, `am_michael`).
  Caption timing comes **directly from the model's own per-phoneme duration output** — no forced
  alignment, so the PocketSphinx British-voice limitation below does not apply to this engine.
  Requires the `kokoro-onnx` PyPI package (`pip install kokoro-onnx`, MIT license) and ~140MB of
  model weights (Apache-2.0), which are **downloaded automatically on first use** from
  `kokoro-onnx`'s own GitHub Releases — not bundled with this skill, and not fetched from Hugging
  Face. This needs network access to GitHub the first time only; after that, the weights are cached
  locally (default `~/.cache/animated-explainer/kokoro`, or set `narration.tts.kokoro_model_dir` /
  the `AE_KOKORO_MODEL_DIR` environment variable to reuse a folder that already has them). If the
  download fails, you get a specific error naming the exact URLs and a manual-download alternative —
  never a silent fallback or a paid service.
- **espeak-ng** (`engine: espeak`) — installs with `apt-get install espeak-ng`, fully offline, GPL,
  no download needed. Several English voices, including British ones: `en-gb`, `en-gb-x-rp`
  (Received Pronunciation), `en-gb-scotland`, `en-gb-x-gbclan` (Lancaster), `en-gb-x-gbcwmd` (West
  Midlands), and `en-us`. Voice quality is mechanical/robotic, not neural — use this only when Kokoro
  isn't available (no network for the one-time model download, or `kokoro-onnx` can't be installed).
- **Piper** (`engine: piper`) — MIT-licensed, local, genuinely natural-sounding neural voices,
  including good British English ones. The `piper-tts` package installs cleanly from PyPI and its
  CLI works correctly. **Its voice model files are hosted only on Hugging Face**, which was not
  reachable from this project's own development sandbox (confirmed: a direct network policy block,
  unrelated to Piper itself). This engine is fully implemented and documented, but **was not tested
  end-to-end in this project's own environment** — if your environment can reach huggingface.co,
  download one voice's `.onnx` + `.onnx.json` from
  [the VOICES list](https://github.com/rhasspy/piper/blob/master/VOICES.md), keep them together, and
  set `narration.tts.voice` to the `.onnx` path; verify the result yourself before relying on it.

**Known limitation — British voices and alignment (espeak-ng/Piper only):** PocketSphinx (the
offline forced-alignment engine this skill uses for recordings and for espeak-ng/Piper narration)
ships with only an American-English acoustic model (confirmed: `pocketsphinx.get_model_path()` lists
only `en-us`). In direct testing, **every** espeak-ng British voice tried (`en-gb`, `en-gb-x-rp`,
`en-gb-scotland`) **failed** forced alignment on realistic sentences, while `en-us` aligned reliably
every time. The skill **does not crash** when this happens — it falls back to estimated word timing
and says so loudly (in the render log, the QA report, and `validate`'s output:
`timing: estimated (alignment failed - see warning)`) — but captions and element cues are then only
approximate, not matched to the real audio. **This limitation does not apply to Kokoro**, whose
timing never goes through PocketSphinx. If you need a British espeak-ng/Piper voice specifically and
precise audio-verified sync matters more than switching engines, expect estimated (not aligned)
timing with espeak-ng, or use `voice: en-us`.

**Known limitation — merged phoneme groups (Kokoro only):** Kokoro's phonemizer occasionally runs two
adjacent words together with no gap in natural connected speech (measured at roughly 25% of sentences
in this project's own testing, e.g. "far more" → one phoneme group). The skill detects this
(`ae/kokoro_tts.py`'s growing-prefix check) and recovers **exact** timing for every word not involved
in a merge, splitting only the real, measured combined duration of the merged pair/run by syllable
weight — never discarding the whole sentence's real timing. `validate`'s log and the QA report note
when any word's timing came from this localized estimate rather than being exact. If a sentence's
mismatch doesn't match this one verified pattern, the skill falls back to the original
whole-sentence estimate for that sentence only, and says so.

## Setup (once per machine)
Follow `README.md` (install section). Then check that everything works:
```bash
python3 -m pytest -q tests/        # expect: passed (1 skipped unless test audio is configured)
```
If tests fail, report the failure and stop. Do not work around it silently.

## Production steps
Run the commands from the skill folder (the one containing this file).

1. **Create the project:** `python3 scripts/make_video.py new <folder>`. This copies
   `project.yaml` and `brief.md` into a new folder.
2. **Fill in `brief.md`** with the user, then write `project.yaml`:
   - **Narration:** one entry per sentence under `narration.script` (`id` + `text`).
   - **Scenes:** usually 2–3, each with `narration: [ids]` (or `duration`), a `transition`, and `elements`.
   - **Cues:** give each element a cue with `at:`. This is one of:
     - a number of seconds after the scene starts (`at: 0.5`);
     - a sentence id (`at: s2`) — **preferred**, since it can never become ambiguous if you reword
       the sentence later;
     - a word spoken in that scene (`at: "evaporates"`) — only valid if the word appears **exactly
       once** in the scene's narration. If it appears more than once, `validate` rejects it rather
       than silently picking the first occurrence — use a sentence id instead, or an occurrence
       selector (`at: "year#2"` for the second "year");
     - a word with a time offset (`at: "rain-0.1"` / `at: "rain+0.2"`).
   - **References:** see `templates/project_template.yaml` (every element type's full option set is
     documented there) and the example in `examples/water_cycle/`. List the icons with
     `python3 scripts/make_video.py icons`.
3. **Validate:** `python3 scripts/make_video.py validate <folder>/project.yaml`. Fix every reported
   problem in the YAML. The validator also resolves every cue now (catching typos and ambiguous
   repeated-word cues before preview/render), and prints the narration's word count plus a
   rule-of-thumb formula for hitting a target duration — use this instead of guessing when you
   need to shorten or lengthen the narration for a specific length.
4. **Preview:** `python3 scripts/make_video.py preview <folder>/project.yaml`. This makes stills plus
   `contact_sheet.png` in `<folder>/work/<name>/preview/`.
   - **Look at the contact sheet yourself:** overlaps, text off-screen, empty scenes, and visuals that
     don't match the words. Grid cells with no still (when the still count doesn't divide evenly
     into the grid) are filled with a hatched "(unused - no still here)" placeholder, not black —
     they are not part of the video.
   - **Show it to the user. Human checkpoint 1:** the user approves the content and look.
5. **Render:** `python3 scripts/make_video.py render <folder>/project.yaml` (add `--draft` for a fast
   half-resolution check).
   - **Resumable:** if it stops, run the same command again; finished segments are kept.
   - **Output:** `<folder>/output/<name>.mp4`, plus `<name>.UNVERIFIED.srt` if audio was supplied, plus
     `<name>.qa_report.md`.
6. **Quality control:**
   - Read the QA report.
   - Extract a contact sheet from the MP4 (`ffmpeg -i out.mp4 -vf "fps=1,scale=480:-1,tile=5x3"
     -frames:v 1 sheet.png`) and inspect it.
   - Fix significant problems (the wrong visual for a sentence, unreadable text, broken transitions), then re-render.
7. **Captions (only when there is a recording). Human checkpoint 2, mandatory:**
   1. Run `python3 scripts/make_video.py verify-captions <folder>/project.yaml`. Then read
      `output/<name>.captions_review.md`. It lists:
      - voiced speech that no script word covers (probable missing words);
      - what a rough offline recogniser heard, for comparison.
   2. **If a missing word is flagged,** ask the user what was said, add it to the script, then
      re-render.
   3. **Then the user listens** to the whole video and reads every caption. Only *the user* runs:
      `python3 scripts/make_video.py approve-captions <folder>/project.yaml --name "Their Name"`.
      This renames the SRT to `<name>.srt` and records the approval against the exact audio and script.

   **Never run approve-captions on the user's behalf, and never call captions "accurate" or
   "verified" before the user has approved them.** Changing the audio or script resets the approval.
8. **Deliver:** give the MP4 (and SRT) paths, the render time, the QA result, the caption status, and any
   limitations you noticed.

## Quality-control requirements (do not skip)
- [ ] If AI narration is used: `validate`'s output says whether timing was **aligned** to the real
      audio or **estimated** (alignment failed) — tell the user which, don't assume aligned.
- [ ] Validation passes with no errors.
- [ ] The preview contact sheet has been reviewed by you and approved by the user.
- [ ] The QA report shows 1920x1080, clean decode, the expected duration, and no unexplained frozen spans.
- [ ] If there is audio: the true peak is ≤ −1 dBFS, and captions were reviewed in `captions_review.md`.
- [ ] If there is audio: the caption status is **VERIFIED** (the user ran approve-captions), or it is
      reported as **NOT VERIFIED**.
- [ ] Facts in the narration and on screen were checked by the user (the skill cannot check facts).

## Troubleshooting
| Symptom | Fix |
|---|---|
| "not in the pronunciation dictionary: X" | Add `spoken: {X: "how it sounds"}` to that sentence, using ordinary dictionary words |
| `verify-captions` flags a spot but nothing is missing | Phonetic spellings (`spoken:`) can leave a part of a word uncovered. Listen; if the captions are right, the flag is a false positive |
| "Segments failed after retries" | Run the same command again (it resumes). If it repeats, lower `render.workers` or raise `render.memory_limit_gb` |
| Cue not found | The cue word must appear in *that scene's* narration; check the spelling |
| Cue "is ambiguous" | The word appears more than once in that scene's narration. Switch to a sentence id (`at: s2`), or add an occurrence number (`at: "word#2"`) |
| Text too small or large | Add `size:` to the element |
| Video ends darker than expected | That's `outro_fade` (default 0.6s fade to black at the very end) — set `outro_fade: 0` in the project file to disable it |
| Narration too long/short for the target duration | Run `validate` — it prints the word count, the estimated pace, and a rule-of-thumb word count for your target length |
| "Could not generate AI narration" | Read the specific reason in the error (missing engine, missing Piper voice file, bad `speed`). Fix `narration.tts` in the project file |
| `timing: estimated (alignment failed - see warning)` with AI narration | Known limitation with espeak-ng/Piper British voices (see "AI narration" above) — not a crash. Switch to `engine: kokoro` (unaffected), or `engine: espeak, voice: en-us` for reliable alignment, or accept estimated timing |
| Could not download the Kokoro model files | A network/proxy issue reaching GitHub Releases, not Hugging Face. The error names the exact URLs — download them yourself on a machine that can reach them and place them in the folder it names, or point `kokoro_model_dir` at a folder that already has them |
| A word's timing note says "shares a merged phoneme group" (Kokoro) | Expected and documented (see "AI narration" above) — that one word pair/run got a localized, syllable-weighted estimate within their real combined duration; every other word in the sentence is exact |
| "the rendered file has no audio stream at all" (QA) | `narration.audio`/`narration.tts` was set but muxing produced a silent file — re-render; if it repeats, check the source audio/TTS output plays correctly on its own |
| "subtitle timing:" issue (QA) | The `.srt` file has a malformed, backwards or overlapping timestamp — regenerate by re-rendering; report it if it persists, this should not happen |

## Limitations (v0.4-rc2, be honest with users)
- **Only Kokoro's `bf_emma` voice has been human-reviewed** for this skill (see
  `V0.4_RELEASE_REPORT.md`). The other Kokoro voices are implemented and documented but untested by
  a human listener. The British voice is acceptable for free educational use; more expressive
  narration remains a possible future improvement, per that review.
- **Kokoro's merged-phoneme-group recovery is a verified, localized estimate, not perfect alignment**
  for the specific word pair/run involved — see "AI narration" above. It is exact for every other
  word in the sentence.
- **AI-narration alignment (espeak-ng/Piper only):** see "AI narration" above — espeak-ng British
  voices are not currently reliable with this project's PocketSphinx forced alignment; `en-us` is.
  Kokoro does not have this limitation (its timing never goes through PocketSphinx).
- **Piper is implemented but unverified end-to-end** in this project's own environment, because its
  voice models are hosted only on Hugging Face, which this sandbox could not reach. Verify it
  yourself if you use it.
- **The missing-word QA check is only as good as the timing it runs against:** when alignment has
  failed and timing fell back to estimates (espeak-ng/Piper), "possible missing words" can be noisy
  (false positives) — read it with that caveat, same as the existing accent-sensitivity caveat below.
- **TTS sentence pacing is uniform:** AI-generated narration inserts a fixed ~0.35s silence between
  sentences; it does not vary pacing for emphasis or breathing the way a human reader would.
- **No prosody/emotion control:** no engine lets you control emphasis, pitch contour or emotion
  beyond overall speed.
- **Kokoro needs a one-time network download** (~140MB, from GitHub Releases) unless
  `kokoro_model_dir` already points at a folder with the model files; after that it runs fully
  offline, like the other engines.
- **Everything below is unchanged from v0.2:**
- **Tested platforms:** only Ubuntu 24.04 x86_64 with Python 3.13. Other operating systems are untested.
- **Format:** 1920x1080 only; frame rates 24, 25 or 30.
- **No character animation:** images can bob, sway or zoom, but there is no lip-sync and no rigging.
- **Recogniser accuracy:** forced alignment uses a small US-English model. Strong accents make the
  recogniser's free transcript unreliable, but alignment of the known script usually still works.
  False positives are possible in `verify-captions`.
- **Visual vocabulary:** layouts are fixed per element type and the icon set is small (20 icons).
- **Facts:** the skill cannot check facts or judge teaching quality; a human must.
- **Duration estimate without a recording is still an estimate**, not exact — `validate`'s word-count
  guidance (new in v0.2) narrows the guesswork but doesn't eliminate the need to re-check after
  editing the narration.
- **The occurrence selector (`word#N`) counts matches in narration order**, not visual/semantic
  order — if a scene's narration is reordered, occurrence numbers can shift. Sentence-id cues don't
  have this issue and are still the more robust choice.
- **Not re-tested cross-platform or against the original v0.1 fresh-session environment from
  scratch** — v0.2 was developed and tested in the same container as the v0.1 test, which already
  matched the documented tested-platform versions exactly (see `DEVELOPMENT_REPORT_v0.2.md`). A
  genuinely independent fresh-session usability test of v0.2 itself has not been run.
