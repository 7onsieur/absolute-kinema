# Testing

## Automated suite
```bash
cd absolute-kinema
python -m pytest -q -rs tests/
```
47 tests cover config validation, cue resolution (including ambiguous-word rejection), contact
sheets, fades, TTS dispatch, forced-alignment fallback, Kokoro merged-phoneme recovery, render-cache
invalidation, real PCM lead-in silence, QA checks and the caption-approval state machine.

**Expected results**

| Situation | Result |
|---|---|
| Kokoro model downloaded (default cache or `AE_KOKORO_MODEL_DIR`) | **46 passed, 1 skipped** |
| Fresh install, before any Kokoro download | 43 passed, 4 skipped (the 3 Kokoro tests skip; they don't fail) |

- The one skip that always appears is the optional real-recording test. To run it, set
  `AE_TEST_AUDIO` (a recording) and `AE_TEST_SCRIPT` (a YAML list of `{id, text}` sentences matching it).
- To run the Kokoro tests on a fresh machine, run `validate` once on a Kokoro project first (for
  example `examples/earthquakes`), or point `AE_KOKORO_MODEL_DIR` at a folder that already has the model.
- The suite takes about 3 minutes on 4 cores.
- Note: the bundled `V0.4_RC2_FRESH_SESSION_TEST_PLAN.md` says the expected skip is `NO_ESPEAK`. In
  practice it is the `AE_TEST_AUDIO` test. This is a documentation slip, already recorded in the
  rc2 assessment.
- That test plan, the development reports and the evidence predate the rename. Where they say
  `animated-explainer` (the folder or ZIP name), read `absolute-kinema`.

**Verified results for this release (Ubuntu 24.04, Python 3.13.18):**
- 46 passed, 1 skipped (rc2 assessment, with weights)
- 46 passed, 1 skipped (release preparation, system Python)
- 46 passed, 1 skipped (release preparation, brand-new virtual environment with a fresh `pip install -r requirements.txt`)

## End-to-end check (about 10 minutes)
Run from `absolute-kinema/`:
```bash
python scripts/make_video.py validate ../examples/earthquakes/project.yaml
python scripts/make_video.py preview  ../examples/earthquakes/project.yaml --times 6.2,12.9,16.3,22.9
python scripts/make_video.py render   ../examples/earthquakes/project.yaml
ffprobe -v error -show_entries stream=codec_type ../examples/earthquakes/output/earthquakes.mp4
python scripts/make_video.py verify-captions ../examples/earthquakes/project.yaml
```
**Expected**
- `validate`: `OK: 4 scenes, 27.4 s, timing exact for 68/70 words ...; 2 word(s) partially estimated`.
  A small number of partially estimated words is normal for Kokoro (merged phoneme groups).
- `ffprobe`: one `video` and one `audio` stream.
- QA report: `issues: none`, about −16 LUFS, true peak ≤ −1 dBFS, captions `NOT VERIFIED`.
- `verify-captions`: 0 possible missing-word spots. The "heard" transcripts are rough. The
  offline recogniser is American English, so treat them as weak evidence only.

**Real lead-in silence check** (the rc2 fix). The first 0.5 s should decode to RMS 0.0, even when
container timestamps are ignored:
```bash
ffmpeg -v error -i ../examples/earthquakes/output/earthquakes.mp4 -map 0:a -t 0.5 -f s16le - | \
  python3 -c "import sys,numpy as n;x=n.frombuffer(sys.stdin.buffer.read(),n.int16).astype(float);print('RMS',(x**2).mean()**.5)"
```

## Human checks (cannot be automated)
1. **Preview approval:** content, look, and visuals matching the words.
2. **Caption approval:** watch with sound, read every caption, then run
   `approve-captions --name "Your Name"` yourself. The agent must never run this step.
3. **Facts:** the skill cannot check them.

## Independent test history
| Version | Tester | Result |
|---|---|---|
| v0.1 | Independent fresh session (`compound_interest` project) | Usability findings, fixed in v0.2 |
| v0.4-rc1 | Independent fresh session (earthquakes project), [`evidence/INDEPENDENT_TEST_REPORT_v0.4-rc1.md`](../evidence/INDEPENDENT_TEST_REPORT_v0.4-rc1.md) | Not ready: 1 blocker, 1 moderate, docs. All fixed in rc2 |
| v0.4-rc2 | Independent assessment (volcano demo), [`evidence/RELEASE_ASSESSMENT_v0.4-rc2.md`](../evidence/RELEASE_ASSESSMENT_v0.4-rc2.md) | **GO, with documented limitations** |
