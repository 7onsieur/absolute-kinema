"""Automated tests for AbsoluteKinema (absolute-kinema).  Run:  python3 -m pytest -q tests/
The optional alignment test runs only if AE_TEST_AUDIO and AE_TEST_SCRIPT point to a
real recording and a YAML list of {id, text} sentences matching it."""
import os, re, sys, json, wave, shutil, subprocess, textwrap
import numpy as np
import pytest
import yaml

SKILL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(SKILL, "scripts"))
from ae import config, timing, scene, render, captions, contact_sheet, tts, qa, align   # noqa: E402

NO_ESPEAK = pytest.mark.skipif(not tts.espeak_available(), reason="espeak-ng is not installed (apt-get install espeak-ng)")

TINY = textwrap.dedent("""
    title: Tiny test
    output: {name: tiny, fps: 24}
    style: {theme: night, particles: false}
    render: {segment_seconds: 1.0, workers: 2}
    outro_hold: 0.2
    narration:
      offset: 0.2
      script:
        - {id: a, text: "Plants make food from light."}
    scenes:
      - id: one
        narration: [a]
        elements:
          - {type: title, text: "Tiny", pos: center}
          - {type: icon, name: leaf, pos: right, at: "light"}
      - id: two
        duration: 0.8
        transition: wipe
        elements:
          - {type: text, text: "The end", pos: center}
""")


def write(tmp_path, text, name="project.yaml"):
    p = tmp_path / name; p.write_text(text); return str(p)


# ---------------------------------------------------------------- config
def test_template_and_example_validate():
    for p in ("templates/project_template.yaml", "examples/water_cycle/project.yaml"):
        cfg = config.load(os.path.join(SKILL, p))
        assert cfg["scenes"]


def test_friendly_errors(tmp_path):
    bad = TINY.replace("type: title", "type: banner").replace("narration: [a]", "narration: [zz]")
    with pytest.raises(config.ConfigError) as e:
        config.load(write(tmp_path, bad))
    msg = str(e.value)
    assert "unknown type 'banner'" in msg and "narration id 'zz'" in msg and "not attached to any scene" in msg


def test_bad_yaml_message(tmp_path):
    with pytest.raises(config.ConfigError, match="not valid YAML"):
        config.load(write(tmp_path, "title: [unclosed"))


# ---------------------------------------------------------------- timing
def test_timing_and_cues(tmp_path):
    cfg = config.load(write(tmp_path, TINY))
    T = timing.Timing(cfg)
    ws = T.words["a"]
    assert all(b > a for _, a, b in ws) and all(ws[i][2] <= ws[i + 1][1] + 1e-9 for i in range(len(ws) - 1))
    assert T.spans[0][0] == 0 and abs(T.spans[0][1] - T.spans[1][0]) < 1e-9
    assert T.cue(0, "light") == pytest.approx([w for w in ws if w[0].startswith("light")][0][1])
    assert T.cue(0, "a") == pytest.approx(ws[0][1])
    assert T.cue(0, "light+0.3") == pytest.approx(T.cue(0, "light") + 0.3)
    assert T.cue(1, 0.5) == pytest.approx(T.spans[1][0] + 0.5)
    with pytest.raises(ValueError):
        T.cue(0, "banana")


def test_caption_chunking_rules(tmp_path):
    long = ("It picks a presentation skill, follows its steps, turns my notes into an outline, "
            "and builds a draft for me to review with a friend.")
    cfg = config.load(write(tmp_path, TINY.replace("Plants make food from light.", long)))
    T = timing.Timing(cfg)
    chunks = T.caption_chunks()
    texts = [" ".join(w for w, _, _ in c) for c in chunks]
    assert " ".join(texts) == long                                        # nothing lost or reordered
    for t in texts[:-1]:
        assert len(t) <= cfg["captions"]["max_chars"] + 8
        last = re.sub(r"[^\w']", "", t.split()[-1].lower())
        assert t[-1] in ",.?!;:" or last not in timing.FUNCTION_WORDS   # no dangling 'a', 'the', 'with'…
    win = T.caption_windows()
    assert all(win[i][2] <= win[i + 1][1] + 1e-9 for i in range(len(win) - 1))   # never overlap


def test_srt_format(tmp_path):
    cfg = config.load(write(tmp_path, TINY))
    T = timing.Timing(cfg); p = tmp_path / "x.srt"; T.write_srt(str(p))
    blocks = p.read_text().strip().split("\n\n")
    assert blocks and all(re.match(r"\d+\n\d\d:\d\d:\d\d,\d{3} --> \d\d:\d\d:\d\d,\d{3}\n.+", b) for b in blocks)


