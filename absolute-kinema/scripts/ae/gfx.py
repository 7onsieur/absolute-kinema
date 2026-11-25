"""Illustrated motion-graphics toolkit (Pillow, supersampled). Ported from the original
explainer project (src/gfx.py) with font fallbacks added.

Design coordinates are 1920x1080. A Canvas renders at out_scale * SS and is
reduced to the output size, giving clean anti-aliased bold outlines that match
the character art (dark ink outline, flat fills, orange + purple accents).
"""
import math
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageChops

INK = (26, 20, 36)
PURPLE = (104, 74, 214)
PURPLE_L = (139, 112, 240)
LAV = (240, 235, 255)
CARD = (250, 248, 255)
ORANGE = (247, 147, 30)
GREEN = (60, 178, 110)
RED = (232, 76, 76)
YELLOW = (247, 190, 50)
BLUE = (70, 130, 230)
GREY = (150, 145, 165)
SKIN = (126, 60, 24)

import glob, os


def _first(*patterns):
    for p in patterns:
        hits = sorted(glob.glob(p, recursive=True))
        if hits: return hits[0]
    return None


# Inter is preferred; DejaVu (installed almost everywhere on Linux) is the fallback.
# Override with the AE_FONT_DIR environment variable or `style.font_dir` in the project file.
_FD = os.environ.get("AE_FONT_DIR", "")
_BOLD = _first(f"{_FD}/*ExtraBold*.otf", f"{_FD}/*ExtraBold*.ttf", "/usr/share/fonts/**/Inter-ExtraBold.otf",
               "/usr/share/fonts/**/DejaVuSans-Bold.ttf", "/Library/Fonts/**/*Bold*.ttf", "C:/Windows/Fonts/arialbd.ttf")
FONTS = {
    "xb": _BOLD,
    "b": _first(f"{_FD}/*-Bold.otf", "/usr/share/fonts/**/Inter-Bold.otf") or _BOLD,
    "sb": _first(f"{_FD}/*SemiBold.otf", "/usr/share/fonts/**/Inter-SemiBold.otf", "/usr/share/fonts/**/DejaVuSans.ttf") or _BOLD,
    "m": _first(f"{_FD}/*Medium.otf", "/usr/share/fonts/**/Inter-Medium.otf", "/usr/share/fonts/**/DejaVuSans.ttf") or _BOLD,
    "mono": _first("/usr/share/fonts/**/JetBrainsMono-Bold.ttf", "/usr/share/fonts/**/DejaVuSansMono-Bold.ttf") or _BOLD,
}
if not FONTS["xb"]:
    raise SystemExit("No usable font found. Install fonts-inter or fonts-dejavu, or set AE_FONT_DIR.")
_FC = {}


def font(kind, px):
    """Font objects are expensive (each FreeType face keeps its own glyph cache).
    Animated text produces endless distinct sizes, which caused the out-of-memory
    crashes in the original project. Sizes are quantised to ~4 % steps (invisible
    mid-animation) and the cache is kept small."""
    px = max(1, int(px))
    if px > 24:
        step = max(1, int(px * 0.04)); px = int(round(px / step) * step)
    k = (kind, px)
    if k not in _FC:
        if len(_FC) >= 48:
            _FC.pop(next(iter(_FC)))          # drop the oldest entry
        _FC[k] = ImageFont.truetype(FONTS[kind], px)
    return _FC[k]


def clamp01(x):
    return max(0.0, min(1.0, x))


def ease(u):
    u = clamp01(u); return 0.5 - 0.5 * math.cos(math.pi * u)


def ease_out(u):
    u = clamp01(u); return 1 - (1 - u) ** 3


def spring(tau, f=2.6, z=0.45):
    if tau <= 0: return 0.0
    w = 2 * math.pi * f; wd = w * math.sqrt(1 - z * z)
    return 1 - math.exp(-z * w * tau) * (math.cos(wd * tau) + z / math.sqrt(1 - z * z) * math.sin(wd * tau))


