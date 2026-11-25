"""Load and validate a project file (YAML). Errors are reported in plain language
with the location of the problem, because students edit YAML, not Python."""
import os
import yaml

ELEMENT_TYPES = {
    "title": {"text"}, "text": {"text"}, "bullets": {"items"}, "card": {"title"},
    "icon": {"name"}, "flow": {"nodes"}, "checklist": {"items"}, "arrow": {"from", "to"},
    "image": {"path"}, "counter": {"to"},
}
ENTER = {"pop", "fade", "slide_up", "slide_left", "slide_right", "draw", "type", "none"}
TRANSITIONS = {"cut", "fade", "slide", "wipe", "circle"}
THEMES = {"dusk", "day", "paper", "night"}
ANCHORS = {
    "center": (960, 500), "top": (960, 200), "bottom": (960, 800), "left": (480, 500), "right": (1440, 500),
    "top-left": (420, 220), "top-right": (1500, 220), "bottom-left": (420, 780), "bottom-right": (1500, 780),
}
DEFAULTS = {
    "output": {"name": "explainer", "width": 1920, "height": 1080, "fps": 30},
    "style": {"theme": "dusk", "accent": "#F7931E", "particles": True, "font_dir": None},
    "narration": {"audio": None, "offset": 0.6, "script": [],
                  "tts": {"enabled": False, "engine": "espeak", "voice": None, "speed": 1.0,
                          "kokoro_model_dir": None}},
    "captions": {"enabled": True, "max_chars": 42},
    "render": {"segment_seconds": 2.0, "workers": 0, "memory_limit_gb": 3.0, "preview_scale": 0.5},
    "outro_hold": 1.5,
    "intro_fade": 0.3,   # seconds of fade-in from black at the very start; 0 disables it
    "outro_fade": 0.6,   # seconds of fade-out to black at the very end; 0 disables it
}


class ConfigError(Exception):
    pass


def _merge(d, defaults):
    out = dict(defaults)
    for k, v in (d or {}).items():
        out[k] = _merge(v, defaults[k]) if isinstance(v, dict) and isinstance(defaults.get(k), dict) else v
    return out


def load(path):
    if not os.path.exists(path):
        raise ConfigError(f"Project file not found: {path}")
    with open(path, encoding="utf-8") as f:
        try:
            raw = yaml.safe_load(f) or {}
        except yaml.YAMLError as e:
            raise ConfigError(f"The project file is not valid YAML (check indentation and colons):\n{e}")
    cfg = _merge(raw, DEFAULTS)
    cfg["scenes"] = raw.get("scenes") or []
    cfg["title"] = raw.get("title", "Untitled explainer")
    cfg["_dir"] = os.path.dirname(os.path.abspath(path))
    cfg["_path"] = os.path.abspath(path)
    problems = validate(cfg)
    if problems:
        raise ConfigError("Please fix these problems in the project file:\n  - " + "\n  - ".join(problems))
    # If narration.tts.enabled is set and no narration.audio, synthesize the narration now
    # and point narration.audio at it, so every other part of the pipeline (alignment,
    # rendering, caption approval, QA) treats AI-generated narration exactly like a user's
    # own recording - see ae/tts.py. This is the one place config.load() has a side effect,
    # and only when the project file opts in.
    from .tts import ensure_narration_audio
    try:
        ensure_narration_audio(cfg)
    except (ValueError, RuntimeError) as e:
        raise ConfigError(f"Could not generate AI narration (narration.tts): {e}")
    return cfg


def resolve(cfg, rel):
    """paths in the project file are relative to the project file's folder"""
    if rel is None: return None
    return rel if os.path.isabs(rel) else os.path.normpath(os.path.join(cfg["_dir"], rel))


