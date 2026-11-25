# AbsoluteKinema (`absolute-kinema`) v0.4-rc2

*Formerly `animated-explainer`. The cache folder `~/.cache/animated-explainer/kokoro`, the
`AE_KOKORO_MODEL_DIR` variable and the `ae` module keep their original names for compatibility.*

Make a 10–15-second educational animation from a YAML project file, with no Python editing. It was developed from
the "How AI Agents Use Skills" explainer project (University of Leicester AI internship); v0.2 was revised
based on an independent fresh-session usability test of v0.1, summarized in `DEVELOPMENT_REPORT_v0.2.md` (the
original test-results write-up was a development-time record and is not bundled with this skill package);
v0.3 added optional AI-generated narration (see `DEVELOPMENT_REPORT_v0.3.md`); v0.4 adds a natural-sounding
Kokoro-ONNX voice with model-native caption timing, exact for most words and a documented, bounded estimate
for the rare merged-phoneme-group case (see `V0.4_RELEASE_REPORT.md`); v0.4-rc2 fixes release-blocking issues
an independent fresh-session test of rc1 found (see `V0.4_RC2_RELEASE_REPORT.md`).
Agents should follow `SKILL.md`; this README covers installation and the folder layout.

**Changed since v0.3:** a new `engine: kokoro` narration option (`SKILL.md`'s "AI narration" section) gives a
natural-sounding British voice (`bf_emma` by default) whose caption timing comes directly from the model's
own output, not forced alignment — so it is unaffected by the espeak-ng/Piper British-voice alignment
limitation. Model weights download automatically on first use from GitHub Releases (not bundled, not from
Hugging Face). Render-cache invalidation was fixed so a changed narration, timing or config can never
silently reuse a stale rendered video segment. Nothing about espeak-ng, Piper, user recordings, silent
videos, cues, or captions approval changed.

**Changed since v0.2 (unchanged in v0.4):** narration can be AI-generated locally (`narration.tts.enabled:
true`) instead of only a user recording or silence. A `voices` command lists available voices. QA also
checks for a missing audio stream, possible missing words, and malformed subtitle timing. Rendering extends
the final scene automatically if real narration audio would otherwise be cut off.

## Tested platform
**Only Ubuntu 24.04.5 LTS, x86_64, Python 3.13.18 and FFmpeg 6.1.1.** Windows, macOS and other versions have **not** been
tested. They may work (all the libraries are cross-platform), but that is unverified.

## Install
```bash
sudo apt-get update
sudo apt-get install -y ffmpeg fonts-inter fonts-dejavu      # fonts-inter is optional (DejaVu is the fallback)
sudo apt-get install -y espeak-ng                             # only needed for AI narration (engine: espeak)
python3 -m pip install -r requirements.txt                   # includes kokoro-onnx, for engine: kokoro
python3 -m pytest -q tests/                                  # check the install
```
Everything is free. espeak-ng/Piper/recordings/silent video run fully offline. Kokoro (`engine: kokoro`)
needs network access to GitHub once, the first time it runs, to download its model files (~140MB); after
that it also runs fully offline. No API keys, no GPU, no paid services, ever.

### Recommended: Kokoro-ONNX (natural AI narration, incl. British voices)
Installed automatically via `requirements.txt` (`kokoro-onnx`, MIT license; the model weights it downloads
are Apache-2.0). Set `narration.tts: {engine: kokoro, voice: bf_emma}` — this is the default British voice
that was actually human-reviewed for this skill. Run `python3 scripts/make_video.py voices --engine kokoro`
for the full voice list. The model files (~140MB) download automatically the first time narration is
generated, from `kokoro-onnx`'s own GitHub Releases, and are cached at `~/.cache/animated-explainer/kokoro`
(override with `narration.tts.kokoro_model_dir` or the `AE_KOKORO_MODEL_DIR` environment variable, e.g. to
reuse a folder on a machine with no network access). If the download fails, the error names the exact URLs
and a manual-download alternative — it never falls back to a paid service.

### Optional: Piper (higher-quality AI narration)
`pip install piper-tts` installs cleanly and works, but its voice files are not bundled (licensing/size) and
are hosted only on Hugging Face. Download one voice's `.onnx` + `.onnx.json` from
[the VOICES list](https://github.com/rhasspy/piper/blob/master/VOICES.md), keep the two files together, and
set `narration.tts: {engine: piper, voice: /path/to/voice.onnx}` in the project file. This path is fully
implemented but was not verified end-to-end in this project's own environment (Hugging Face was not
reachable from it) — verify it yourself before relying on it for a real deliverable.

## Quick start
```bash
python3 scripts/make_video.py validate examples/water_cycle/project.yaml
python3 scripts/make_video.py preview  examples/water_cycle/project.yaml
python3 scripts/make_video.py render   examples/water_cycle/project.yaml   # about 40 s on 4 cores
```
Output goes to `examples/water_cycle/output/water_cycle.mp4` and `water_cycle.qa_report.md`.

New project: `python3 scripts/make_video.py new my_topic`, then edit `my_topic/project.yaml`.

## What is in the folder
| Path | Purpose |
|---|---|
| `SKILL.md` | Instructions for the agent: inputs, steps, human checkpoints, QA, limitations |
| `scripts/make_video.py` | The only command you run (`new`, `validate`, `preview`, `render`, `verify-captions`, `approve-captions`, `qa`, `icons`, `voices`) |
| `scripts/ae/` | Reusable modules: `config` (validation), `timing` (cues, captions, SRT), `scene` (elements, transitions, themes), `gfx` (drawing toolkit), `render` (segmented, resumable, memory-bounded, duration safety net, render-cache invalidation), `align` (forced alignment and mismatch evidence, for recordings/espeak-ng/Piper), `captions` (review and approval), `contact_sheet` (preview grid layout), `tts` (local AI narration dispatch: espeak-ng/Piper/Kokoro), `kokoro_tts` (Kokoro-ONNX synthesis and native word-timing recovery), `qa` |
| `templates/` | `project_template.yaml` (every element type's full option set documented) and `brief_template.md` |
| `examples/water_cycle/` | A worked example (brief, project file, rendered MP4) |
| `tests/` | Automated tests (`python3 -m pytest -q tests/`) |

## Rendering design
The video is rendered in 2-second segments. Each segment is handled by a short-lived process with a memory ceiling and goes straight to a small MP4. Re-running a command resumes from where it stopped. A failed segment is retried twice, then reported (it never hangs).

## Licence and content
- **Code:** the code is original to this project.
- **Fonts:** Inter and DejaVu are free (OFL / Bitstream Vera licences) and are installed separately.
- **Distribution:** do not add personal recordings or copyrighted footage to this folder.