# ---------------------------------------------------------------- drawing
def test_every_element_and_transition_renders(tmp_path):
    img = tmp_path / "art.png"
    from PIL import Image
    Image.new("RGBA", (200, 120), (200, 80, 40, 255)).save(img)
    els = [
        {"type": "title", "text": "T", "subtitle": "s", "tag": "x"}, {"type": "text", "text": "hello world " * 5},
        {"type": "bullets", "items": ["a", "b"]}, {"type": "card", "title": "C", "body": "b b b", "icon": "gear"},
        {"type": "checklist", "items": ["x", "y"], "title": "Steps"}, {"type": "arrow", "from": "left", "to": "right"},
        {"type": "flow", "nodes": [{"label": "A", "icon": "sun"}, {"label": "B", "icon": "nope"}], "cycle": True},
        {"type": "image", "path": str(img), "motion": "bob", "frame": True}, {"type": "counter", "to": 42, "suffix": "%"},
    ] + [{"type": "icon", "name": n, "pos": [100 + 80 * i, 900]} for i, n in enumerate(scene.ICONS)]
    for tr in ("cut", "fade", "slide", "wipe", "circle"):
        d = {"title": "x", "output": {"name": "e"}, "scenes": [
            {"id": "a", "duration": 1, "elements": [els[0]]},
            {"id": "b", "duration": 2, "transition": tr, "elements": els}]}
        cfg = config.load(write(tmp_path, yaml.safe_dump(d)))
        T = timing.Timing(cfg)
        for t in (0.5, 1.2, 2.5):
            fr = scene.frame(cfg, T, [], t, 0.25)
            assert fr.shape == (270, 480, 3) and fr.dtype == np.uint8


# ---------------------------------------------------------------- render + resume
def _dur(p):
    return float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", p],
                                capture_output=True, text=True).stdout)


def test_render_and_resume(tmp_path):
    cfg = config.load(write(tmp_path, TINY))
    logs = []
    final, srt, _ = render.render(cfg, scale=0.25, log=logs.append)
    T = timing.Timing(cfg)
    assert os.path.exists(final) and abs(_dur(final) - T.duration) < 0.15
    assert srt is None                                                       # no audio -> no SRT
    sd = os.path.join(render.work_dir(cfg), "segments_s0.25")
    segs = sorted(f for f in os.listdir(sd) if f.startswith("seg_") and f.endswith(".mp4"))
    keep = os.path.getmtime(os.path.join(sd, segs[0]))
    os.remove(os.path.join(sd, segs[-1]))                                    # simulate an interrupted render
    logs.clear(); render.render(cfg, scale=0.25, log=logs.append)
    assert any(f"({len(segs) - 1} already done)" in l for l in logs)          # only the missing one re-rendered
    assert os.path.getmtime(os.path.join(sd, segs[0])) == keep
    assert abs(_dur(final) - T.duration) < 0.15


def test_memory_limit_failure_is_reported_not_hung(tmp_path):
    txt = TINY.replace("workers: 2}", "workers: 1, memory_limit_gb: 0.05}")
    cfg = config.load(write(tmp_path, txt))
    logs = []
    with pytest.raises(RuntimeError, match="Re-run the same command to resume"):
        render.render(cfg, scale=0.25, log=logs.append)
    assert any("retrying (2/2)" in l for l in logs)


# ---------------------------------------------------------------- captions approval
def _tone(path, secs=1.0):
    sr = 16000; t = np.arange(int(sr * secs)) / sr
    with wave.open(str(path), "w") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr)
        w.writeframes((0.2 * np.sin(2 * np.pi * 220 * t) * 32767).astype(np.int16).tobytes())


def test_caption_approval_is_bound_to_audio_and_script(tmp_path):
    _tone(tmp_path / "voice.wav")
    txt = TINY.replace("offset: 0.2", "offset: 0.2\n  audio: voice.wav")
    cfg = config.load(write(tmp_path, txt))
    assert captions.status(cfg) == "NOT VERIFIED" and captions.srt_path(cfg).endswith(".UNVERIFIED.srt")
    captions.approve(cfg, "Tester")
    assert captions.status(cfg).startswith("VERIFIED") and captions.srt_path(cfg).endswith("tiny.srt")
    cfg2 = config.load(write(tmp_path, txt.replace("from light", "from sunlight")))
    assert "out of date" in captions.status(cfg2)


# ---------------------------------------------------------------- v0.2 regressions
# These cover the findings from the v0.1 fresh-session reproducibility test
# (FRESH_SESSION_TEST_RESULTS.md): ambiguous word cues silently resolving to the wrong
# occurrence, contact-sheet unused cells looking like black video frames, no narration-length
# guidance, and the undocumented/non-configurable ending fade.

