# Independent test report: animated-explainer v0.4-rc1

**Date:** 2026-11-20 · **Tester:** independent fresh session (no prior development context)
**Package:** `animated-explainer-v0.4-rc1.zip`, SHA-256 `4c532057ff222d8a6f62e8840ed4355960f1ffd085b3b43a414c36c9a48d7a5c`
**Platform:** Ubuntu 24.04.5 LTS x86_64, 4 cores / 15 GB, Python 3.13.18, FFmpeg 6.1.1 (matches the documented tested platform exactly)

## Verdict: **NOT READY for public release — close (one blocker, several minor fixes)**

The core pipeline works well: install, validate, preview, render, QA and caption review all ran
without errors, and the Kokoro `bf_emma` narration was synthesised, rendered into the MP4 and
captioned with tight sync (≤ 0.08 s, no drift). The blocker is that the shipped test suite **cannot
test the v0.4 headline feature (Kokoro) on any machine except the developer's**. Minor issues are a
missing install step, an MP4 audio-timing robustness risk, and several documentation errors. None
needed source changes to work around for this test. Human caption review is still outstanding.

## Test-plan results

| Step | Result | Notes |
|---|---|---|
| 0. Prerequisites | PASS | Platform identical to the tested one |
| 1. Install | PASS* | *`apt-get install` failed until `apt-get update` was run (undocumented). pip install clean |
| 2. Test suite | **FAIL vs. expectation** | 41 passed, **4 skipped** (docs: "1 skip"). 3 Kokoro tests always skip — see B1 |
| 3. Kokoro voices | PASS | 11 voices, `bf_emma` flagged as reviewed |
| 4. Validate + model download | PASS | 136 MB downloaded automatically from GitHub Releases; validate ~57 s incl. download |
| 5. Preview / render / QA | PASS | Render 96 s (4 workers), QA: no issues |
| 6. verify-captions | PASS | 0 possible-missing-word spots |
| 7. Human caption/voice review | **PENDING — user** | Not approved by the tester, as required |
| 8. Regression (silent example, espeak voices) | PASS | |
| 9. Render-cache invalidation | Not attempted | Optional; out of scope for this run |

## Test project: "How Earthquakes Happen"

- 5 sentences / 70 words, 4 scenes (title → plates drifting → locked fault swapping to a
  rupture on "snaps" → seismic waves), dusk theme, Kokoro `bf_emma`, speed 1.0.
- The built-in icons include no geology visuals, so 4 simple original diagrams (drawn with Pillow for this
  test, no third-party assets) were used through the `image` element.
- Preview approved by the user at human checkpoint 1.

### Deliverables
| File | Path |
|---|---|
| Video (1920×1080, 30 fps, H.264 + AAC 48 kHz mono, 27.43 s) | `<test-workspace>/earthquakes/output/earthquakes.mp4` |
| Subtitles (12 cues, unapproved) | `<test-workspace>/earthquakes/output/earthquakes.UNVERIFIED.srt` |
| QA report | `<test-workspace>/earthquakes/output/earthquakes.qa_report.md` |
| Caption review | `<test-workspace>/earthquakes/output/earthquakes.captions_review.md` |
| 1-fps contact sheet of the MP4 | `<test-workspace>/earthquakes/output/earthquakes_contact_sheet.png` |
| Project file / brief | `<test-workspace>/earthquakes/project.yaml`, `brief.md` |

## QA results (skill's own + independent checks)

| Check | Result |
|---|---|
| Resolution / fps / duration | 1920×1080, 30 fps, 27.43 s (target 20–30 s) ✅ |
| Clean decode | ✅ no errors |
| Frozen spans | none ✅ (one expected 1.8 s silence at the end = outro hold) |
| Loudness | −16.3 LUFS integrated, **true peak −1.5 dBFS** (≤ −1 required) ✅ |
| Narration is Kokoro `bf_emma` | ✅ narration metadata says `engine: kokoro, voice: bf_emma`; MP4 audio vs the generated Kokoro WAV: **0.989** envelope correlation (0.834 waveform) |
| Caption ↔ speech sync | ✅ sentence onsets measured from the MP4 audio (timestamp-respecting decode) are 0.03–0.08 s from caption/word timings, from first sentence to last, **with no cumulative drift** |
| Word timing source | "exact" from Kokoro durations; 2/70 words ("in the", s3) used the documented merged-group estimate |
| Recogniser cross-check | rough, as documented (e.g. "athletes" for "earthquakes"); no extra/missing words |
| Visual cues & transitions | ✅ 16 frames extracted from the MP4 just before/after each cue: card on "tectonic", drift text on "centimetres", 4 bullets on lock/stress/snaps/energy, diagram swap on "snaps", heading on "seismic"; slide/wipe/circle transitions at 2.60/9.60/20.51 s; outro fade |
| Caption status | **NOT VERIFIED**: awaiting the user's own review and `approve-captions` |

