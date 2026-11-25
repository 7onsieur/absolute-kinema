# Example: How earthquakes happen (27 s, British AI narration)

A complete narrated project. Use it to see what a finished project file looks like, and as an
end-to-end test.

| File | What it is |
|---|---|
| `brief.md` | The filled-in brief: audience, narration, visual plan |
| `project.yaml` | 5 sentences, 4 scenes, Kokoro `bf_emma`, word- and sentence-cued elements |
| `art/*.png` | 4 original diagrams (plates, locked fault, rupture, seismic waves) |
| `art/make_diagrams.py` | The Pillow script that drew them: `python3 art/make_diagrams.py art` |
| `output/earthquakes.mp4` | Rendered with v0.4-rc2: 1920×1080, 30 fps, 27.4 s, −16.3 LUFS, true peak −1.5 dBFS |
| `output/earthquakes.UNVERIFIED.srt` | 12 subtitle cues, **not approved by a human** |
| `output/earthquakes.qa_report.md`, `output/earthquakes.captions_review.md` | The automated QA and caption evidence |

## Re-render it
Run from the `absolute-kinema/` skill folder:
```bash
python scripts/make_video.py validate ../examples/earthquakes/project.yaml
python scripts/make_video.py render   ../examples/earthquakes/project.yaml
```
`validate` should report `timing exact for 68/70 words; 2 word(s) partially estimated`. The two
estimated words, "in the", are a merged phoneme group.

## What it demonstrates
- Elements cued to words: the card appears on "tectonic", the drift text on "centimetres", and the
  four bullets on lock, stress, snaps and energy.
- `until:` to swap images: the locked-fault diagram is replaced by the rupture exactly on "snaps".
- The `image` element with your own artwork, because the built-in icons include no geology.
- Slide, wipe and circle transitions, and the outro fade.

## Status
- The preview was approved by a human reviewer.
- The **captions are NOT VERIFIED**. To approve them, watch the video with sound and read every caption.
- Facts (plate speeds of roughly 2–10 cm a year, and the elastic-rebound explanation) follow standard
  introductory geology. Check them yourself before teaching with it.