REPEATED_WORD = textwrap.dedent("""
    title: amb
    output: {name: amb}
    narration:
      script:
        - {id: s1, text: "One year, then one more year, then one final year."}
    scenes:
      - id: a
        narration: [s1]
        elements: [{type: title, text: x}]
""")


def test_ambiguous_word_cue_is_rejected_not_silently_first_match(tmp_path):
    cfg = config.load(write(tmp_path, REPEATED_WORD))
    T = timing.Timing(cfg)
    with pytest.raises(ValueError, match="ambiguous"):
        T.cue(0, "year")
    # the error should point the user at both escape hatches, not just name the problem
    try:
        T.cue(0, "year")
    except ValueError as e:
        assert "sentence id" in str(e) and "#2" in str(e)


def test_occurrence_selector_disambiguates_repeated_words(tmp_path):
    cfg = config.load(write(tmp_path, REPEATED_WORD))
    T = timing.Timing(cfg)
    t1, t2, t3 = T.cue(0, "year#1"), T.cue(0, "year#2"), T.cue(0, "year#3")
    assert t1 < t2 < t3
    # sentence-id cues are untouched by ambiguity in the same scene
    assert T.cue(0, "s1") == pytest.approx(T.spans[0][0] + 0.6)
    with pytest.raises(ValueError, match="only appears 3 time"):
        T.cue(0, "year#4")
    with pytest.raises(ValueError, match="1 or higher"):
        T.cue(0, "year#0")


def test_unique_word_cue_still_works_without_sentence_id(tmp_path):
    cfg = config.load(write(tmp_path, TINY))
    T = timing.Timing(cfg)
    assert T.cue(0, "light") == pytest.approx([w for w in T.words["a"] if w[0].startswith("light")][0][1])


def test_water_cycle_example_cues_unaffected_by_ambiguity_fix():
    # the shipped example's offset-style cues (e.g. "heats-0.2") must keep resolving exactly
    # as before - this is a regression guard for the cue() rewrite, not a new behaviour.
    cfg = config.load(os.path.join(SKILL, "examples/water_cycle/project.yaml"))
    T = timing.Timing(cfg)
    for spec in ("heats-0.2", "evaporates-0.1", "clouds-0.1", "rain-0.1", "flows-0.1"):
        assert T.cue(1, spec) > 0


# ---------------------------------------------------------------- v0.2: contact sheet
def test_contact_sheet_unused_cells_are_not_black():
    from PIL import Image
    stills = [Image.new("RGB", (40, 40), c) for c in [(255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 255, 0)]]
    sheet = contact_sheet.build_contact_sheet(stills)   # 3 cols x 2 rows -> 2 unused cells
    arr = np.array(sheet)
    cw, ch = contact_sheet.CELL_W, contact_sheet.CELL_H
    # bottom-right cell (index 5) is unused: must not be black, and must look like the
    # dedicated "unused" fill, not a rendered frame
    corner = arr[ch + 20: ch + 60, 2 * cw + 20: 2 * cw + 60]
    assert corner.mean() > 15                      # not black
    assert tuple(corner[0, 0]) == contact_sheet.UNUSED_FILL
    # a real still (top-left, red) must render unchanged, not be mistaken for "unused"
    real = arr[20:60, 20:60]
    assert real[..., 0].mean() > 200 and real[..., 1].mean() < 50   # still red-dominant


def test_contact_sheet_exact_fit_has_no_unused_cells():
    from PIL import Image
    stills = [Image.new("RGB", (40, 40), (10, 20, 30))] * 3   # exactly fills 1 row of 3
    sheet = contact_sheet.build_contact_sheet(stills)
    assert sheet.size == (3 * contact_sheet.CELL_W, contact_sheet.CELL_H)


def test_contact_sheet_rejects_empty_list():
    with pytest.raises(ValueError):
        contact_sheet.build_contact_sheet([])


# ---------------------------------------------------------------- v0.2: duration guidance
def test_validate_prints_word_count_and_rule_of_thumb(tmp_path):
    p = write(tmp_path, TINY)
    r = subprocess.run([sys.executable, "-I", os.path.join(SKILL, "scripts", "make_video.py"), "validate", p],
                        capture_output=True, text=True)
    assert r.returncode == 0
    assert "words ->" in r.stdout and "rule of thumb" in r.stdout and "words" in r.stdout.split("rule of thumb")[1]