def validate(cfg):
    p = []
    o = cfg["output"]
    if not str(o.get("name", "")).replace("_", "").replace("-", "").isalnum():
        p.append("output.name should use only letters, numbers, '-' or '_' (it becomes the file name).")
    if (o["width"], o["height"]) != (1920, 1080):
        p.append("output width/height: only 1920x1080 is supported.")
    if o["fps"] not in (24, 25, 30):
        p.append("output.fps must be 24, 25 or 30.")
    for key in ("intro_fade", "outro_fade", "outro_hold"):
        try:
            if float(cfg.get(key, 0)) < 0:
                p.append(f"{key} must be 0 or a positive number of seconds.")
        except (TypeError, ValueError):
            p.append(f"{key} must be a number of seconds.")
    if cfg["style"]["theme"] not in THEMES:
        p.append(f"style.theme must be one of {sorted(THEMES)}.")
    script = cfg["narration"]["script"] or []
    ids = []
    for i, s in enumerate(script):
        if not isinstance(s, dict) or "id" not in s or "text" not in s:
            p.append(f"narration.script[{i}] needs both 'id' and 'text' (e.g. - id: s1\\n  text: \"...\").")
            continue
        ids.append(str(s["id"]))
    if len(ids) != len(set(ids)):
        p.append("narration.script: every sentence id must be unique.")
    audio = cfg["narration"]["audio"]
    if audio and not os.path.exists(resolve(cfg, audio)):
        p.append(f"narration.audio file not found: {audio}")
    if audio and not script:
        p.append("narration.audio is set, so narration.script must contain exactly what is said in the recording.")
    tts = cfg["narration"].get("tts") or {}
    if tts.get("enabled"):
        if audio:
            p.append("narration.audio and narration.tts.enabled are both set - use only one "
                     "(remove narration.audio to use AI narration, or set tts.enabled: false to use a recording).")
        if not script:
            p.append("narration.tts.enabled is set, so narration.script must contain the sentences to narrate.")
        if tts.get("engine", "espeak") not in ("espeak", "piper", "kokoro"):
            p.append("narration.tts.engine must be 'espeak', 'piper' or 'kokoro'.")
        try:
            if not (0.5 <= float(tts.get("speed", 1.0)) <= 2.0):
                raise ValueError
        except (TypeError, ValueError):
            p.append("narration.tts.speed must be a number between 0.5 and 2.0.")
        if tts.get("engine") == "piper" and not tts.get("voice"):
            p.append("narration.tts.voice (path to a downloaded Piper .onnx voice file) is required "
                      "when narration.tts.engine is 'piper'.")
        if tts.get("engine") == "kokoro" and tts.get("voice"):
            from .kokoro_tts import list_voices as _kokoro_voices
            if tts.get("voice") not in _kokoro_voices():
                p.append(f"narration.tts.voice '{tts.get('voice')}' is not a known Kokoro voice "
                          f"(use one of {sorted(_kokoro_voices())}, or leave it unset for the default).")
    if not cfg["scenes"]:
        p.append("Add at least one scene under 'scenes:'.")
    used = set()
    for si, sc in enumerate(cfg["scenes"]):
        where = f"scenes[{si}]" + (f" ({sc.get('id')})" if isinstance(sc, dict) and sc.get("id") else "")
        if not isinstance(sc, dict):
            p.append(f"{where} must be a mapping with 'id', 'duration' or 'narration', and 'elements'."); continue
        nar = sc.get("narration") or []
        if isinstance(nar, str): nar = [nar]
        for n in nar:
            if str(n) not in ids:
                p.append(f"{where}: narration id '{n}' is not in narration.script.")
            used.add(str(n))
        if not nar and not sc.get("duration"):
            p.append(f"{where}: give either 'duration' (seconds) or 'narration' (sentence ids).")
        if sc.get("transition", "fade") not in TRANSITIONS:
            p.append(f"{where}: transition must be one of {sorted(TRANSITIONS)}.")
        for ei, el in enumerate(sc.get("elements") or []):
            w = f"{where}.elements[{ei}]"
            t = el.get("type") if isinstance(el, dict) else None
            if t not in ELEMENT_TYPES:
                p.append(f"{w}: unknown type '{t}'. Use one of {sorted(ELEMENT_TYPES)}."); continue
            miss = ELEMENT_TYPES[t] - set(el)
            if miss:
                p.append(f"{w} ({t}) is missing: {', '.join(sorted(miss))}.")
            if el.get("enter", "pop") not in ENTER:
                p.append(f"{w}: enter must be one of {sorted(ENTER)}.")
            pos = el.get("pos", "center")
            if not ((isinstance(pos, str) and pos in ANCHORS) or (isinstance(pos, (list, tuple)) and len(pos) == 2)):
                p.append(f"{w}: pos must be a named spot {sorted(ANCHORS)} or [x, y] in a 1920x1080 frame.")
            if t == "image" and not os.path.exists(resolve(cfg, el.get("path", ""))):
                p.append(f"{w}: image not found: {el.get('path')}")
    unused = [i for i in ids if i not in used]
    if unused and cfg["scenes"]:
        p.append(f"These narration sentences are not attached to any scene: {', '.join(unused)}.")
    return p