def ramp(t, t0, d=0.4):
    return ease((t - t0) / d)


def lerp(a, b, u):
    return a + (b - a) * u


def mix(c1, c2, u):
    return tuple(int(lerp(a, b, u)) for a, b in zip(c1, c2))


class Canvas:
    SS = 2

    def __init__(self, out_scale=1.0, size=(1920, 1080)):
        self.f0 = out_scale * self.SS
        self.W, self.H = size
        self.sz = (int(size[0] * self.f0), int(size[1] * self.f0))
        self.rgb = Image.new("RGB", self.sz, (0, 0, 0))
        self.al = Image.new("L", self.sz, 0)
        self.d = _Dual(self)
        self.stack = [(0.0, 0.0, 1.0, 1.0)]  # ox, oy, scale, alpha
        self.out_scale = out_scale

    # transforms ---------------------------------------------------------
    @property
    def tr(self):
        return self.stack[-1]

    def push(self, cx=0, cy=0, s=1.0, alpha=1.0, dx=0, dy=0):
        """scale by s about design point (cx, cy), then translate by (dx, dy)"""
        ox, oy, sc, al = self.tr
        # new mapping: P -> ox + sc*((cx + (x-cx)*s + dx))
        nox = ox + sc * (cx - cx * s + dx)
        noy = oy + sc * (cy - cy * s + dy)
        self.stack.append((nox, noy, sc * s, al * alpha))

    def pop(self):
        self.stack.pop()

    def P(self, x, y):
        ox, oy, sc, _ = self.tr
        return ((ox + sc * x) * self.f0, (oy + sc * y) * self.f0)

    def L(self, v):
        return v * self.tr[2] * self.f0

    def C(self, col, a=1.0):
        if col is None: return None
        al = (col[3] / 255 if len(col) == 4 else 1.0) * a * self.tr[3]
        return (col[0], col[1], col[2], int(255 * clamp01(al)))

    # primitives ---------------------------------------------------------
    def rrect(self, x0, y0, x1, y1, r=18, fill=CARD, outline=INK, w=5, shadow=0.0, a=1.0):
        if self.tr[2] <= 0.01 or self.tr[3] <= 0.004: return
        if shadow:
            p0 = self.P(x0 + 6, y0 + 10); p1 = self.P(x1 + 6, y1 + 10)
            self.d.rounded_rectangle([p0, p1], self.L(r), fill=self.C((10, 6, 30), 0.28 * shadow * a))
        p0 = self.P(x0, y0); p1 = self.P(x1, y1)
        if p1[0] - p0[0] < 2 or p1[1] - p0[1] < 2: return
        self.d.rounded_rectangle([p0, p1], min(self.L(r), (p1[0] - p0[0]) / 2, (p1[1] - p0[1]) / 2),
                                 fill=self.C(fill, a), outline=self.C(outline, a) if outline else None,
                                 width=max(1, int(self.L(w))) if outline else 0)

    def circle(self, cx, cy, r, fill=CARD, outline=INK, w=5, a=1.0):
        if self.tr[2] <= 0.01: return
        p0 = self.P(cx - r, cy - r); p1 = self.P(cx + r, cy + r)
        self.d.ellipse([p0, p1], fill=self.C(fill, a), outline=self.C(outline, a) if outline else None,
                       width=max(1, int(self.L(w))) if outline else 0)

    def ellipse(self, cx, cy, rx, ry, fill, outline=None, w=4, a=1.0):
        p0 = self.P(cx - rx, cy - ry); p1 = self.P(cx + rx, cy + ry)
        self.d.ellipse([p0, p1], fill=self.C(fill, a), outline=self.C(outline, a) if outline else None,
                       width=max(1, int(self.L(w))) if outline else 0)

    def line(self, pts, w=5, fill=INK, a=1.0, round_caps=True):
        pp = [self.P(x, y) for x, y in pts]
        lw = max(1, int(self.L(w)))
        self.d.line(pp, fill=self.C(fill, a), width=lw, joint="curve")
        if round_caps:
            for p in (pp[0], pp[-1]):
                r = lw / 2
                self.d.ellipse([p[0] - r, p[1] - r, p[0] + r, p[1] + r], fill=self.C(fill, a))

    def poly(self, pts, fill, outline=INK, w=4, a=1.0):
        pp = [self.P(x, y) for x, y in pts]
        self.d.polygon(pp, fill=self.C(fill, a))
        if outline:
            self.d.line(pp + [pp[0]], fill=self.C(outline, a), width=max(1, int(self.L(w))), joint="curve")

    def text(self, x, y, s, size=32, kind="b", fill=INK, anchor="lm", a=1.0, stroke=0, stroke_fill=None):
        if self.tr[2] * size < 2 or self.tr[3] * a <= 0.01: return
        f = font(kind, self.L(size))
        self.d.text(self.P(x, y), s, font=f, fill=self.C(fill, a), anchor=anchor,
                    stroke_width=int(self.L(stroke)), stroke_fill=self.C(stroke_fill or INK, a))

    def tlen(self, s, size=32, kind="b"):
        return font(kind, 100).getlength(s) * size / 100

    def paste_unused(self):
        pass

    def paste(self, rgba, x, y, w, a=1.0):
        """paste a numpy RGBA (float 0..1) image with top-left at design (x, y), width w"""
        if self.tr[2] <= 0.01 or a * self.tr[3] <= 0.01: return
        p0 = self.P(x, y)
        tw = max(1, int(self.L(w))); th = max(1, int(tw * rgba.shape[0] / rgba.shape[1]))
        im = Image.fromarray((np.clip(rgba, 0, 1) * 255).astype(np.uint8), "RGBA").resize((tw, th), Image.LANCZOS)
        if a * self.tr[3] < 0.999:
            arr = np.asarray(im).copy(); arr[..., 3] = (arr[..., 3] * a * self.tr[3]).astype(np.uint8)
            im = Image.fromarray(arr, "RGBA")
        pos = (int(p0[0]), int(p0[1]))
        self.rgb.paste(im.convert("RGB"), pos, im.split()[3])
        tmp = Image.new("L", self.sz, 0); tmp.paste(im.split()[3], pos)
        self.al = ImageChops.lighter(self.al, tmp)

    def result(self):
        """float RGBA at output resolution (premultiplied rgb, alpha)"""
        sz = (int(self.W * self.out_scale), int(self.H * self.out_scale))
        rgb = np.asarray(self.rgb.resize(sz, Image.BOX)).astype(np.float32) / 255
        al = np.asarray(self.al.resize(sz, Image.BOX)).astype(np.float32)[..., None] / 255
        return np.concatenate([rgb, al], 2)   # premultiplied colour + coverage