# ---------------------------------------------------------------- v0.2: configurable fade
def test_outro_fade_defaults_preserve_v01_behaviour(tmp_path):
    cfg = config.load(write(tmp_path, TINY))
    T = timing.Timing(cfg)
    assert cfg["intro_fade"] == 0.3 and cfg["outro_fade"] == 0.6
    bright_mid = scene.frame(cfg, T, [], T.duration / 2, 0.25).mean()
    dim_end = scene.frame(cfg, T, [], T.duration - 0.05, 0.25).mean()
    assert dim_end < bright_mid * 0.3   # fades out close to the very end, same as v0.1


def test_outro_fade_zero_disables_the_fade(tmp_path):
    cfg = config.load(write(tmp_path, TINY + "outro_fade: 0\n"))
    T = timing.Timing(cfg)
    bright_mid = scene.frame(cfg, T, [], T.duration / 2, 0.25).mean()
    end = scene.frame(cfg, T, [], T.duration - 0.05, 0.25).mean()
    assert end > bright_mid * 0.6   # no forced dimming when outro_fade is 0


def test_negative_fade_is_a_validation_error(tmp_path):
    with pytest.raises(config.ConfigError, match="intro_fade"):
        config.load(write(tmp_path, TINY + "intro_fade: -1\n"))


# ---------------------------------------------------------------- optional real alignment
@pytest.mark.skipif(not os.environ.get("AE_TEST_AUDIO"), reason="set AE_TEST_AUDIO + AE_TEST_SCRIPT to run")
def test_alignment_on_real_recording(tmp_path):
    from ae import align
    script = yaml.safe_load(open(os.environ["AE_TEST_SCRIPT"]))
    wav = align.to_wav(os.environ["AE_TEST_AUDIO"], str(tmp_path / "a.wav"))
    words = align.align(script, wav)
    flat = [x for s in script for x in words[str(s["id"])]]
    assert all(b >= a for _, a, b in flat) and all(flat[i][1] <= flat[i + 1][1] for i in range(len(flat) - 1))
    ev = align.verify(script, wav, words)
    assert "uncovered_speech" in ev


# ---------------------------------------------------------------- v0.3: AI narration (ae/tts.py)
TTS_TINY = textwrap.dedent("""
    title: tts tiny
    output: {name: ttstiny, fps: 24}
    render: {segment_seconds: 1.0, workers: 1}
    outro_hold: 0.2
    narration:
      offset: 0.3
      script:
        - {id: a, text: "Sunlight looks white, but it is really a mix of every colour."}
        - {id: b, text: "Blue light has a shorter wavelength than red light."}
      tts: {enabled: true, engine: espeak, voice: en-us, speed: 1.0}
    scenes:
      - id: one
        narration: [a]
        elements: [{type: title, text: "Tiny", pos: center}]
      - id: two
        narration: [b]
        elements: [{type: text, text: "The end", pos: center}]
""")


def test_apply_spoken_overrides_substitutes_whole_words_only():
    out = tts.apply_spoken_overrides("Check out GitHub.com today", {"GitHub.com": "git hub dot com"})
    assert out == "Check out git hub dot com today"
    assert tts.apply_spoken_overrides("nothing to change", None) == "nothing to change"


def test_synth_script_rejects_bad_engine_and_speed(tmp_path):
    script = [{"id": "a", "text": "hi"}]
    with pytest.raises(ValueError, match="unknown TTS engine"):
        tts.synth_script(script, str(tmp_path / "o.wav"), engine="nope")
    with pytest.raises(ValueError, match="0.5 and 2.0"):
        tts.synth_script(script, str(tmp_path / "o.wav"), engine="espeak", speed=9)
    with pytest.raises(ValueError, match="empty"):
        tts.synth_script([], str(tmp_path / "o.wav"), engine="espeak")


def test_piper_without_voice_file_gives_actionable_error(tmp_path):
    # Piper itself may or may not be installed in a given environment; either way, a missing
    # voice file must raise a clear, specific error, not a generic crash.
    script = [{"id": "a", "text": "hello"}]
    with pytest.raises(RuntimeError, match="Piper|piper"):
        tts.synth_script(script, str(tmp_path / "o.wav"), engine="piper", voice="/no/such/voice.onnx")


@NO_ESPEAK
def test_espeak_voices_lists_british_english_variants():
    voices = tts.espeak_voices()
    assert "en-gb" in voices and "en-gb-x-rp" in voices
    assert tts.list_voices("espeak") == voices


@NO_ESPEAK
def test_synth_script_concatenates_sentences_with_spans(tmp_path):
    script = [{"id": "s1", "text": "Hello there."}, {"id": "s2", "text": "General greetings."}]
    out = str(tmp_path / "n.wav")
    tts.synth_script(script, out, engine="espeak", voice="en-us", speed=1.0, log=lambda *a: None)
    assert os.path.exists(out) and os.path.exists(out + ".spans.json")
    spans = json.load(open(out + ".spans.json"))
    assert set(spans) == {"s1", "s2"}
    (a0, a1), (b0, b1) = spans["s1"], spans["s2"]
    assert a0 == 0 and a1 > a0 and b0 >= a1 and b1 > b0          # sequential, non-overlapping
    assert abs(_dur(out) - b1) < 0.05                            # file length matches last span end


