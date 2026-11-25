# Known limitations (v0.4.0-rc2)

These ship with the release. None of them blocks release. They are recorded honestly, not fixed,
because this release finishes v0.4 rather than starting v0.5.

## Verification scope
1. **Platform:** tested only on Ubuntu 24.04 x86_64 with Python 3.13.18 and FFmpeg 6.1.1. macOS,
   Windows and other Linux distributions are untested.
2. **Voices:** only Kokoro `bf_emma` has been reviewed by a human listener. The other 10 Kokoro
   voices are implemented but unreviewed.
3. **Piper** is implemented but not verified end to end. Its voices are hosted only on Hugging
   Face, which the development environment could not reach.
4. **Captions are never machine-verified.** Every render starts `NOT VERIFIED` until a human runs
   `approve-captions`. The bundled example's captions are unapproved.
5. **Facts and teaching quality** cannot be checked by the skill.

## Timing and captions
6. **Kokoro merged phoneme groups:** in connected speech Kokoro sometimes runs two words together
   (for example "in the"). Those words get a localised, syllable-weighted estimate inside their real
   combined duration. All other words are exact. This happened in every Kokoro project tested
   (2/70 words in the earthquake example, 2/91 in the volcano demo). `validate` reports it.
7. **espeak-ng British voices fail forced alignment**, because PocketSphinx ships only an
   American-English model. Timing then falls back to estimates, loudly. Kokoro is unaffected. Use
   `voice: en-us` if you need aligned espeak timing.
8. **`verify-captions` "heard" transcripts are rough** for British voices (the recogniser is
   American English). Only the missing-word count is informative, so a pass is weak evidence. A
   person must still listen.
9. **Misleading alignment-failure message:** a very short user recording can make PocketSphinx
   return nothing (`TypeError: 'NoneType' object is not iterable`). The fallback to estimated timing
   works and is reported, but the warning wrongly blames British voices.
10. **AI narration pacing** is uniform (a fixed ~0.35 s between sentences). There is no control over
    emphasis, pitch or emotion beyond overall speed.

## Visuals
11. **Fixed visual vocabulary:** 20 icons, no shape or diagram primitives, and no subject-specific
    icons (no volcano, tectonic plate or fault). Topic diagrams must be supplied as images, as both
    test projects did with original Pillow drawings.
12. **No motion inside a diagram:** images can bob, sway or zoom, and swap on cues, but nothing
    moves within them. There is no character animation or lip-sync.
13. **Bullets and checklists don't wrap:** long items can run off-frame, and neither `validate` nor
    QA warns. Keep items short and check the preview.
14. **Preview stills:** the automatic preview shows only a few stills, which can miss cue moments.
    Use `preview --times t1,t2,...` to check them.
15. **Format:** 1920×1080 only; 24, 25 or 30 fps.

## Workflow and performance
16. **Running the CLI inside the skill folder writes files there:** running `validate` on the
    bundled `water_cycle` example creates `examples/water_cycle/work/`, and tests create caches.
    This repository's `.gitignore` excludes them. Keep your own projects outside the skill folder.
17. **Render speed:** about 3.5× real time on 4 cores, and about 5× on 2 workers. A 30-second video
    takes roughly 2–3 minutes.
18. **Kokoro needs a one-time ~136 MB download** from GitHub Releases. It works offline after that.
19. **Duration:** designed for 10–60 s. Test projects ran 13–33 s. `validate` prints a per-project
    word-count rule of thumb for estimated timing.
20. **Test plan wording:** `V0.4_RC2_FRESH_SESSION_TEST_PLAN.md` names the expected skip as
    `NO_ESPEAK`. In practice it is the `AE_TEST_AUDIO` test.

## Proposed for a future version (not in this release)
Wrap or warn on overlong bullet and checklist items. Handle `d.seg() is None` in `align.py` and
report a generic "alignment failed". Write example work files outside the package. Correct the test
plan's skip wording. Review more Kokoro voices.
