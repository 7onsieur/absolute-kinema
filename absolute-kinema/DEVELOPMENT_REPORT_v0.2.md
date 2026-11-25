# animated-explainer v0.2 — development report

**Scope:** address the findings from `FRESH_SESSION_TEST_RESULTS.md` (the independent fresh-session
usability test of v0.1). Work was done in a separate copy (`dev/animated-explainer/`); the v0.1
source tree and its original zip were not touched (see "What was preserved" below).

**Not done in this pass:** publishing, GitHub, or any paid service — none were used, per
instructions. A genuinely independent fresh-session usability test of v0.2 itself (the way v0.1 was
tested) has **not** been run — see Limitations.

## Changes, mapped to the v0.1 findings

| v0.1 finding | Change in v0.2 | Where |
|---|---|---|
| No words-per-second rule of thumb; first duration draft missed the target by 5s | `validate` now prints the narration's word count, the resulting pace, and a rule-of-thumb formula for a new target duration | `scripts/make_video.py` (`validate` command) |
| Element schemas (e.g. `counter`'s `prefix`, `flow`'s `sub`/per-node `at`) undocumented in the template, forcing a read of the Python source | Every element type (`title`, `text`, `bullets`, `card`, `icon`, `checklist`, `flow`, `arrow`, `image`, `counter`) now has its full option set documented with examples, plus a dedicated "Cues" section | `templates/project_template.yaml` |
| Word cues silently resolve to the *first* matching word in a scene when the word repeats — a correctness footgun with no warning | A plain word cue that matches more than one word in the scene is now a **validation error**, naming the ambiguity and suggesting a sentence id or an occurrence selector (`"word#2"`, newly added) | `scripts/ae/timing.py` (`Timing.cue`) |
| Preview contact sheet pads unused grid cells with solid black, indistinguishable from a black video frame at a glance | Unused cells are filled with a distinct slate colour, a diagonal hatch, and an "(unused - no still here)" label; every cell (used or not) gets a thin border so the grid itself is unambiguous | New module `scripts/ae/contact_sheet.py`, used by `scripts/make_video.py` |
| The ending visibly dims over the last ~0.6s of every video, not documented, not configurable | Intro/outro fade are now named config keys (`intro_fade`, default 0.3s; `outro_fade`, default 0.6s), documented in the template and `SKILL.md`, and can be set to `0` to disable | `scripts/ae/config.py` (defaults + validation), `scripts/ae/scene.py` (`frame()`) |
| (Explicitly out of scope for this pass) No `/usr/bin/time` in the test container, so render memory was a coarse estimate | Not addressed — this was an environment limitation of the test run, not a skill defect | — |
| (Explicitly out of scope) Font install step (`apt-get install fonts-inter fonts-dejavu`) was never exercised in the v0.1 test | Not addressed — still unverified; same caveat in v0.2's README | — |

## What was preserved