# ---------------------------------------------------------------- v0.3: config validation
def test_config_rejects_audio_and_tts_both_set(tmp_path):
    txt = TTS_TINY.replace("offset: 0.3", "offset: 0.3\n  audio: x.wav")
    (tmp_path / "x.wav").write_bytes(b"RIFF....WAVEfmt ")   # just needs to exist for the audio-file check
    with pytest.raises(config.ConfigError, match="both set"):
        config.load(write(tmp_path, txt))


def test_config_rejects_unknown_tts_engine(tmp_path):
    txt = TTS_TINY.replace("engine: espeak", "engine: nope")
    with pytest.raises(config.ConfigError, match="'espeak', 'piper' or 'kokoro'"):
        config.load(write(tmp_path, txt))


def test_config_rejects_bad_tts_speed(tmp_path):
    txt = TTS_TINY.replace("speed: 1.0", "speed: 9")
    with pytest.raises(config.ConfigError, match="0.5 and 2.0"):
        config.load(write(tmp_path, txt))


def test_config_requires_voice_for_piper_engine(tmp_path):
    txt = TTS_TINY.replace("engine: espeak, voice: en-us, ", "engine: piper, ")
    with pytest.raises(config.ConfigError, match="piper"):
        config.load(write(tmp_path, txt))


# ---------------------------------------------------------------- v0.3: end-to-end AI narration
@NO_ESPEAK
def test_tts_narration_generated_and_treated_like_a_recording(tmp_path):
    cfg = config.load(write(tmp_path, TTS_TINY))
    # config.load() resolved narration.tts into a real audio file, exactly as if the user had
    # pointed narration.audio at their own recording - nothing downstream needs to know it's AI.
    assert cfg["narration"]["audio"] and os.path.exists(config.resolve(cfg, cfg["narration"]["audio"]))
    assert captions.status(cfg) == "NOT VERIFIED"                 # never auto-verified
    captions.approve(cfg, "Tester")
    assert captions.status(cfg).startswith("VERIFIED")


@NO_ESPEAK
def test_tts_audio_aligns_to_real_timings_not_estimates(tmp_path):
    # en-us is the voice verified (see DEVELOPMENT_REPORT_v0.3.md) to align reliably against
    # PocketSphinx's bundled (American English) acoustic model.
    cfg = config.load(write(tmp_path, TTS_TINY))
    T = render.build_timing(cfg, log=lambda *a: None)
    assert T.source == "aligned to recording" and not T.alignment_warning
    assert T.duration > 0


@NO_ESPEAK
def test_tts_render_produces_audible_mp4_and_srt(tmp_path):
    # scale=1.0 (full resolution) because SRT export is skipped for sub-1.0 preview renders -
    # same existing rule as for a human recording, unrelated to TTS.
    cfg = config.load(write(tmp_path, TTS_TINY))
    final, srt, _ = render.render(cfg, scale=1.0, log=lambda *a: None)
    assert os.path.exists(final) and srt and os.path.exists(srt)
    r, _ = qa.check(cfg, final, render.build_timing(cfg, log=lambda *a: None))
    assert r["has_audio"] is True
    assert not any("ESTIMATED" in i for i in r["issues"])
    assert r.get("possible_missing_words") == 0


def test_alignment_failure_falls_back_to_estimate_instead_of_crashing(tmp_path, monkeypatch):
    # Simulates the verified failure mode (PocketSphinx forced alignment can fail outright on
    # some TTS voices) without depending on espeak-ng or accent-specific flakiness: whatever the
    # cause, build_timing() must degrade to estimated timing with a loud warning, never crash.
    def boom(*a, **k):
        raise TypeError("'NoneType' object is not iterable")
    monkeypatch.setattr(align, "align_segments", boom)
    monkeypatch.setattr(align, "align", boom)
    _tone(tmp_path / "voice.wav", secs=2.0)
    cfg = config.load(write(tmp_path, TINY.replace("offset: 0.2", "offset: 0.2\n  audio: voice.wav")))
    T = render.build_timing(cfg, log=lambda *a: None)
    assert T.alignment_warning and "estimated" in T.source
    assert T.duration > 0   # still produced something usable


