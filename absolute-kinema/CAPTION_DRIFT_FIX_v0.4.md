# Caption-drift investigation: root cause and fix

## 1. Root cause — established with direct evidence, not assumed

Of the 4 sky-is-blue sentences, only **s3** ("Blue light has a shorter wavelength, so it
spreads out far more than red or yellow light.") produced a phoneme-group/word-count mismatch
(16 groups for 17 words) — Kokoro's phonemizer ran "far" and "more" together with no audible
gap. The *previous* version of the POC handled any such mismatch by discarding **all** of that
sentence's real timing and estimating **every** word's position from syllable count alone. That
estimate is only loosely correlated with real speech rhythm, so it visibly diverges from the
actual audio across the ~4.7s of that one sentence — the second half of the 19s video. That is
what the reviewer heard as captions "progressively drifting towards the end": not a bug in
offsets, inserted silence, or unit conversion (all checked and confirmed exact — see §2), but one
sentence's word-level timing being a coarse estimate instead of real data.

## 2. What was checked and ruled out

- **Cumulative sentence offsets / inserted silence / timing conversion**: the combined WAV's
  real duration (via `ffprobe` and raw sample count) matches the predicted total to the
  millisecond (19.018625s actual vs 19.0186s predicted). Each sentence's start offset is derived
  from the previous sentences' real, measured audio length, not an assumption, so these are not
  the cause.
- **"Exact" sentences cannot drift by construction**: for s1, s2, s4, word boundaries come
  directly from the same per-phoneme duration values the vocoder used to render that exact
  audio — there is no separate measurement step that could introduce error. Confirmed this isn't
  a hidden scale/rounding issue in `kokoro_onnx`'s frame→sample conversion by inspecting
  `sliding.py`'s `token_edges()` directly; it renormalizes to the real rendered sample count, so
  any single-window sentence's timing is tautologically consistent with its own audio.
- **Fourth sentence**: s4 itself got exact, model-native timing (no mismatch). The reviewer's
  framing ("fourth sentence's estimated timing") most likely reflects where the drift became
  perceptible while watching — right after s3, not that s4's own words were estimated.

## 3. Fix made — smallest change that is actually verified to work

Replaced the previous all-or-nothing fallback in `poc/kokoro_timing.py` with a localized
recovery (`_find_runs` / `_realign_merged_groups`): grow the sentence word by word, re-phonemizing
each growing prefix (text-only, no audio) and checking whether adding a word added a new phoneme
group. A word that doesn't add a new group shares a group with its neighbour — only *that* pair's
real, combined duration is split between them (by syllable weight, same formula as before, just
local); every other word keeps **exact** model-native timing.

**A first attempt at this (comparing each word's own isolated phonemization against the groups)
was tried and rejected**: it failed on ordinary function words ("has", "a") that reduce
differently in isolation than in context (e.g. "has" alone phonemizes `hˈaz`, but `hɐz` next to
"a shorter" — a real, measured vowel-reduction effect, not a guess), so it broke before even
reaching the actual merge. The growing-prefix method avoids this because it only ever uses
in-context phonemization, matching the real audio's conditions. Verified directly on the real
failing sentence and on 7 additional varied test sentences (mismatched and clean) with no
crashes or incorrect localization.

Result for s3: **15 of 17 words now get exact, model-native timing**; only "far" and "more"
(the words that actually share a merged group) are estimated, and that estimate is now confined
to their own ~0.4s combined span instead of the whole ~4.7s sentence.

## 4. Regression test and re-render

- Re-ran the fix against the real failing sentence and 7 additional varied sentences (clean and
  mismatched) — correct localization in every case, safe fallback (`None` → whole-sentence
  estimate) never triggered because the pattern held in all of them.
- Found and fixed a second, unrelated issue while re-rendering: `render.py`'s segment cache keys
  purely on file existence, not content, so my first re-render after the fix silently reused
  segment video files rendered *before* the fix (a stale-cache artifact of this investigation's
  own testing, not a bug in the shipped pipeline's normal resume behaviour). Cleared the segment
  cache and re-rendered properly; `sky_is_blue.mp4`, `.UNVERIFIED.srt`, and the QA report attached
  are from that clean re-render.
- `timing_diagnostics.json` (attached) now shows s3 as `"method": "partial"` with the two
  affected words individually flagged.

## 5. What is and isn't verified

- **Verified independently of me**: nothing. This fix has not been confirmed by listening — that
  is the next step, and it's yours. The numbers above are measured facts about the code and the
  timing data, not a claim that the drift is now imperceptible.
- **Not changed**: the Kokoro-ONNX voice/audio content, the caption approval system (still
  correctly `NOT VERIFIED`, nothing auto-approved), the v0.3 baseline, and every other sentence's
  timing (s1/s2/s4 were already exact and are untouched).
- **Remaining limitation**: the two merged words in any affected sentence are still an estimate,
  not measured timing — just a much smaller one. A sentence with more than one merge, or a merge
  pattern the prefix-growing check can't resolve, still falls back safely to the original
  whole-sentence estimate (this did not occur in s3 or in any of the 7 extra test sentences, but
  hasn't been proven impossible).

Please listen to `sky_is_blue.mp4` and judge whether the drift is resolved; only then should
`approve-captions` be run.