- `/home/claude/fresh_test/skill_src/animated-explainer/` (the original v0.1 source, extracted from
  the user's zip) was never modified during this development pass. A `diff -rq` against it still
  shows only the known starting-state cache directories removed from the dev copy, no content
  differences introduced before development began.
- `animated-explainer-v0.1.zip` (the user's original upload) was not touched.
- `workdir/compound_interest/` — the original fresh-session test's project and rendered video — was
  not touched; it lives entirely outside the `dev/` tree used for this work.
- The caption approval system (`verify-captions` / `approve-captions`, human checkpoint 2) is
  byte-for-byte unchanged in `scripts/ae/captions.py`. No caption-accuracy claim is made anywhere in
  this report or in the v0.2 code: captions are only ever "VERIFIED" once a human runs
  `approve-captions` themselves, exactly as in v0.1.

## Testing performed

1. **Full automated suite**, `python3 -m pytest -q tests/`: **21 passed, 1 skipped** (the 1 skip is
   the audio-alignment test, which only runs with `AE_TEST_AUDIO`/`AE_TEST_SCRIPT` set — same as
   v0.1). The 11 new tests cover every change above:
   - `test_ambiguous_word_cue_is_rejected_not_silently_first_match`
   - `test_occurrence_selector_disambiguates_repeated_words`
   - `test_unique_word_cue_still_works_without_sentence_id` (regression guard)
   - `test_water_cycle_example_cues_unaffected_by_ambiguity_fix` (regression guard against the
     shipped example's own offset-style cues)
   - `test_contact_sheet_unused_cells_are_not_black`
   - `test_contact_sheet_exact_fit_has_no_unused_cells`
   - `test_contact_sheet_rejects_empty_list`
   - `test_validate_prints_word_count_and_rule_of_thumb`
   - `test_outro_fade_defaults_preserve_v01_behaviour`
   - `test_outro_fade_zero_disables_the_fade`
   - `test_negative_fade_is_a_validation_error`
2. **Manual, end-to-end render** of a new example project (`demo_v02/`, "Photosynthesis in brief",
   14.0s, 1920x1080, 30fps) exercising the fixes directly rather than just in unit tests:
   - The project's narration repeats the word "sugar" twice in one scene. A plain `at: "sugar"` cue
     was confirmed to be **rejected** by `validate` with the new ambiguity message (tested against a
     deliberately-broken copy of the project, see below) and the shipped version uses
     `at: "sugar#1"` / `at: "sugar#2"` successfully.
   - `validate` printed `narration: 27 words -> ~12.0s of speech ... rule of thumb: words ≈
     (target_seconds - 2.0) / 0.44`.
   - `preview` produced a contact sheet with 2 genuinely unused cells (6-cell grid, 4 stills),
     visibly marked, not black.
   - `render` produced a clean MP4, QA report `issues: none`. A frame extracted directly from the
     rendered file at the "Growth" node's cue confirms it lands exactly on the second "sugar", not
     the first.
   - Render took ~61s wall-clock for 14s of video on 2 cores, consistent with the v0.1 test's
     rendering performance (no regression).
3. **Negative-path check:** a copy of `demo_v02/project.yaml` with the occurrence selector removed
   (`at: "sugar#1"` → `at: "sugar"`) was validated and confirmed to fail with exit code 1 and the new
   ambiguity error, rather than silently validating and rendering the wrong cue.

## Remaining limitations (v0.2)

- **No independent fresh-session usability test of v0.2 itself.** v0.1 was tested by an agent with
  no memory of its development; v0.2 was developed and tested by the same agent/session that wrote
  it, in the same container. That's a materially weaker form of validation — this report's own
  testing cannot rule out rough edges that only surface to a genuinely fresh reader of the v0.2
  docs. Recommend running the same `FRESH_SESSION_TEST_PLAN.md`-style test against v0.2 before
  relying on it.
- **Narration-length guidance is still an estimate, not a guarantee** — the rule of thumb is derived
  from the current narration's own pace, so it's most accurate for small edits to existing text, not
  a from-scratch prediction for very different wording.
- **The occurrence selector is positional, not semantic** — reordering a scene's narration sentences
  can silently change which word a given `#N` refers to. Sentence-id cues remain the more robust
  choice and are recommended first in both the template and `SKILL.md`.
- **Cross-platform support is still unverified** (same as v0.1) — this development pass ran in the
  same Ubuntu 24.04 / Python 3.13 / FFmpeg 6.1.1 container as the v0.1 test.
- **Font installation step is still unexercised** (same as v0.1) — Inter/DejaVu were already present
  in this container both times.
- Everything else in v0.1's own "Limitations" section (`SKILL.md`) still applies unchanged: no
  character lip-sync/rigging, fixed visual vocabulary with a 20-icon set, and the skill still cannot
  check facts or judge teaching quality.

## Files changed

```
scripts/ae/timing.py          Timing.cue(): reject ambiguous word cues; add "word#N" selector
scripts/ae/config.py          DEFAULTS + validate(): intro_fade / outro_fade keys
scripts/ae/scene.py           frame(): use configurable intro_fade / outro_fade instead of hardcoded
scripts/ae/contact_sheet.py   NEW: build_contact_sheet() - marks unused preview grid cells
scripts/make_video.py         preview: use contact_sheet module; validate: word-count/duration guidance
templates/project_template.yaml   Full documentation for every element type + a Cues section
SKILL.md                      Version bump, "What's new", cue docs, troubleshooting, limitations
README.md                     Version bump, "Changed since v0.1" summary
tests/test_ae.py              11 new regression tests (see "Testing performed")
DEVELOPMENT_REPORT_v0.2.md    This file
```