def over(frame, layer):
    """frame float RGB (H,W,3); layer = premultiplied colour + coverage"""
    al = layer[..., 3:4]
    return frame * (1 - al) + layer[..., :3]


class _Dual:
    """ImageDraw facade: colour is alpha-blended onto the RGB plane, coverage is
    unioned (max) into the alpha plane within the primitive's bounding box, so a
    semi-transparent shape never punches a hole in what is beneath it."""
    def __init__(self, cv):
        # weak reference: a strong one formed a Canvas <-> _Dual reference cycle, so each
        # frame's ~33 MB of image buffers waited for the cyclic GC -> unbounded memory growth
        # (root cause of the out-of-memory crashes in the original project's V1/V2 renders)
        import weakref
        self.cv = weakref.proxy(cv)

    def _do(self, name, bbox, args, kw):
        cv = self.cv
        dc = ImageDraw.Draw(cv.rgb, "RGBA")
        getattr(dc, name)(*args, **kw)
        x0, y0, x1, y1 = [int(v) for v in bbox]
        pad = int(kw.get("width", 0) or 0) + int(kw.get("stroke_width", 0) or 0) + 4
        x0 = max(0, x0 - pad); y0 = max(0, y0 - pad); x1 = min(cv.sz[0], x1 + pad); y1 = min(cv.sz[1], y1 + pad)
        if x1 <= x0 or y1 <= y0: return
        m = Image.new("L", (x1 - x0, y1 - y0), 0)
        dm = ImageDraw.Draw(m)
        kw2 = dict(kw)
        for k in ("fill", "outline", "stroke_fill"):
            if kw2.get(k) is not None:
                col = kw2[k]; kw2[k] = col[3] if isinstance(col, tuple) and len(col) == 4 else 255
        args2 = [_shift(a, x0, y0) for a in args]
        getattr(dm, name)(*args2, **kw2)
        reg = cv.al.crop((x0, y0, x1, y1))
        cv.al.paste(ImageChops.lighter(reg, m), (x0, y0))

    def rounded_rectangle(self, xy, r, **kw):
        (a, b) = xy; self._do("rounded_rectangle", (a[0], a[1], b[0], b[1]), [xy, r], kw)

    def ellipse(self, xy, **kw):
        if isinstance(xy[0], tuple): bb = (xy[0][0], xy[0][1], xy[1][0], xy[1][1])
        else: bb = xy
        self._do("ellipse", bb, [xy], kw)

    def line(self, pts, **kw):
        xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
        self._do("line", (min(xs), min(ys), max(xs), max(ys)), [pts], kw)

    def polygon(self, pts, **kw):
        xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
        self._do("polygon", (min(xs), min(ys), max(xs), max(ys)), [pts], kw)

    def text(self, xy, s, **kw):
        dc = ImageDraw.Draw(self.cv.rgb, "RGBA")
        bb = dc.textbbox(xy, s, font=kw["font"], anchor=kw.get("anchor"), stroke_width=kw.get("stroke_width", 0))
        self._do("text", bb, [xy, s], kw)


