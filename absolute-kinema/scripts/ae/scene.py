"""Render one frame of a project at time t (pure function of config + timing + t)."""
import math, os
import numpy as np
import cv2
from PIL import Image
from . import gfx as G
from .gfx import Canvas, INK, PURPLE, PURPLE_L, LAV, CARD, ORANGE, GREEN, RED, YELLOW, BLUE, ease, ease_out, spring, lerp, clamp01
from .config import ANCHORS, resolve

THEMES = {   # background top, bottom (0..1 RGB), text colour, sub-text colour
    "dusk": ((0.11, 0.08, 0.25), (0.20, 0.12, 0.36), (255, 255, 255), (215, 205, 245)),
    "night": ((0.04, 0.05, 0.11), (0.09, 0.11, 0.21), (255, 255, 255), (190, 200, 230)),
    "day": ((0.93, 0.95, 1.00), (0.80, 0.87, 1.00), INK, (70, 70, 100)),
    "paper": ((0.99, 0.97, 0.91), (0.94, 0.90, 0.81), INK, (95, 80, 60)),
}
TRANS_D = 0.6


def hexcol(h, default=ORANGE):
    try:
        h = str(h).lstrip("#"); return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))
    except Exception:
        return default


# ------------------------------------------------------------------ background
_BG = {}


