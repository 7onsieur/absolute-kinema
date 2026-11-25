# Third-party notices

This repository's own code, documentation, examples and example artwork are under the
[MIT Licence](LICENSE). **No third-party code, model weights or fonts are bundled in this
repository.** The components below are installed or downloaded separately by the user and remain
under their own licences. Licences were read from each package's installed metadata (versions
pinned in `absolute-kinema/requirements.txt`) on 25 November 2026. This is not legal advice.

## Python packages (installed with `pip install -r requirements.txt`)
| Package | Version | Licence | Notes |
|---|---|---|---|
| numpy | 2.5.3 | BSD-3-Clause (plus bundled permissive licences) | |
| opencv-contrib-python-headless | 5.1.0.95 | Apache-2.0 | |
| pillow | 12.3.0 | MIT-CMU | |
| PyYAML | 6.0.3 | MIT | |
| pocketsphinx | 5.1.1 | BSD | Includes its US-English acoustic model |
| pytest | 9.1.1 | MIT | Tests only |
| kokoro-onnx | 0.6.1 | MIT | Kokoro voice engine wrapper |
| onnxruntime | (dependency of kokoro-onnx) | MIT | |
| **phonemizer** | (dependency of kokoro-onnx) | **GPL-3.0-or-later** | Imported at run time by kokoro-onnx |
| **espeakng-loader** | (dependency of kokoro-onnx) | Ships the **eSpeak NG library (GPL-3.0)** | Loaded at run time by phonemizer |

**GPL note:** when the Kokoro engine runs, GPL-3.0 code is loaded into the same process as this
skill. The MIT licence of this repository is compatible with GPL-3.0. If you **redistribute** a
bundle that includes these GPL components (for example a container image or frozen app), the
GPL-3.0 terms apply to that bundle. Using the skill as published (users install dependencies
themselves) does not redistribute them.

## Downloaded at first use
| Component | Licence | Source |
|---|---|---|
| Kokoro-82M model, ONNX export (`kokoro-v1.0.int8.onnx`) and voices (`voices-v1.0.bin`) | Apache-2.0 | kokoro-onnx GitHub Releases (`model-files-v1.1`), cached in `~/.cache/animated-explainer/kokoro` |

## System packages (installed with `apt-get`)
| Component | Licence | Notes |
|---|---|---|
| FFmpeg | LGPL-2.1+ / GPL-2.0+ (depending on build) | Called as a separate programme |
| espeak-ng | GPL-3.0 | Called as a separate programme (`engine: espeak`) |
| Inter font | SIL Open Font License 1.1 | Optional; rendered into videos as pixels |
| DejaVu fonts | Bitstream Vera licence (and public domain) | Fallback font |

## Optional, not installed by default
| Component | Licence | Notes |
|---|---|---|
| Piper (`piper-tts`) | MIT | Voices are downloaded by the user from Hugging Face and have their own per-voice licences |

## Example media in this repository
- `examples/earthquakes/art/*.png`: original diagrams drawn by `make_diagrams.py` (MIT, this repository).
- `examples/earthquakes/output/earthquakes.mp4`, `absolute-kinema/examples/water_cycle/output/water_cycle.mp4`:
  rendered by this skill. The narration is synthetic speech from the Kokoro `bf_emma` voice (Apache-2.0
  model; there are no restrictions on its output). Text is rendered with the fonts above.
