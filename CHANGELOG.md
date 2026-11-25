# Changelog

## v0.4.0-rc2: release candidate (current)
**Renamed from `animated-explainer` to AbsoluteKinema** (skill identifier `absolute-kinema`, repository
`7onsieur/absolute-kinema`). The rename changed only the skill folder name, `name:` in `SKILL.md`, titles,
comments, docstrings and the CLI help text; no behaviour changed, and the full test suite was re-run
after the rename. The cache folder `~/.cache/animated-explainer/kokoro`, `AE_KOKORO_MODEL_DIR` and the `ae`
module keep their names for compatibility. Development reports and test evidence from before the
rename keep the old name as a historical record.

The **v0.4-rc2 implementation** (package ZIP SHA-256 `c7972aef47757fc0e8b03228ff4cfa96a81eb98d6f71fdaaccbd6a52ecc55b19`).
The skill reports `version: 0.4.0-rc2`. Released under the MIT licence. A final v0.4.0 waits on human caption
approval. An independent assessment rated it
"GO, with documented limitations" ([`evidence/`](evidence/README.md)). Release preparation re-ran the test suite
(46 passed, 1 skipped, including in a fresh virtual environment), re-rendered the earthquake example
with rc2, and confirmed the lead-in silence fix on real output. No code was changed.

### What changed in rc2
Fixes every finding from the independent rc1 test:
- Kokoro tests find the model through the skill's own cache logic (`AE_KOKORO_MODEL_DIR`, or
  `~/.cache/animated-explainer/kokoro`) instead of a developer-only path.
- The 0.6 s narration lead-in is written as real silent samples, not an MP4 timestamp gap, so audio stays in
  sync in tools that ignore container timestamps. Two new tests.
- `validate` reports "exact for N/M words; K partially estimated" instead of a blanket "exact".
- Documentation: `apt-get update` install step, no reference to the unbundled test-results file, a
  corrected section reference, the template version label, consistent duration guidance, and a new rc2 test plan.

### v0.4-rc1
- **Kokoro-ONNX narration engine** (`engine: kokoro`): natural British voices (default `bf_emma`),
  with word timing taken from the model's own phoneme durations, so no forced alignment is needed.
- Model weights download automatically, once, from GitHub Releases.
- Merged-phoneme-group recovery: exact timing for every word except a merged pair or run (see
  `absolute-kinema/CAPTION_DRIFT_FIX_v0.4.md`).
- Render-cache invalidation: changing the narration, timing or config never reuses stale video segments.

## v0.3
Optional local AI narration (espeak-ng, and Piper, which is unverified). A `voices` command.
Per-sentence alignment. A loud fallback to estimated timing when alignment fails (espeak-ng British
voices). A duration safety net. New QA checks: missing audio, possible missing words, subtitle timing.
37 tests. See `absolute-kinema/DEVELOPMENT_REPORT_v0.3.md`.

## v0.2
Changes from the first independent usability test: ambiguous word cues are rejected (`word#N`
selector), `validate` prints word-count and pace guidance, unused contact-sheet cells are marked,
fades are configurable, and every element type is documented in the template. 21 tests. See
`absolute-kinema/DEVELOPMENT_REPORT_v0.2.md`.

## v0.1
First reusable version, extracted from the "How AI Agents Use Skills" explainer project: YAML
projects, cue-driven elements, segmented resumable rendering, PocketSphinx alignment of user
recordings, and human caption approval.
