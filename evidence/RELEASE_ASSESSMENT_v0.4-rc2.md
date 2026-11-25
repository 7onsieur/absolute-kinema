# animated-explainer v0.4-rc2: independent release assessment

Tester environment: Ubuntu 24.04 x86_64, Python 3.13.18, FFmpeg 6.1.1. ZIP SHA-256 starts `c7972aef…`.
Source tree diffed against a pristine unzip: identical, except that running `validate` on
`examples/water_cycle` created an `examples/water_cycle/work/` directory inside the package.

## Recommendation: GO, with documented limitations (READY WITH DOCUMENTED LIMITATIONS)
No release-blocking defect found. The GO is conditional on one step I cannot do: a human listening
for voice naturalness and approving captions (test plan step 7). I verified timing, silence and
text by measurement. I did not listen to the audio, and captions remain NOT VERIFIED.

## Pass/fail
| # | Check | Result |
|---|---|---|
| 1 | Install per README | PASS (espeak-ng was absent and the documented apt step supplied it). Plain `pip` without `--break-system-packages` not tested separately. |
| 2 | Test suite, no weights | 43 passed, 4 skipped (Kokoro tests skip silently, as documented) |
| 2 | Test suite, with weights | PASS: 46 passed, 1 skipped (`AE_TEST_AUDIO`, unrelated). Kokoro tests executed. |
| 3 | `voices --engine kokoro` / espeak | PASS: 11 Kokoro voices, `bf_emma` marked as reviewed |
| 4 | Model download and validate | PASS (about 20 s). Outcome: partially estimated (9/11 words exact). |
| 5 | Render, ffprobe, QA | PASS: video and audio streams, SRT, QA clean |
| 5 | Lead-in as real PCM | PASS: first 0.5 s RMS = 0.0, max 0, also with `-ignore_editlist 1`. Voice onset decodes at 0.60–0.65 s. |
| 6 | `verify-captions` | PASS: 0 missing-word spots (see limitation 4) |
| 8 | Silent, espeak, user-recording paths | PASS (one recording failed alignment, see bug 2) |
| 9 | Cache invalidation | PASS: narration change cleared 3 of 3 segments, visual-only change cleared 4 of 4, unchanged re-render reused 4 of 4 |
| 7 | Human voice and caption judgment | NOT DONE: needs you |

## Demo video (volcano, bf_emma, 32.9 s, 1920x1080, 30 fps)
- Narration: 91 words, timing exact for 89/91. **Estimated words: "in" and "the" (s3, about 14.56–14.69 s in the narration audio)**, a merged phoneme group.
- Decoded-audio sentence onsets sit 29–66 ms before my expected times. The offsets are steady from s1 to s6, so **no cumulative drift**. Offsets are about 80 ms early, a trailing-release tail.
- A second aligner (PocketSphinx, US model) matched Kokoro word starts with a median of 80 ms and a maximum of 160 ms, on the pre-correction narration.
- SRT text equals script text exactly. 16 captions, none overlapping or backwards. Captions lead first-word onset by about 30–120 ms (by design).
- Frame check at cue points: stage images swap on sentence cues, bullets appear on "lava", "ash" and "gas", and checklist ticks follow "bubbles", "builds" and the cracking.
- QA report: no issues, -16.2 LUFS, true peak -1.5 dBFS, no frozen spans.
- Scientific correction applied as requested. Sentence 6 now reads "As the pressure drops, the eruption slows or stops, and the volcano goes quiet." Final diagram: "Eruption slows / Pressure drops / Magma still in chamber".

## Reproducible bugs and issues
Release-blocking: none.

Minor, for V0.5 (or a one-line doc note):
1. `bullets` do not wrap. `width` only centres the block, so long items run off-frame and `validate` and QA do not warn. Repro: a bullet "Magma chamber: where the magma collects" at size 38, width 600, pos x=1530.
2. Alignment-failure message is misleading. A user recording of "Plants make food from sunlight and water." (espeak en-us, 3.2 s) failed with `TypeError: 'NoneType' object is not iterable`, because PocketSphinx `d.seg()` returned None. The warning blames "British voices", which is not the cause. A longer clip aligned fine. The fallback to estimated timing was loud and correct.
3. Running `validate` on the shipped example writes a `work/` directory into the package folder.
4. Test plan inaccuracies: the expected single skip is `AE_TEST_AUDIO`, not `NO_ESPEAK`; and the one-line plan sentence gave a partial result, not the "common case" of fully exact.
5. Render speed: 158 s for 33 s of video, about 5x real time, on 2 workers.

## Capability limits for this brief
- No shape or diagram primitives and no volcano icon. Diagrams must be supplied images. I drew six original stages with Pillow, outside the package (`project_source/make_diagrams.py`).
- Diagrams are static stages that cross-fade on cues. There is no motion inside a diagram (magma does not flow).
- Preview gives only one still per scene, so sentence-level stage changes cannot be checked pre-render.

## Limitations (shipping with the release)
1. Not verified: other platforms, Kokoro voices other than `bf_emma`, Piper with Hugging Face access.
2. Kokoro merged-phoneme words get a localized estimate. This happened in both of my Kokoro projects.
3. Voice quality and caption sync are not human-verified by me.
4. `verify-captions` "heard" transcripts are mostly gibberish for the British voice (e.g. "didn't the grounds…"). Only the missing-word count is informative, so a pass is weak evidence.
5. Install was not run on a clean machine without root-managed Python packages.

## Proposed fixes (not applied)
Wrap or warn on bullets and checklist overflow. Catch the `d.seg() is None` case in `align.py` and report it as "alignment failed". Write example work files outside the package, or add a `.gitignore`. Correct the test plan's skip description.