def test_duration_safety_net_never_shortens_real_narration_audio(tmp_path, monkeypatch):
    # If timing (estimated or aligned) under-shoots the real audio's own length, build_timing()
    # must extend the last scene so the final mux never trims off real speech.
    _tone(tmp_path / "voice.wav", secs=5.0)   # much longer than the estimate for one short sentence
    cfg = config.load(write(tmp_path, TINY.replace("offset: 0.2", "offset: 0.2\n  audio: voice.wav")))
    monkeypatch.setattr(align, "align", lambda *a, **k: (_ for _ in ()).throw(TypeError("boom")))
    T = render.build_timing(cfg, log=lambda *a: None)
    assert T.duration >= 5.0 + cfg["narration"]["offset"] + cfg["outro_hold"] - 0.05


# ---------------------------------------------------------------- v0.3: extended QA checks
def test_check_srt_flags_malformed_overlapping_and_backwards_timestamps(tmp_path):
    good = ("1\n00:00:00,000 --> 00:00:01,000\nHi\n\n"
            "2\n00:00:01,000 --> 00:00:02,000\nThere\n\n")
    p = tmp_path / "good.srt"; p.write_text(good)
    assert qa._check_srt(str(p)) == []

    backwards = good.replace("00:00:00,000 --> 00:00:01,000", "00:00:01,000 --> 00:00:00,000")
    p2 = tmp_path / "bad1.srt"; p2.write_text(backwards)
    assert any("not after" in m for m in qa._check_srt(str(p2)))

    overlap = ("1\n00:00:00,000 --> 00:00:02,000\nHi\n\n"
               "2\n00:00:01,000 --> 00:00:03,000\nThere\n\n")
    p3 = tmp_path / "bad2.srt"; p3.write_text(overlap)
    assert any("overlap" in m for m in qa._check_srt(str(p3)))

    assert qa._check_srt(str(tmp_path / "missing.srt")) and "missing" in qa._check_srt(str(tmp_path / "missing.srt"))[0]


def test_qa_flags_missing_audio_stream_when_narration_audio_is_set(tmp_path):
    _tone(tmp_path / "voice.wav")
    cfg = config.load(write(tmp_path, TINY.replace("offset: 0.2", "offset: 0.2\n  audio: voice.wav")))
    final, srt, _ = render.render(cfg, scale=0.25, log=lambda *a: None)
    silent_copy = str(tmp_path / "no_audio.mp4")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", final, "-c:v", "copy", "-an", silent_copy], check=True)
    r, _ = qa.check(cfg, silent_copy, render.build_timing(cfg, log=lambda *a: None))
    assert any("no audio stream" in i for i in r["issues"])


# ---------------------------------------------------------------- v0.4: Kokoro-ONNX narration
from ae import kokoro_tts  # noqa: E402

try:
    import kokoro_onnx  # noqa: F401
    HAS_KOKORO_ONNX = True
except ImportError:
    HAS_KOKORO_ONNX = False

# Locate the Kokoro model weights the SAME way the skill itself does (ae.kokoro_tts.DEFAULT_MODEL_DIR:
# the AE_KOKORO_MODEL_DIR environment variable if set, else the standard per-user cache
# ~/.cache/animated-explainer/kokoro) - NEVER a developer-specific hardcoded path. A hardcoded
# sandbox path here was a v0.4-rc1 release blocker found by an independent fresh-session test: it
# made these tests fail to locate real, already-downloaded models in any other environment. If a
# tester already has the models cached (from ordinary use, or from setting AE_KOKORO_MODEL_DIR
# before running the suite), these tests run for real; otherwise they skip rather than fail or fake it.
_TEST_KOKORO_MODEL_DIR = kokoro_tts.DEFAULT_MODEL_DIR
HAS_KOKORO_MODEL = HAS_KOKORO_ONNX and all(
    os.path.exists(os.path.join(_TEST_KOKORO_MODEL_DIR, f)) for f in (kokoro_tts.MODEL_FILE, kokoro_tts.VOICES_FILE))
NO_KOKORO_MODEL = pytest.mark.skipif(
    not HAS_KOKORO_MODEL,
    reason=f"kokoro-onnx or its model weights are not available at {_TEST_KOKORO_MODEL_DIR} "
           f"(set AE_KOKORO_MODEL_DIR to a folder that has {kokoro_tts.MODEL_FILE} and {kokoro_tts.VOICES_FILE} "
           f"to run these tests for real)")

KOKORO_TINY = TTS_TINY.replace("engine: espeak, voice: en-us, speed: 1.0",
                                f"engine: kokoro, voice: bf_emma, speed: 1.0, kokoro_model_dir: {_TEST_KOKORO_MODEL_DIR}")