def _shift(a, ox, oy):
    if isinstance(a, tuple) and len(a) == 2 and all(isinstance(v, (int, float)) for v in a):
        return (a[0] - ox, a[1] - oy)
    if isinstance(a, (list, tuple)) and a and isinstance(a[0], (tuple, list)):
        return [(p[0] - ox, p[1] - oy) for p in a]
    if isinstance(a, (list, tuple)) and len(a) == 4 and all(isinstance(v, (int, float)) for v in a):
        return [a[0] - ox, a[1] - oy, a[2] - ox, a[3] - oy]
    return a


# =====================================================================
# illustrated elements
# =====================================================================
def bot(c, x, y, s=1.0, t=0.0, look=(0, 0), blink=0.0, mood="happy", hands=None, a=1.0, glow=1.0):
    """The AI agent mascot: a chip-headed helper (evolves from the AI chip card
    of the proof of concept). (x, y) = centre of the head."""
    c.push(x, y, s, a)
    bob = 0
    # hover glow
    if glow > 0:
        for k in range(4):
            c.ellipse(x, y + 128, 70 - k * 12, 14 - k * 2.5, (150, 120, 255), a=0.10 * glow)
    # body pod
    c.rrect(x - 44, y + 54, x + 44, y + 108, 22, PURPLE, w=6)
    c.circle(x, y + 80, 10, ORANGE, w=4)
    # antenna
    c.line([(x, y - 66), (x, y - 92)], w=6)
    c.circle(x, y - 98, 11, ORANGE, w=5)
    # pins
    for k in range(3):
        oy = -26 + 26 * k
        c.line([(x - 78, y + oy), (x - 66, y + oy)], w=6)
        c.line([(x + 66, y + oy), (x + 78, y + oy)], w=6)
    # head
    c.rrect(x - 68, y - 68, x + 68, y + 62, 30, PURPLE, w=7)
    c.rrect(x - 52, y - 50, x + 52, y + 44, 20, LAV, w=5)
    # eyes (same construction as the character: white sclera, big black iris, highlight)
    lx, ly = look
    for ex in (-22, 22):
        cx_, cy_ = x + ex, y - 6
        c.ellipse(cx_, cy_, 15, 19, (255, 255, 255), INK, 4)
        if blink < 0.8:
            c.ellipse(cx_ + lx * 5, cy_ + ly * 5, 10, 13 * (1 - blink), INK)
            c.ellipse(cx_ + lx * 5 + 3, cy_ + ly * 5 - 5, 3.2, 4.2 * (1 - blink), (255, 255, 255))
        if blink > 0.05:
            # lid
            c.ellipse(cx_, cy_ - 19 + 19 * blink, 16, 19 * blink + 0.5, LAV)
            c.line([(cx_ - 14, cy_ - 19 + 34 * blink), (cx_ + 14, cy_ - 19 + 34 * blink)], w=4)
    # mouth
    if mood == "happy":
        pts = [(x - 14 + 2 * i, y + 22 + 6 * math.sin(math.pi * i / 14)) for i in range(15)]
        c.line(pts, w=5)
    elif mood == "o":
        c.ellipse(x, y + 26, 7, 8, INK)
    elif mood == "think":
        c.line([(x - 10, y + 26), (x + 10, y + 22)], w=5)
    # hands
    if hands:
        for hx, hy in hands:
            c.circle(x + hx, y + hy, 16, PURPLE_L, w=5)
    c.pop()


