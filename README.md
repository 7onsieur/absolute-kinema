# AbsoluteKinema

**AbsoluteKinema** (skill identifier `absolute-kinema`, formerly `animated-explainer`) is an agent skill that turns a short plain-language brief into an **educational animated explainer
video**: a 1920×1080 MP4 with burned-in captions, plus an `.srt` subtitle file. It uses only free,
local tools: Python, Pillow, OpenCV, FFmpeg, PocketSphinx, and optionally espeak-ng, Piper or
Kokoro-ONNX for AI narration.

You describe the video in a YAML project file. The skill handles the timing, animation, narration,
captions and quality checks, and stops at two **human checkpoints**: approving the preview, and
approving the captions.

> **Status: release candidate v0.4.0-rc2.** This is the independently assessed v0.4-rc2 implementation,
> renamed from `animated-explainer` to AbsoluteKinema at release. Only names and descriptive text
> changed; the code behaves exactly as tested (see [`CHANGELOG.md`](CHANGELOG.md)). It is not yet a final
> release: human approval of the example captions is still pending.
> Developed during the University of Leicester AI internship, from the "How AI Agents Use Skills"
> explainer project.

| | |
|---|---|
| Example output | [`examples/earthquakes/output/earthquakes.mp4`](examples/earthquakes/output/earthquakes.mp4): 27 s, British Kokoro voice |
| Silent example | [`absolute-kinema/examples/water_cycle/`](absolute-kinema/examples/water_cycle/) |
| Install | [`docs/INSTALL.md`](docs/INSTALL.md) |
| Testing | [`docs/TESTING.md`](docs/TESTING.md) |
| Limitations | [`docs/LIMITATIONS.md`](docs/LIMITATIONS.md) |
| Version history | [`CHANGELOG.md`](CHANGELOG.md) |
| Independent test evidence | [`evidence/`](evidence/README.md) |

## What it can do
- **Titles, text, cards, bullets, checklists, flows, arrows, counters, 20 built-in icons**, and your
  own images. Each element can appear on a specific word of the narration (`at: "evaporates"`) or
  sentence (`at: s2`).
- **Scene transitions** (cut, fade, slide, wipe, circle), a gentle camera zoom, and four themes.
- **Three narration options:**
  - **your own recording**, forced-aligned to the script with PocketSphinx;
  - **free local AI narration**: **Kokoro** (recommended; natural British voices, word timing
    taken from the model itself), **espeak-ng** (always offline, more robotic), or **Piper**
    (implemented, not verified end to end);
  - **no voice** at all.
- **Synchronised captions**, burned in and exported as `.srt`. They stay marked `UNVERIFIED` until
  a human approves them.
- **Automated QA**: resolution, clean decode, frozen frames, loudness and true peak, a missing audio
  track, possibly missing words, and malformed subtitles.
- **Resumable, memory-bounded rendering** in 2-second segments.

It is **not** for live action, AI-generated footage, lip-synced characters, or videos longer than
about a minute.

## Quick start
```bash
git clone https://github.com/7onsieur/absolute-kinema.git
cd absolute-kinema/absolute-kinema
sudo apt-get update && sudo apt-get install -y ffmpeg fonts-inter fonts-dejavu espeak-ng
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
python -m pytest -q tests/                       # see docs/TESTING.md for the expected result

python scripts/make_video.py validate ../examples/earthquakes/project.yaml   # first run downloads Kokoro (~136 MB, once)
python scripts/make_video.py preview  ../examples/earthquakes/project.yaml
python scripts/make_video.py render   ../examples/earthquakes/project.yaml
python scripts/make_video.py verify-captions ../examples/earthquakes/project.yaml
# watch the video with sound, read every caption, then (a human, not the agent):
python scripts/make_video.py approve-captions ../examples/earthquakes/project.yaml --name "Your Name"
```
Start a new project with `python scripts/make_video.py new my_topic`. Every option is documented
in [`absolute-kinema/templates/project_template.yaml`](absolute-kinema/templates/project_template.yaml).

## Using it as an agent skill
The skill is the self-contained folder [`absolute-kinema/`](absolute-kinema/). Its
[`SKILL.md`](absolute-kinema/SKILL.md) is the agent's instruction file: when to use the skill,
what to ask the user, the production steps, the human checkpoints and the QA checklist. Copy that
folder (from the repository root) into your agent's skills directory, keeping its name so it matches the identifier
`absolute-kinema`. For Claude Code, for example:
```bash
mkdir -p ~/.claude/skills && cp -r absolute-kinema ~/.claude/skills/absolute-kinema
```
(or a project's `.claude/skills/`). Then install its dependencies as in [`docs/INSTALL.md`](docs/INSTALL.md). The agent edits YAML and runs the CLI. It never edits the Python, and it
never approves captions on the user's behalf.

## Repository layout
```
absolute-kinema/             the skill itself: the tested v0.4-rc2 code, renamed (names and text only)
  SKILL.md                   agent instructions
  README.md                  the package's own install notes and folder layout
  scripts/make_video.py      the only command you run
  scripts/ae/                rendering, timing, TTS, alignment, captions, QA modules
  templates/                 project + brief templates
  examples/water_cycle/      silent example (no narration)
  tests/                     pytest suite (47 tests)
  *_REPORT*.md, CAPTION_DRIFT_FIX_v0.4.md, V0.4_RC2_FRESH_SESSION_TEST_PLAN.md   development records
examples/earthquakes/        narrated example: project, brief, original diagrams, rendered output
docs/                        install guide, testing guide, known limitations
evidence/                    independent test reports for v0.4-rc1 and v0.4-rc2
CHANGELOG.md                 version history
LICENSE                      MIT licence
THIRD-PARTY-NOTICES.md       licences of dependencies, model and fonts (none bundled)
```

## Compatibility names kept from `animated-explainer`
To keep the tested behaviour unchanged, three internal names were not renamed: the voice-model cache
folder `~/.cache/animated-explainer/kokoro`, the `AE_KOKORO_MODEL_DIR` environment variable and the
`ae` Python module. Existing Kokoro downloads are reused.

## Status and honesty notes
- Tested **only on Ubuntu 24.04 x86_64, Python 3.13.18, FFmpeg 6.1.1**.
- Of the voices, only Kokoro **`bf_emma`** has been reviewed by a human.
- Captions in the bundled example are **NOT VERIFIED**. They are machine-checked only (see
  `examples/earthquakes/output/earthquakes.captions_review.md`).
- The skill cannot check facts. A human must.

Full list: [`docs/LIMITATIONS.md`](docs/LIMITATIONS.md).

## Licence
This repository (the skill's code, documentation, examples and the original example diagrams) is
released under the **[MIT Licence](LICENSE)**, Copyright (c) 2026 7onsieur. If you copy only the
`absolute-kinema/` skill folder elsewhere, copy `LICENSE` with it.

No third-party code, model weights or fonts are bundled. Dependencies are installed separately and
keep their own licences. Note that the Kokoro voice path installs **GPL-3.0** components at run time
(`phonemizer` and the eSpeak NG library). See [`THIRD-PARTY-NOTICES.md`](THIRD-PARTY-NOTICES.md).