def test_merge_localization_recovers_exact_timing_for_unaffected_words():
    """The real, measured failure mode (see CAPTION_DRIFT_FIX_v0.4.md): Kokoro's phonemizer ran
    'far' and 'more' together with no gap (16 phoneme groups for 17 words). This must recover
    exact timing for every word except the pair that actually merged, not discard the whole
    sentence's real timing."""
    if not HAS_KOKORO_MODEL:
        pytest.skip(f"kokoro-onnx or its model weights are not available at {_TEST_KOKORO_MODEL_DIR}")
    from kokoro_onnx import Kokoro
    k = Kokoro(*kokoro_tts.model_paths(_TEST_KOKORO_MODEL_DIR))
    text = "Blue light has a shorter wavelength, so it spreads out far more than red or yellow light."
    audio, sr, result = kokoro_tts.sentence_word_timing(k, text, "bf_emma", lang="en-gb", speed=1.0)
    assert result.method == "partial"
    words = [w.word for w in result.words]
    assert words == text.split()                                   # every word accounted for, in order
    estimated = [w.word for w in result.words if w.confidence != "exact"]
    assert estimated == ["far", "more"]                             # only the merged pair, not the whole sentence
    assert sum(1 for w in result.words if w.confidence == "exact") == 15


def test_merge_localization_falls_back_safely_when_unverified(monkeypatch):
    """When the growing-prefix check can't line runs up with the real groups, it must return
    None (caller's whole-sentence estimate), never guess."""
    monkeypatch.setattr(kokoro_tts, "_find_runs", lambda *a, **k: [[0], [1]])   # too few runs
    assert kokoro_tts._realign_merged_groups(None, ["a", "b", "c"], ["g1", "g2", "g3"], "en-gb") is None


def test_build_timing_uses_word_timing_sidecar_without_alignment(tmp_path, monkeypatch):
    """render.build_timing() must prefer a '<audio>.word_timing.json' sidecar over forced
    alignment whenever one exists next to the audio - exact by construction, no PocketSphinx
    involved - and this must survive a cache hit (the provenance-label bug found and fixed in
    CAPTION_DRIFT_FIX_v0.4.md §4)."""
    def boom(*a, **k):
        raise AssertionError("alignment must not run when a word_timing.json sidecar exists")
    monkeypatch.setattr(align, "align", boom)
    monkeypatch.setattr(align, "align_segments", boom)
    _tone(tmp_path / "voice.wav", secs=1.0)
    sidecar = {"a": [["Plants", 0.2, 0.5], ["make", 0.5, 0.7], ["food", 0.7, 0.9],
                     ["from", 0.9, 1.0], ["light.", 1.0, 1.1]]}
    json.dump(sidecar, open(str(tmp_path / "voice.wav") + ".word_timing.json", "w"))
    cfg = config.load(write(tmp_path, TINY.replace("offset: 0.2", "offset: 0.2\n  audio: voice.wav")))
    T = render.build_timing(cfg, log=lambda *a: None)
    assert T.source == "exact (from TTS engine's own duration output)"
    # cache hit must keep the same label, not the generic one Timing.__init__ defaults to
    T2 = render.build_timing(cfg, log=lambda *a: None)
    assert T2.source == "exact (from TTS engine's own duration output)"


def test_render_cache_invalidates_when_narration_changes(tmp_path):
    """Segment caching is by design (resumable renders), but it must never reuse a segment video
    rendered against different narration/timing/config - found and fixed in this project's own
    v0.4 testing (CAPTION_DRIFT_FIX_v0.4.md §4) after it happened for real."""
    _tone(tmp_path / "voice.wav", secs=1.0)
    cfg = config.load(write(tmp_path, TINY.replace("offset: 0.2", "offset: 0.2\n  audio: voice.wav")))
    render.render(cfg, scale=0.25, log=lambda *a: None)
    sd = os.path.join(render.work_dir(cfg), "segments_s0.25")
    before = {f: os.path.getmtime(os.path.join(sd, f)) for f in os.listdir(sd) if f.endswith(".mp4")}
    assert before
    _tone(tmp_path / "voice.wav", secs=1.6)   # same filename, different real audio -> different timing
    logs = []
    render.render(cfg, scale=0.25, log=logs.append)
    after = {f: os.path.getmtime(os.path.join(sd, f)) for f in os.listdir(sd) if f.endswith(".mp4")}
    assert any("cleared" in l and "cached segment" in l for l in logs)
    assert set(before) != set(after) or any(before[f] != after.get(f) for f in before if f in after)