def face_badge(c, art, x, y, r=56, a=1.0, ring=ORANGE):
    """circular portrait of the real character art"""
    c.circle(x, y, r + 7, ring, w=6, a=a)
    c.paste(art, x - r, y - r, 2 * r, a=a)


def check_badge(c, x, y, r=22, a=1.0, col=GREEN):
    c.circle(x, y, r, col, w=5, a=a)
    c.line([(x - r * 0.45, y + r * 0.02), (x - r * 0.1, y + r * 0.38), (x + r * 0.5, y - r * 0.35)], w=r * 0.24,
           fill=(255, 255, 255), a=a)


def tick_box(c, x, y, done, a=1.0, size=26):
    c.rrect(x, y - size / 2, x + size, y + size / 2, 7, (255, 255, 255), w=4, a=a)
    if done > 0:
        u = clamp01(done)
        p0 = (x + size * 0.2, y + size * 0.02); p1 = (x + size * 0.42, y + size * 0.28); p2 = (x + size * 0.85, y - size * 0.32)
        if u < 0.4:
            q = (lerp(p0[0], p1[0], u / 0.4), lerp(p0[1], p1[1], u / 0.4)); c.line([p0, q], w=5, fill=GREEN, a=a)
        else:
            v = (u - 0.4) / 0.6
            q = (lerp(p1[0], p2[0], v), lerp(p1[1], p2[1], v)); c.line([p0, p1, q], w=5, fill=GREEN, a=a)


def window(c, x0, y0, x1, y1, title="", a=1.0, bar=PURPLE, url=None, shadow=1.0):
    c.rrect(x0, y0, x1, y1, 20, CARD, w=6, shadow=shadow, a=a)
    c.rrect(x0, y0, x1, y0 + 50, 20, bar, w=6, a=a)
    c.rrect(x0 + 3, y0 + 30, x1 - 3, y0 + 50, 0, bar, outline=None, a=a)
    c.line([(x0 + 3, y0 + 50), (x1 - 3, y0 + 50)], w=6, a=a)
    for k, col in enumerate([(255, 110, 100), (255, 200, 70), (110, 210, 120)]):
        c.circle(x0 + 26 + 22 * k, y0 + 25, 7, col, w=3, a=a)
    if url is not None:
        c.rrect(x0 + 100, y0 + 10, x1 - 20, y0 + 40, 15, (255, 255, 255), w=3, a=a)
        c.text(x0 + 118, y0 + 25, url, 18, "sb", INK, a=a)
    elif title:
        c.text(x0 + 100, y0 + 25, title, 20, "b", (255, 255, 255), a=a)