def background(theme, t, scale, particles=True):
    W, H = int(1920 * scale), int(1080 * scale)
    key = (theme, W, H)
    if key not in _BG:
        top, bot, _, _ = THEMES[theme]
        yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
        u = (yy / H)[..., None]
        base = np.array(top) * (1 - u) + np.array(bot) * u
        vig = 1 - 0.25 * (((xx - W / 2) / W) ** 2 + ((yy - H / 2) / H) ** 2)[..., None] * 2.2
        step = max(8, int(48 * scale)); tile = np.zeros((step, step), np.float32)
        cv2.circle(tile, (step // 2, step // 2), max(1, int(2.0 * scale)), 1.0, -1, cv2.LINE_AA)
        _BG[key] = ((base * vig).astype(np.float32), tile)
    base, tile = _BG[key]
    fr = base.copy(); step = tile.shape[0]
    dark = THEMES[theme][2] != INK
    off = int(t * 6 * scale) % step
    dots = np.tile(tile, (H // step + 2, W // step + 2))[off:off + H, :W]
    fr += dots[..., None] * (np.array([0.35, 0.3, 0.6]) * 0.3 if dark else np.array([-0.08, -0.08, -0.05]))
    if particles:
        rng = np.random.default_rng(5)
        for k in range(30):
            px = (rng.uniform(0, 1920) + 9 * t * rng.uniform(-1, 1)) % 1920
            py = (rng.uniform(0, 1080) - 14 * t * rng.uniform(0.3, 1.2)) % 1080
            col = [(0.95, 0.6, 0.2), (0.6, 0.5, 1.0), (0.5, 0.9, 1.0)][k % 3]
            a = (0.30 if dark else 0.18) + 0.2 * math.sin(t * 2 + k)
            c = tuple(float(v * a + (0.12 if dark else 0.55)) for v in col)
            cv2.circle(fr, (int(px * scale), int(py * scale)), max(1, int(rng.uniform(2, 5) * scale)), c, -1, cv2.LINE_AA)
    return np.clip(fr, 0, 1)


# ------------------------------------------------------------------ icons
def icon(c, name, x, y, s=1.0, col=None):
    """Simple bold-outline icons, drawn about centre (x, y); s=1 is ~100 px."""
    c.push(x, y, s)
    n = name.lower()
    if n == "sun":
        for k in range(8):
            a = k * math.pi / 4
            c.line([(x + 38 * math.cos(a), y + 38 * math.sin(a)), (x + 52 * math.cos(a), y + 52 * math.sin(a))], w=8, fill=ORANGE)
        c.circle(x, y, 28, YELLOW, w=6)
    elif n == "cloud":
        for (dx, dy, r) in [(-24, 6, 22), (0, -10, 28), (26, 4, 22)]:
            c.circle(x + dx, y + dy, r, (240, 244, 255), w=6)
        c.rrect(x - 46, y + 2, x + 48, y + 28, 13, (240, 244, 255), w=6)
        c.rrect(x - 40, y - 4, x + 42, y + 22, 10, (240, 244, 255), outline=None)
    elif n in ("rain", "drop"):
        if n == "rain": icon(c, "cloud", x, y - 18, 0.8)
        pts = [(-18, 30), (8, 22), (30, 34)] if n == "rain" else [(0, 0)]
        for dx, dy in pts:
            sc = 0.45 if n == "rain" else 1.0
            px, py = x + dx, y + dy
            c.poly([(px, py - 40 * sc), (px + 22 * sc, py + 6 * sc), (px - 22 * sc, py + 6 * sc)], (110, 175, 255), w=5)
            c.circle(px, py + 10 * sc, 22 * sc, (110, 175, 255), w=5)
            c.ellipse(px, py + 10 * sc, 20 * sc, 18 * sc, (110, 175, 255))
    elif n in ("leaf", "plant"):
        if n == "plant":
            c.rrect(x - 26, y + 16, x + 26, y + 48, 8, (200, 120, 70), w=6)
            c.line([(x, y + 16), (x, y - 18)], w=6)
            yy = y - 20
        else:
            yy = y
        c.poly([(x, yy - 34), (x + 30, yy - 4), (x, yy + 22), (x - 30, yy - 4)], GREEN, w=6)
        c.line([(x, yy - 26), (x, yy + 16)], w=4)
    elif n == "mountain":
        c.poly([(x - 50, y + 32), (x - 10, y - 30), (x + 12, y + 2), (x + 26, y - 14), (x + 52, y + 32)], (150, 160, 190), w=6)
        c.poly([(x - 22, y - 12), (x - 10, y - 30), (x + 2, y - 12)], (255, 255, 255), w=4)
    elif n == "wave":
        for k in range(2):
            pts = [(x - 50 + i * 5, y - 6 + 16 * k + 8 * math.sin(i * 0.6)) for i in range(21)]
            c.line(pts, w=7, fill=BLUE)
    elif n == "book":
        G.book_icon(c, x - 22, y - 46, 44, 92, PURPLE)
    elif n == "globe":
        G.globe_icon(c, x, y, 40)
    elif n == "folder":
        G.folder_icon(c, x - 45, y - 32, 90)
    elif n == "doc":
        G.doc_icon(c, x - 30, y - 38, 60)
    elif n == "check":
        G.check_badge(c, x, y, 40)
    elif n == "gear":
        for k in range(8):
            a = k * math.pi / 4
            c.circle(x + 34 * math.cos(a), y + 34 * math.sin(a), 11, (190, 195, 215), w=5)
        c.circle(x, y, 32, (190, 195, 215), w=6); c.circle(x, y, 12, LAV, w=5)
    elif n == "bulb":
        c.circle(x, y - 10, 30, YELLOW, w=6)
        c.rrect(x - 14, y + 18, x + 14, y + 40, 5, (190, 195, 215), w=5)
    elif n == "person":
        c.circle(x, y - 22, 20, (240, 190, 150), w=6)
        c.rrect(x - 34, y + 4, x + 34, y + 46, 22, BLUE, w=6)
    elif n == "bot":
        G.bot(c, x, y + 8, 0.45, 0, (0.3, 0.2), 0, "happy", glow=0)
    elif n == "magnifier":
        G.magnifier(c, x - 8, y - 8, 30)
    elif n == "heart":
        c.circle(x - 16, y - 10, 20, RED, w=6); c.circle(x + 16, y - 10, 20, RED, w=6)
        c.poly([(x - 34, y - 2), (x + 34, y - 2), (x, y + 36)], RED, w=6)
        c.ellipse(x, y - 4, 32, 12, RED)
    elif n == "star":
        pts = [(x + (40 if k % 2 == 0 else 17) * math.sin(k * math.pi / 5), y - (40 if k % 2 == 0 else 17) * math.cos(k * math.pi / 5)) for k in range(10)]
        c.poly(pts, YELLOW, w=6)
    else:   # unknown name -> labelled dot, never crash
        c.circle(x, y, 34, col or PURPLE_L, w=6)
        c.text(x, y, n[:2].upper(), 26, "xb", (255, 255, 255), anchor="mm")
    c.pop()


ICONS = ["sun", "cloud", "rain", "drop", "leaf", "plant", "mountain", "wave", "book", "globe", "folder", "doc",
         "check", "gear", "bulb", "person", "bot", "magnifier", "heart", "star"]


# ------------------------------------------------------------------ helpers
def wrap(c, text, size, width, kind="b"):
    words = str(text).split(); lines = []; cur = ""
    for w in words:
        t = (cur + " " + w).strip()
        if c.tlen(t, size, kind) > width and cur:
            lines.append(cur); cur = w
        else:
            cur = t
    if cur: lines.append(cur)
    return lines


def pos_of(el, default="center"):
    p = el.get("pos", default)
    return ANCHORS[p] if isinstance(p, str) else (float(p[0]), float(p[1]))


class Ctx:
    def __init__(self, cfg, timing, si, t, theme):
        self.cfg, self.T, self.si, self.t = cfg, timing, si, t
        _, _, self.fg, self.sub = THEMES[theme]
        self.accent = hexcol(cfg["style"].get("accent"))

    def cue(self, spec, default=0.0):
        return self.T.cue(self.si, spec, default)


def appear(ctx, el, default_at=0.0):
    t0 = ctx.cue(el.get("at"), default_at)
    t1 = ctx.cue(el["until"]) if el.get("until") is not None else None
    return t0, t1


def enter_transform(c, el, t, t0, cx, cy, t1=None):
    """push the element's entrance transform; returns progress u (0..1) and alpha"""
    kind = el.get("enter", "pop"); u = clamp01((t - t0) / 0.45)
    alpha = 1.0
    if t1 is not None: alpha *= 1 - clamp01((t - t1) / 0.3)
    pulse = 0.0
    if el.get("pulse") is not None:
        pt = el["_pulse_t"]; pulse = 0.12 * math.exp(-((t - pt - 0.12) / 0.12) ** 2)
    if kind == "pop":
        c.push(cx, cy, max(0.0, spring(t - t0, 2.8, 0.45)) * (1 + pulse), alpha=alpha)
    elif kind == "fade":
        c.push(cx, cy, 1 + pulse, alpha=alpha * ease(u))
    elif kind == "slide_up":
        c.push(cx, cy, 1 + pulse, alpha=alpha * ease(u), dy=60 * (1 - ease_out(u)))
    elif kind in ("slide_left", "slide_right"):
        d = 140 if kind == "slide_left" else -140
        c.push(cx, cy, 1 + pulse, alpha=alpha * ease(u), dx=d * (1 - ease_out(u)))
    else:   # draw / type / none: progressive content, no transform
        c.push(cx, cy, 1 + pulse, alpha=alpha * (1 if kind != "none" or t >= t0 else 0))
    return u


# ------------------------------------------------------------------ elements
def draw_element(c, ctx, el):
    t = ctx.t
    t0, t1 = appear(ctx, el)
    if t < t0 or (t1 is not None and t > t1 + 0.3): return
    if el.get("pulse") is not None: el["_pulse_t"] = ctx.cue(el["pulse"])
    typ = el["type"]; x, y = pos_of(el)
    col = hexcol(el["color"]) if el.get("color") else None
    u = enter_transform(c, el, t, t0, x, y, t1)
    if typ == "title":
        size = el.get("size", 78)
        if el.get("tag"):
            G.pill(c, x, y - size * 0.95, str(el["tag"]).upper(), 24, ctx.accent)
        txt = str(el["text"])
        if el.get("enter") == "type": txt = txt[:int(len(txt) * clamp01((t - t0) / max(0.4, len(txt) * 0.045)))]
        lines = wrap(c, txt, size, el.get("width", 1500), "xb") or [""]
        for k, ln in enumerate(lines):
            c.text(x, y + k * size * 1.12 - (len(lines) - 1) * size * 0.56, ln, size, "xb", col or ctx.fg, anchor="mm")
        if el.get("subtitle"):
            c.text(x, y + len(lines) * size * 0.56 + 40, str(el["subtitle"]), el.get("subtitle_size", 34), "sb", ctx.sub, anchor="mm")
    elif typ == "text":
        size = el.get("size", 40); width = el.get("width", 1100)
        lines = wrap(c, el["text"], size, width)
        for k, ln in enumerate(lines):
            yy = y + (k - (len(lines) - 1) / 2) * size * 1.3
            c.text(x, yy, ln, size, "b", col or ctx.fg, anchor="mm")
    elif typ == "card":
        w = el.get("width", 560); body = wrap(c, el.get("body", ""), 30, w - 80, "sb") if el.get("body") else []
        has_icon = bool(el.get("icon"))
        h = 90 + 42 * len(body) + (110 if has_icon else 0)
        x0, y0 = x - w / 2, y - h / 2
        c.rrect(x0, y0, x0 + w, y0 + h, 28, CARD, w=6, shadow=1)
        yy = y0 + 30
        if has_icon:
            icon(c, el["icon"], x, yy + 50, 0.8); yy += 110
        c.text(x, yy + 22, str(el["title"]), 38, "xb", INK, anchor="mm")
        for k, ln in enumerate(body):
            c.text(x, yy + 72 + 42 * k, ln, 30, "sb", (70, 66, 90), anchor="mm")
    elif typ == "icon":
        s = el.get("size", 140) / 100
        if el.get("badge", True):
            c.circle(x, y, 70 * s, (250, 248, 255), w=6)
        icon(c, el["name"], x, y, s * (0.8 if el.get("badge", True) else 1.0), col)
        if el.get("label"):
            c.text(x, y + 70 * s + 34, str(el["label"]), el.get("label_size", 32), "xb", ctx.fg, anchor="mm")
        if el.get("bob"):
            pass
    elif typ == "bullets":
        items = el["items"]; size = el.get("size", 40); gap = size * 1.6
        x0 = x - el.get("width", 900) / 2
        cues = el.get("cues") or [None] * len(items)
        for k, it in enumerate(items):
            tk = ctx.cue(cues[k], 0) if cues[k] is not None else t0 + k * el.get("stagger", 0.5)
            if t < tk: continue
            a = ease((t - tk) / 0.35)
            yy = y + (k - (len(items) - 1) / 2) * gap
            c.push(x0, yy, 1, alpha=a, dx=-30 * (1 - a))
            c.circle(x0 + 12, yy, 10, ctx.accent, outline=None)
            c.text(x0 + 40, yy, str(it), size, "b", col or ctx.fg)
            c.pop()
    elif typ == "checklist":
        items = el["items"]; size = el.get("size", 46); w = el.get("width", 900); gap = size * 1.7
        h = 70 + gap * len(items)
        x0, y0 = x - w / 2, y - h / 2
        c.rrect(x0, y0, x0 + w, y0 + h, 26, CARD, w=6, shadow=1)
        if el.get("title"):
            G.pill(c, x0 + 40, y0 + 2, str(el["title"]).upper(), 22, ctx.accent, anchor="lm")
        ticks = el.get("ticks") or [None] * len(items)
        for k, it in enumerate(items):
            yy = y0 + 55 + gap * k + gap / 2 - 10
            tk = ctx.cue(ticks[k], 0) if ticks[k] is not None else t0 + 0.8 + k * el.get("stagger", 0.6)
            G.tick_box(c, x0 + 40, yy, (t - tk) / 0.25, size=size * 0.8)
            c.text(x0 + 40 + size * 1.25, yy, str(it), size, "sb", INK)
    elif typ == "flow":
        nodes = el["nodes"]; n = len(nodes); width = el.get("width", 1500)
        nw, nh = el.get("node_width", 230), el.get("node_height", 210)
        xs = [x - width / 2 + nw / 2 + k * (width - nw) / max(1, n - 1) for k in range(n)] if n > 1 else [x]
        cues = [nd.get("at") if isinstance(nd, dict) else None for nd in nodes]
        times = [ctx.cue(cues[k], 0) if cues[k] is not None else t0 + k * el.get("stagger", 0.7) for k in range(n)]
        for k, nd in enumerate(nodes):
            nd = nd if isinstance(nd, dict) else {"label": str(nd)}
            tk = times[k]
            if t < tk: continue
            if k > 0:
                G.arrow(c, (xs[k - 1] + nw / 2 + 8, y), (xs[k] - nw / 2 - 8, y), ease((t - tk + 0.15) / 0.35),
                        w=7, col=ctx.fg if ctx.fg != INK else INK)
            p = max(0.0, spring(t - tk, 3.0, 0.45))
            c.push(xs[k], y, p)
            c.rrect(xs[k] - nw / 2, y - nh / 2, xs[k] + nw / 2, y + nh / 2, 28, CARD, w=6, shadow=1)
            if nd.get("icon"): icon(c, nd["icon"], xs[k], y - 25, 0.75)
            c.text(xs[k], y + nh / 2 - 38, str(nd.get("label", "")), 28, "xb", INK, anchor="mm")
            c.pop()
            if nd.get("sub"):
                c.text(xs[k], y + nh / 2 + 34, str(nd["sub"]), 26, "b", ctx.fg, anchor="mm",
                       stroke=3 if ctx.fg != INK else 0, stroke_fill=(30, 20, 40), a=clamp01((t - tk) / 0.3))
        if el.get("cycle") and n > 1:
            tc = times[-1] + 0.4
            if t > tc:
                uu = ease((t - tc) / 0.8)
                base = y + nh / 2 + (78 if any(isinstance(d, dict) and d.get("sub") for d in nodes) else 40)
                pts = [(xs[-1] - (xs[-1] - xs[0]) * i / 30, base + 70 * math.sin(math.pi * i / 30)) for i in range(31)]
                m = max(2, int(len(pts) * uu))
                c.line(pts[:m], w=7, fill=ctx.accent)
                if uu > 0.97:   # arrowhead pointing back up into the first node
                    G.arrow(c, (xs[0], base + 4), (xs[0], base - 22), 1, w=7, col=ctx.accent, head=20)
    elif typ == "arrow":
        p0 = el["from"]; p1 = el["to"]
        p0 = ANCHORS[p0] if isinstance(p0, str) else p0; p1 = ANCHORS[p1] if isinstance(p1, str) else p1
        G.arrow(c, tuple(p0), tuple(p1), ease((t - t0) / 0.5), w=el.get("width", 8), col=col or ctx.accent, head=22)
    elif typ == "image":
        im = _image(resolve(ctx.cfg, el["path"]))
        w = el.get("width", 600); h = w * im.shape[0] / im.shape[1]
        mo = el.get("motion", "none"); dy = 0; s = 1.0
        if mo == "bob": dy = 10 * math.sin(2 * math.pi * 0.5 * (t - t0))
        if mo == "zoom": s = 1 + 0.06 * clamp01((t - t0) / 6)
        if mo == "sway":
            dy = 4 * math.sin(2 * math.pi * 0.4 * (t - t0))
        c.push(x, y, s, dy=dy)
        if el.get("frame"):
            c.rrect(x - w / 2 - 10, y - h / 2 - 10, x + w / 2 + 10, y + h / 2 + 10, 24, CARD, w=6, shadow=1)
        c.paste(im, x - w / 2, y - h / 2, w)
        c.pop()
    elif typ == "counter":
        a = float(el.get("from", 0)); b = float(el["to"]); d = float(el.get("duration", 1.5))
        v = lerp(a, b, ease_out((t - t0) / d))
        fmt = "{:,.0f}" if float(b).is_integer() and float(a).is_integer() else "{:,.1f}"
        txt = f"{el.get('prefix', '')}{fmt.format(v)}{el.get('suffix', '')}"
        c.text(x, y, txt, el.get("size", 120), "xb", col or ctx.accent, anchor="mm", stroke=5, stroke_fill=INK)
        if el.get("label"):
            c.text(x, y + el.get("size", 120) * 0.75, str(el["label"]), 34, "b", ctx.fg, anchor="mm")
    c.pop()


_IMG = {}


def _image(path):
    if path not in _IMG:
        im = Image.open(path).convert("RGBA")
        if im.width > 1600: im = im.resize((1600, int(im.height * 1600 / im.width)), Image.LANCZOS)
        _IMG[path] = np.asarray(im).astype(np.float32) / 255
    return _IMG[path]


# ------------------------------------------------------------------ captions
def draw_caption(c, windows, t):
    for chunk, sa, sb in windows:
        if sa <= t <= sb:
            a = clamp01((t - sa) / 0.08) * clamp01((sb - t) / 0.08)
            size = 46; sp = c.tlen(" ", size, "xb")
            ws = [c.tlen(w, size, "xb") for w, _, _ in chunk]
            tot = sum(ws) + sp * (len(ws) - 1); x = 960 - tot / 2; y = 1000
            c.rrect(x - 30, y - 42, x + tot + 30, y + 38, 20, (20, 17, 26, 225), outline=None, a=a)
            for (wd, w0, w1), wl in zip(chunk, ws):
                c.text(x, y, wd, size, "xb", (255, 160, 40) if w0 <= t < w1 else (255, 255, 255), a=a)
                x += wl + sp
            return


# ------------------------------------------------------------------ frame
def scene_layer(cfg, T, si, t, scale):
    sc = cfg["scenes"][si]
    theme = sc.get("theme", cfg["style"]["theme"])
    bg = background(theme, t, scale, cfg["style"].get("particles", True))
    c = Canvas(scale)
    a, b = T.spans[si]
    z0, z1 = (sc.get("camera") or {}).get("zoom", [1.0, 1.04])
    z = lerp(z0, z1, ease((t - a) / max(0.5, b - a)))
    c.push(960, 540, z)
    ctx = Ctx(cfg, T, si, t, theme)
    for el in sc.get("elements") or []:
        draw_element(c, ctx, dict(el))
    c.pop()
    return G.over(bg, c.result())


def transition(kind, A, B, u, scale, center=(960, 540)):
    u = ease(u)
    if kind == "cut": return B if u >= 0.5 else A
    if kind == "fade": return A * (1 - u) + B * u
    H, W = A.shape[:2]
    if kind == "slide":
        off = int(W * u); out = np.empty_like(A)
        out[:, :W - off] = A[:, off:]; out[:, W - off:] = B[:, :off]
        return out
    xx = np.arange(W)[None, :, None].astype(np.float32)
    if kind == "wipe":
        m = np.clip((u * (W + 200) - 100 - xx) / 60, 0, 1)
        return A * (1 - m) + B * m
    if kind == "circle":
        yy = np.arange(H)[:, None, None].astype(np.float32)
        d = np.sqrt((xx - center[0] * scale) ** 2 + (yy - center[1] * scale) ** 2)
        r = u * 2300 * scale
        m = np.clip((r - d) / (4 * scale), 0, 1)
        ring = np.exp(-((d - r) / (12 * scale)) ** 2) * (0.02 < u < 0.98)
        return np.clip(A * (1 - m) + B * m + ring * np.array([1.0, 0.65, 0.25]) * 0.8, 0, 1)
    return B


def frame(cfg, T, windows, t, scale=1.0):
    si = T.scene_at(t)
    out = scene_layer(cfg, T, si, t, scale)
    a, _ = T.spans[si]
    if si > 0:
        kind = cfg["scenes"][si].get("transition", "fade")
        if kind != "cut" and t < a + TRANS_D:
            u = (t - a) / TRANS_D
            prev = scene_layer(cfg, T, si - 1, t, scale)
            out = transition(kind, prev, out, u, scale)
    if cfg["captions"]["enabled"] and windows:
        c = Canvas(scale); draw_caption(c, windows, t); out = G.over(out, c.result())
    fade_in = float(cfg.get("intro_fade", 0.3))
    fade_out = float(cfg.get("outro_fade", 0.6))
    if fade_in > 0 and t < fade_in: out = out * ease(t / fade_in)
    if fade_out > 0 and t > T.duration - fade_out:
        out = out * (1 - ease((t - (T.duration - fade_out)) / fade_out))
    return (np.clip(out, 0, 1) * 255 + 0.5).astype(np.uint8)
