# Installation guide

## Supported platform
**Tested:** Ubuntu 24.04 LTS (x86_64), Python 3.13.18, FFmpeg 6.1.1.
Other Linux distributions, macOS and Windows are **untested**. The libraries are cross-platform,
but expect to adapt the system-package step.

Note: Ubuntu 24.04's own `python3` is version 3.12. Every test of this release used Python 3.13.18,
so Python 3.12 is **untested**. If you can, install Python 3.13 and create the virtual environment
with it.

Hardware: no GPU needed. Rendering a 27-second video took about 95 s on 4 CPU cores.

## 1. System packages
```bash
sudo apt-get update                 # needed on fresh images, or apt can't find espeak-ng/fonts-dejavu
sudo apt-get install -y ffmpeg fonts-inter fonts-dejavu espeak-ng
```
- `ffmpeg`/`ffprobe`: required.
- `fonts-inter`: optional; DejaVu is the fallback.
- `espeak-ng`: needed only for `engine: espeak` narration. Kokoro ships its own phonemizer.

Check the apt output. A failed `apt-get install` piped through other commands can still look
successful.

## 2. Get the code and install the Python packages (virtual environment recommended)
```bash
git clone https://github.com/7onsieur/absolute-kinema.git
cd absolute-kinema/absolute-kinema         # the skill folder (identifier: absolute-kinema)
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
```
`requirements.txt` pins numpy, opencv-contrib-python-headless, pillow, PyYAML, pocketsphinx, pytest
and kokoro-onnx. A fresh Python 3.13.18 virtual environment on Ubuntu 24.04 installed cleanly and
passed the test suite during release preparation.

On Ubuntu's system Python, `pip install` outside a virtual environment is refused (PEP 668). Use the
virtual environment above.

## 3. Kokoro voice model (one-time, automatic)
The first `validate`, `preview` or `render` of a project with `engine: kokoro` downloads two files
(~136 MB in total) from kokoro-onnx's **GitHub Releases**:
`kokoro-v1.0.int8.onnx` and `voices-v1.0.bin`. They are cached in
`~/.cache/animated-explainer/kokoro`. After that, Kokoro runs fully offline.

- To use another folder, set `AE_KOKORO_MODEL_DIR=/path` or `narration.tts.kokoro_model_dir` in the
  project file.
- If the download fails, the error names the exact URLs. Download them on another machine and put
  them in that folder.
- Hugging Face access is **not** needed. Piper is the only engine whose voices are hosted there.

## 4. Check the install
```bash
python -m pytest -q tests/
python scripts/make_video.py voices --engine kokoro
python scripts/make_video.py validate examples/water_cycle/project.yaml
```
See [`TESTING.md`](TESTING.md) for the expected results.

## 5. Optional: Piper
`pip install piper-tts`. Download one voice's `.onnx` and `.onnx.json` from the Piper VOICES list
(hosted on Hugging Face), then set `narration.tts: {engine: piper, voice: /path/voice.onnx}`.
**Not verified end to end by this project.**

## Costs
None. No API keys, no paid services, no GPU. Network access is needed only for the package install
and the one-time Kokoro download.

## Installing it as an agent skill
Copy the skill folder into your agent's skills directory, keeping the name `absolute-kinema`. For
Claude Code, run this from the repository root:
```bash
mkdir -p ~/.claude/skills && cp -r absolute-kinema ~/.claude/skills/absolute-kinema
```
Then create the virtual environment and install the requirements inside that copy, as in step 2.

**Renamed from `animated-explainer`:** the Kokoro cache folder `~/.cache/animated-explainer/kokoro`
and the `AE_KOKORO_MODEL_DIR` variable keep their original names, so an existing download is reused.
