#!/usr/bin/env python3
"""AbsoluteKinema (absolute-kinema): make a short educational animation from a YAML project file.

  python3 scripts/make_video.py new my_project            create a project from the template
  python3 scripts/make_video.py validate my_project/project.yaml
  python3 scripts/make_video.py preview  my_project/project.yaml [--times 1,4,8]
  python3 scripts/make_video.py render   my_project/project.yaml [--draft]
  python3 scripts/make_video.py verify-captions  my_project/project.yaml
  python3 scripts/make_video.py approve-captions my_project/project.yaml --name "Your Name"
  python3 scripts/make_video.py qa       my_project/output/<name>.mp4 --project my_project/project.yaml
  python3 scripts/make_video.py icons                       list built-in icon names
  python3 scripts/make_video.py voices [--engine espeak|piper|kokoro]   list available AI narration voices
"""
import argparse, os, shutil, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
SKILL = os.path.dirname(HERE)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("new"); p.add_argument("folder")
    for name in ("validate", "preview", "render", "verify-captions", "approve-captions"):
        p = sub.add_parser(name); p.add_argument("project")
        if name == "preview": p.add_argument("--times", default=None, help="comma-separated seconds")
        if name == "render": p.add_argument("--draft", action="store_true", help="half resolution, faster")
        if name == "approve-captions": p.add_argument("--name", required=True)
    p = sub.add_parser("qa"); p.add_argument("mp4"); p.add_argument("--project", required=True)
    sub.add_parser("icons")
    p = sub.add_parser("voices"); p.add_argument("--engine", choices=["espeak", "piper", "kokoro"], default="espeak")
    a = ap.parse_args()

    if a.cmd == "icons":
        from ae.scene import ICONS
        print("Built-in icons:", ", ".join(ICONS)); return
    if a.cmd == "voices":
        from ae import tts
        if a.engine == "kokoro":
            voices = tts.list_voices("kokoro")
            print("Voices for engine 'kokoro' (default: bf_emma - see README.md's 'Kokoro voices'):")
            for vid, desc in sorted(voices.items()):
                print(f"  {vid:14s} {desc}")
            return
        voices = tts.list_voices(a.engine)
        if not voices:
            avail = tts.espeak_available() if a.engine == "espeak" else tts.piper_available()
            print(f"No voices found for engine '{a.engine}'" + ("" if avail else " (the engine itself is not installed - see README.md)."))
            return
        print(f"Voices for engine '{a.engine}':")
        for vid, desc in sorted(voices.items()):
            print(f"  {vid:20s} {desc}")
        return
    if a.cmd == "new":
        if os.path.exists(a.folder): sys.exit(f"{a.folder} already exists - choose a new folder name.")
        os.makedirs(a.folder)
        shutil.copy(os.path.join(SKILL, "templates", "project_template.yaml"), os.path.join(a.folder, "project.yaml"))
        shutil.copy(os.path.join(SKILL, "templates", "brief_template.md"), os.path.join(a.folder, "brief.md"))
        print(f"Created {a.folder}/project.yaml and {a.folder}/brief.md. Edit them, then run validate."); return

    from ae.config import load, ConfigError
    try:
        cfg = load(a.project if a.cmd != "qa" else a.project)
    except ConfigError as e:
        sys.exit(str(e))
    if a.cmd == "validate":
        from ae.render import build_timing
        T = build_timing(cfg)
        print(f"OK: {len(cfg['scenes'])} scenes, {T.duration:.1f} s, timing {T.source}.")
        for sc, (s0, s1) in zip(cfg["scenes"], T.spans):
            print(f"  {sc.get('id', '?'):12s} {s0:5.2f}-{s1:5.2f} s  transition={sc.get('transition', 'fade')}")
        # Narration-length guidance (findings from the v0.1 fresh-session test: getting the word
        # count right for a target duration took an extra iteration because there was no rule of
        # thumb to work from). Only shown for estimated timing - once a real recording is aligned,
        # the actual duration already reflects the true speaking pace.
        if "partially estimated" in T.source:
            print("  note: most words have exact, model-native timing; a few (merged phoneme "
                  "groups in connected speech) use a localized estimate instead - see SKILL.md "
                  "'AI narration' for what this means and why.")
        script = cfg["narration"]["script"] or []
        words = sum(len(str(s["text"]).split()) for s in script)
        if words and T.source.startswith("estimated"):
            offset = cfg["narration"]["offset"]; outro = cfg.get("outro_hold", 1.5)
            speaking_s = T.duration - offset - outro
            rate = speaking_s / words
            print(f"  narration: {words} words -> ~{speaking_s:.1f}s of speech at this pace "
                  f"(~{rate:.2f}s/word), + {offset:.1f}s lead-in + {outro:.1f}s outro hold = {T.duration:.1f}s total.")
            print(f"  rule of thumb for a NEW target duration: words ≈ (target_seconds - "
                  f"{offset + outro:.1f}) / {rate:.2f}")
        # resolve every cue now so typos are caught before rendering
        from ae.scene import pos_of
        bad = []
        for si, sc in enumerate(cfg["scenes"]):
            for el in sc.get("elements") or []:
                for key in ("at", "until", "pulse"):
                    if el.get(key) is not None:
                        try: T.cue(si, el[key])
                        except ValueError as e: bad.append(str(e))
                for sub_ in (el.get("cues") or []) + (el.get("ticks") or []) + [n.get("at") for n in el.get("nodes", []) if isinstance(n, dict)]:
                    if sub_ is not None:
                        try: T.cue(si, sub_)
                        except ValueError as e: bad.append(str(e))
        if bad: sys.exit("Cue problems:\n  - " + "\n  - ".join(bad))
        return
    if a.cmd == "preview":
        from ae.render import build_timing, work_dir
        from ae import scene
        from ae.contact_sheet import build_contact_sheet
        T = build_timing(cfg); s = float(cfg["render"]["preview_scale"])
        times = [float(x) for x in a.times.split(",")] if a.times else \
            [round((s0 + s1) / 2, 2) for s0, s1 in T.spans] + [round(T.duration - 0.8, 2)]
        d = os.path.join(work_dir(cfg), "preview"); os.makedirs(d, exist_ok=True)
        from PIL import Image
        ims = []
        for t in times:
            im = Image.fromarray(scene.frame(cfg, T, T.caption_windows(), t, s)); im.save(f"{d}/t{t:06.2f}.png"); ims.append(im)
        build_contact_sheet(ims).save(f"{d}/contact_sheet.png")
        print(f"Preview stills in {d} (contact_sheet.png)"); return
    if a.cmd == "render":
        from ae.render import render
        from ae import qa
        from ae.render import build_timing
        final, srt, took = render(cfg, 0.5 if a.draft else 1.0)
        r, p = qa.check(cfg, final, build_timing(cfg))
        print(f"QA: {p}  issues: {r['issues'] or 'none'}  captions: {r['caption_status']}"); return
    if a.cmd == "verify-captions":
        from ae.captions import verify
        p, ev = verify(cfg)
        print(f"{len(ev['possible_mismatch'])} possible missing-word spots. Read {p}, listen, then approve."); return
    if a.cmd == "approve-captions":
        from ae.captions import approve
        print("Approval recorded:", approve(cfg, a.name)); return
    if a.cmd == "qa":
        from ae import qa
        from ae.render import build_timing
        r, p = qa.check(cfg, a.mp4, build_timing(cfg)); print(p, r["issues"] or "no automatic issues")


if __name__ == "__main__":
    main()