def doc_icon(c, x, y, w=60, col=(255, 255, 255), a=1.0, lines=3, accent=BLUE):
    h = w * 1.25; f = w * 0.3
    c.poly([(x, y), (x + w - f, y), (x + w, y + f), (x + w, y + h), (x, y + h)], col, w=5, a=a)
    c.poly([(x + w - f, y), (x + w - f, y + f), (x + w, y + f)], (225, 220, 240), w=4, a=a)
    for k in range(lines):
        c.line([(x + w * 0.18, y + h * (0.42 + 0.17 * k)), (x + w * (0.82 - 0.2 * (k == lines - 1)), y + h * (0.42 + 0.17 * k))],
               w=w * 0.07, fill=accent, a=a)


def folder_icon(c, x, y, w=70, col=(255, 196, 70), a=1.0):
    h = w * 0.72
    c.poly([(x, y + h * 0.12), (x + w * 0.38, y + h * 0.12), (x + w * 0.46, y + h * 0.26), (x + w, y + h * 0.26),
            (x + w, y + h), (x, y + h)], col, w=5, a=a)
    c.line([(x + 2, y + h * 0.36), (x + w - 2, y + h * 0.36)], w=4, a=a)


def book_icon(c, x, y, w=46, h=150, col=PURPLE, label="", a=1.0, open_u=0.0):
    c.rrect(x, y, x + w, y + h, 8, col, w=5, a=a)
    c.line([(x + 8, y + 16), (x + w - 8, y + 16)], w=4, fill=(255, 255, 255), a=a * 0.8)
    c.line([(x + 8, y + h - 16), (x + w - 8, y + h - 16)], w=4, fill=(255, 255, 255), a=a * 0.8)
    if label:
        # vertical label (rotated text is costly: draw letters stacked)
        n = len(label); step = min(17, (h - 46) / max(1, n))
        for i, ch in enumerate(label[:12]):
            c.text(x + w / 2, y + 30 + i * step, ch, 15, "xb", (255, 255, 255), anchor="mm", a=a)


def magnifier(c, x, y, r=34, a=1.0):
    c.line([(x + r * 0.7, y + r * 0.7), (x + r * 1.6, y + r * 1.6)], w=12, a=a)
    c.circle(x, y, r, (220, 240, 255, 160), w=7, a=a)


def wrench_icon(c, x, y, s=1.0, a=1.0):
    c.push(x, y, s)
    c.line([(x - 22, y + 22), (x + 10, y - 10)], w=14, a=a)
    c.line([(x - 22, y + 22), (x + 10, y - 10)], w=7, fill=(200, 205, 220), a=a)
    c.circle(x + 16, y - 16, 16, (200, 205, 220), w=5, a=a)
    c.circle(x + 22, y - 22, 7, LAV, outline=None, a=a)
    c.pop()


def globe_icon(c, x, y, r=26, a=1.0):
    c.circle(x, y, r, (110, 175, 255), w=5, a=a)
    c.ellipse(x, y, r * 0.45, r, None, INK, 4, a=a)
    c.line([(x - r, y), (x + r, y)], w=4, a=a)


def pill(c, x, y, s, size=24, fill=INK, tc=(255, 255, 255), a=1.0, kind="xb", anchor="mm"):
    w = c.tlen(s, size, kind) + size * 1.2; h = size * 1.7
    if anchor == "lm": x = x + w / 2
    c.rrect(x - w / 2, y - h / 2, x + w / 2, y + h / 2, h / 2, fill, w=4, a=a)
    c.text(x, y + 1, s, size, kind, tc, anchor="mm", a=a)
    return w