@NO_KOKORO_MODEL
def test_kokoro_narration_generated_and_treated_like_a_recording(tmp_path):
    cfg = config.load(write(tmp_path, KOKORO_TINY))
    assert cfg["narration"]["audio"] and os.path.exists(config.resolve(cfg, cfg["narration"]["audio"]))
    sidecar = config.resolve(cfg, cfg["narration"]["audio"]) + ".word_timing.json"
    assert os.path.exists(sidecar)
    assert captions.status(cfg) == "NOT VERIFIED"                 # never auto-verified, same as any other engine
    captions.approve(cfg, "Tester")
    assert captions.status(cfg).startswith("VERIFIED")


@NO_KOKORO_MODEL
def test_kokoro_render_produces_audible_mp4_and_srt_with_exact_timing(tmp_path):
    cfg = config.load(write(tmp_path, KOKORO_TINY))
    final, srt, _ = render.render(cfg, scale=1.0, log=lambda *a: None)
    assert os.path.exists(final) and srt and os.path.exists(srt)
    T = render.build_timing(cfg, log=lambda *a: None)
    assert T.source == "exact (from TTS engine's own duration output)"
    r, _ = qa.check(cfg, final, T)
    assert r["has_audio"] is True
    assert r.get("possible_missing_words") == 0


def test_kokoro_model_download_failure_raises_clear_error_not_silent_fallback(tmp_path, monkeypatch):
    def boom(*a, **k):
        raise OSError("network unreachable")
    monkeypatch.setattr(kokoro_tts.urllib.request, "urlretrieve", boom)
    with pytest.raises(RuntimeError, match="free, open download") as e:
        kokoro_tts.ensure_model(model_dir=str(tmp_path / "empty_model_dir"), log=lambda *a: None)
    assert "no paid service" in str(e.value)


# ---------------------------------------------------------------- v0.4-rc2: real audio lead-in
def test_prepend_silence_wav_adds_real_zero_samples(tmp_path):
    """render._prepend_silence_wav must bake the lead-in into actual PCM data: reading the
    result's raw samples (bypassing any container/stream metadata) must show true digital
    silence for the lead-in, followed by the original audio's samples, bit for bit."""
    sr = 16000
    tone = (0.2 * np.sin(2 * np.pi * 220 * np.arange(int(sr * 0.5)) / sr) * 32767).astype(np.int16)
    src = str(tmp_path / "src.wav")
    with wave.open(src, "w") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr); w.writeframes(tone.tobytes())
    out = str(tmp_path / "out.wav")
    render._prepend_silence_wav(src, 0.6, out)
    with wave.open(out, "rb") as r:
        assert r.getframerate() == sr and r.getnchannels() == 1
        data = np.frombuffer(r.readframes(r.getnframes()), dtype=np.int16)
    n_lead = int(0.6 * sr)
    assert len(data) == n_lead + len(tone)
    assert np.all(data[:n_lead] == 0)            # real zero samples, not a timestamp/offset trick
    assert np.array_equal(data[n_lead:], tone)    # original audio is preserved exactly, unshifted


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")
def test_lead_in_silence_is_real_in_rendered_output_not_a_container_trick(tmp_path):
    """Flagged by an independent fresh-session test of v0.4-rc1 as a release blocker: the
    narration.offset lead-in must be real silent audio samples, not an MP4 start_time/edit-list
    gap a decoder could skip past. Verified here by decoding the final MP4's audio to raw PCM
    with ffmpeg's rawvideo/pcm pipe (-f s16le), which ignores all container-level timestamps -
    the lead-in region must still measure as near-silence in the actual decoded samples."""
    _tone(tmp_path / "voice.wav", secs=1.0)
    cfg = config.load(write(tmp_path, TINY.replace("offset: 0.2", "offset: 0.8\n  audio: voice.wav")))
    final, _, _ = render.render(cfg, scale=0.25, log=lambda *a: None)
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", final, "-vn", "-ac", "1", "-ar", "16000",
                          "-f", "s16le", "-"], capture_output=True, check=True).stdout
    samples = np.frombuffer(raw, dtype=np.int16).astype(np.float64)
    sr = 16000
    lead_in = samples[: int(0.7 * sr)]            # comfortably inside the 0.8s lead-in, decoded raw
    rms = float(np.sqrt(np.mean(lead_in ** 2))) if len(lead_in) else 0.0
    assert rms < 200, f"lead-in should be near-silent real samples, got RMS {rms:.1f}/32768"
    narration_zone = samples[int(0.85 * sr): int(1.0 * sr)]   # just after the lead-in ends
    narration_rms = float(np.sqrt(np.mean(narration_zone ** 2))) if len(narration_zone) else 0.0
    assert narration_rms > 500, (f"narration audio should be clearly audible shortly after the "
                                  f"lead-in ends, got RMS {narration_rms:.1f}/32768")