**Subjective (tester):** the British voice sounded clear and natural. As a tester I'm not giving the
human sign-off; that's the user's call.

## Issues found

### Blocker
**B1. Kokoro tests are hard-wired to the developer's machine.** `tests/test_ae.py:501` sets
`_DEV_MODEL_DIR = "/home/claude/fresh_test/dev_v04_investigation/models/kokoro"`. Everywhere else, the
3 Kokoro tests (including the merged-phoneme-group regression test) skip silently, **even after the model
is downloaded to the documented default cache**. So a fresh install has zero automated coverage of
v0.4's main feature, and the "expect 1 skip" guidance is wrong. *Verification:* in a scratch copy of the
test file with only that path changed to `~/.cache/animated-explainer/kokoro`, all 5 Kokoro-related
tests **passed** (the package itself was not modified). *Suggested fix:* resolve the model directory
the way the skill does (`AE_KOKORO_MODEL_DIR` → default cache), and document that the Kokoro tests run
only after the first download (or add an opt-in download step).

### Moderate
**M1. The 0.6 s audio lead-in is stored as a timestamp gap, not as silence.** In the MP4's AAC stream,
packet timestamps jump from 0.021 s to 0.600 s (plus a smaller ~20 ms gap near 23.0 s). Standard
players and ffmpeg honour this, so playback is in sync. But anything that decodes samples sequentially
(sample-level tools, some editors/web pipelines, re-muxing without timestamps) gets audio **~0.58 s
earlier than the captions**. The raw decode was 26.84 s against a 27.41 s stream. *Suggested fix:*
make the mux produce real silent samples (e.g. `aresample=async=1` after `adelay`, or delay before
`loudnorm`), and add a QA check that decoded sample count ≈ stream duration.

**M2. The install instructions omit `apt-get update`.** On a fresh Ubuntu 24.04 image,
`apt-get install … fonts-dejavu espeak-ng` failed with "Unable to locate package" until the package lists
were updated.

### Minor / documentation
- **D1.** `SKILL.md` and `README.md` refer to `FRESH_SESSION_TEST_RESULTS.md`, which **is not in the ZIP**.
- **D2.** `voices --engine kokoro` and `requirements.txt` point to *README.md's 'Kokoro voices'*. That
  section doesn't exist (it's titled "Recommended: Kokoro-ONNX…").
- **D3.** `SKILL.md` says `validate` prints word count, pace and a target-duration formula. It does that
  **only for estimated timing** (confirmed on the silent example), not for Kokoro/exact timing. Either
  document this or print it in both modes.
- **D4.** The `validate` / `render` summary says "timing exact" even when some words fell back to the
  merged-group estimate. The detail line says so, but the headline overstates it. Suggest e.g.
  "exact (2/70 words estimated)".
- **D5.** Length guidance is inconsistent: "10–15 s" (frontmatter, README, brief template) against "up to
  about 60 s". 27 s worked fine; the docs should say what's supported.
- **D6.** `templates/project_template.yaml` is still headed "(v0.2)".
- **D7.** The test plan doesn't say the Kokoro model download happens *after* the test-suite step. That
  ordering is why the B1 skips go unnoticed.
- **D8.** The default preview gives only 5 automatic stills, which here missed the key cue moments
  (diagram swap, bullets 3–4). `--times` works well. Suggest still times based on the cues, or
  mentioning `--times` in SKILL.md step 4.
- **D9.** The built-in icons have no science-specific visuals (geology here). This is a documented
  limitation; the `image` element with your own artwork was an effective workaround.
- **D10.** Running commands inside the package (tests, the bundled example) writes `__pycache__/`,
  `.pytest_cache/` and `examples/water_cycle/work/` into the skill folder. Consider a `.gitignore`
  entry or documenting this before packaging releases.
- **D11.** apt error output still exits 0 when piped through `tail`, so install scripts can miss it.
  Minor; worth a "check the output" note.

### Undocumented steps the tester needed
1. `sudo apt-get update` before the apt install (M2).
2. `make_video.py preview --times …` to check specific cue moments (D8).
3. Creating your own artwork for topic-specific visuals (D9).

## Integrity of the package under test
- ZIP SHA-256 unchanged after testing.
- All 28 files extracted from the ZIP are **byte-identical** to the archive (CRC-checked). No Python
  source was modified. The only additions are tool-generated caches and the example's `work/` folder (D10).
- The earthquake project was created **outside** the package (`<test-workspace>/earthquakes`).
- Nothing was published to GitHub or anywhere else.

## Remaining actions for release
1. Fix B1 and update the expected test output.
2. Fix M1 (or document it) and add the sample-count QA check.
3. Fix M2 and D1–D7.
4. **User:** watch `earthquakes.mp4` with sound, read every caption, and only then run
   `python3 scripts/make_video.py approve-captions <test-workspace>/earthquakes/project.yaml --name "Your Name"`
   from the skill folder.