def arrow(c, p0, p1, u=1.0, w=7, col=INK, a=1.0, head=16):
    if u <= 0: return
    q = (lerp(p0[0], p1[0], u), lerp(p0[1], p1[1], u))
    c.line([p0, q], w=w, fill=col, a=a)
    if u > 0.85:
        ang = math.atan2(p1[1] - p0[1], p1[0] - p0[0])
        h = head
        pts = [q, (q[0] - h * math.cos(ang - 0.5), q[1] - h * math.sin(ang - 0.5)),
               (q[0] - h * math.cos(ang + 0.5), q[1] - h * math.sin(ang + 0.5))]
        c.poly(pts, col, outline=col, w=3, a=a)


def cursor(c, x, y, click=0.0, a=1.0):
    if click > 0:
        c.circle(x, y, 10 + 26 * click, (255, 255, 255, 0), outline=ORANGE, w=5, a=a * (1 - click))
    c.poly([(x, y), (x, y + 34), (x + 9, y + 26), (x + 15, y + 40), (x + 21, y + 37), (x + 15, y + 23), (x + 26, y + 23)],
           (255, 255, 255), w=4, a=a)


def bubble(c, x0, y0, x1, y1, fill=CARD, tail="left", a=1.0, w=5):
    c.rrect(x0, y0, x1, y1, 24, fill, w=w, shadow=0.6, a=a)
    if tail == "left":
        c.poly([(x0 + 30, y1 - 3), (x0 + 22, y1 + 22), (x0 + 58, y1 - 3)], fill, outline=None, a=a)
        c.line([(x0 + 30, y1), (x0 + 22, y1 + 22), (x0 + 58, y1)], w=w, a=a)
    elif tail == "right":
        c.poly([(x1 - 30, y1 - 3), (x1 - 22, y1 + 22), (x1 - 58, y1 - 3)], fill, outline=None, a=a)
        c.line([(x1 - 30, y1), (x1 - 22, y1 + 22), (x1 - 58, y1)], w=w, a=a)


def slide_thumb(c, x, y, w, kind, a=1.0, title="", accent=PURPLE):
    h = w * 9 / 16
    c.rrect(x, y, x + w, y + h, 10, (255, 255, 255), w=5, shadow=0.7, a=a)
    if kind == "title":
        c.rrect(x, y, x + w, y + h, 10, accent, w=5, a=a)
        c.text(x + w * 0.08, y + h * 0.42, title or "Sleep & Memory", w * 0.085, "xb", (255, 255, 255), a=a)
        c.line([(x + w * 0.08, y + h * 0.62), (x + w * 0.45, y + h * 0.62)], w=w * 0.025, fill=ORANGE, a=a)
        c.text(x + w * 0.08, y + h * 0.76, "Seminar · Week 6", w * 0.05, "sb", (230, 225, 255), a=a)
    elif kind == "bullets":
        c.text(x + w * 0.07, y + h * 0.18, title or "Key findings", w * 0.07, "xb", INK, a=a)
        for k in range(3):
            yy = y + h * (0.42 + 0.17 * k)
            c.circle(x + w * 0.09, yy, w * 0.018, ORANGE, outline=None, a=a)
            c.line([(x + w * 0.14, yy), (x + w * (0.8 - 0.12 * k), yy)], w=w * 0.03, fill=(190, 185, 210), a=a)
    elif kind == "chart":
        c.text(x + w * 0.07, y + h * 0.18, title or "Results", w * 0.07, "xb", INK, a=a)
        for k, hh in enumerate([0.3, 0.5, 0.42, 0.62]):
            bx = x + w * (0.12 + 0.19 * k)
            c.rrect(bx, y + h * (0.88 - hh), bx + w * 0.12, y + h * 0.88, 4, [PURPLE_L, ORANGE, PURPLE_L, GREEN][k],
                    w=3, a=a)
