"""Draw original, simple earthquake diagrams (RGBA PNG) for the AbsoluteKinema earthquake example."""
import math, sys
from PIL import Image, ImageDraw, ImageFont

OUT = sys.argv[1]
W, H = 1200, 720
PLATE_A = (196, 138, 84, 255)
PLATE_B = (150, 104, 70, 255)
EDGE = (60, 40, 30, 255)
FENCE = (245, 240, 225, 255)
ACCENT = (255, 112, 67, 255)
WHITE = (255, 255, 255, 255)
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"


def font(s):
    return ImageFont.truetype(FONT, s)


def arrow(d, p0, p1, col, w=14, head=34):
    d.line([p0, p1], fill=col, width=w)
    ang = math.atan2(p1[1] - p0[1], p1[0] - p0[0])
    l = (p1[0] - head * math.cos(ang - 0.5), p1[1] - head * math.sin(ang - 0.5))
    r = (p1[0] - head * math.cos(ang + 0.5), p1[1] - head * math.sin(ang + 0.5))
    d.polygon([p1, l, r], fill=col)


def fault_x(y):
    # a gently jagged fault line running top to bottom through the middle
    return W / 2 + 18 * math.sin(y / 55.0) + 8 * math.sin(y / 17.0)


def plates_base(offset=0):
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    top, bot = 60, H - 60
    left = [(60, top)] + [(fault_x(y), y) for y in range(top, bot + 1, 6)] + [(60, bot)]
    right = [(W - 60, top)] + [(fault_x(y), y) for y in range(top, bot + 1, 6)] + [(W - 60, bot)]
    d.polygon(left, fill=PLATE_A)
    d.polygon(right, fill=PLATE_B)
    d.line([(fault_x(y), y) for y in range(top, bot + 1, 6)], fill=EDGE, width=8)
    d.rectangle([60, top, W - 60, bot], outline=EDGE, width=8)
    return im, d, top, bot


def label(d, xy, text, size=40, col=WHITE):
    d.text(xy, text, font=font(size), fill=col, anchor="mm", stroke_width=4, stroke_fill=EDGE)


# 1. two plates drifting past each other (top-down view)
im, d, top, bot = plates_base()
arrow(d, (330, 250), (330, 110), WHITE)
arrow(d, (870, 470), (870, 610), WHITE)
label(d, (330, 420), "Plate A", 48)
label(d, (870, 300), "Plate B", 48)
label(d, (W / 2, 30), "plate boundary (fault)", 32, (255, 220, 190, 255))
im.save(f"{OUT}/plates_drift.png")

# 2. locked fault: fence lines bend as stress builds (elastic strain)
im, d, top, bot = plates_base()
for i, y0 in enumerate((200, 360, 520)):
    pts = []
    for x in range(80, W - 79, 8):
        dx = x - W / 2
        bend = 70 * math.tanh(dx / 260.0)          # drag near the fault, shear across it
        pts.append((x, y0 + bend))
    d.line(pts, fill=FENCE, width=10)
arrow(d, (200, 640), (200, 520), WHITE, w=12, head=28)
arrow(d, (1000, 80), (1000, 200), WHITE, w=12, head=28)
label(d, (W / 2 + 230, 110), "locked", 46, ACCENT)
label(d, (W / 2 - 230, 640), "stress builds", 40, (255, 220, 190, 255))
im.save(f"{OUT}/fault_locked.png")

# 3. rupture: fence lines snap straight again, but offset across the fault; energy burst
im, d, top, bot = plates_base()
for y0 in (200, 360, 520):
    d.line([(80, y0 - 70), (fault_x(y0 - 70) - 4, y0 - 70)], fill=FENCE, width=10)
    d.line([(fault_x(y0 + 70) + 4, y0 + 70), (W - 80, y0 + 70)], fill=FENCE, width=10)
cx, cy = fault_x(360), 360
for k in range(16):
    a = 2 * math.pi * k / 16
    r0, r1 = 34, 120 if k % 2 == 0 else 85
    d.line([(cx + r0 * math.cos(a), cy + r0 * math.sin(a)), (cx + r1 * math.cos(a), cy + r1 * math.sin(a))],
           fill=ACCENT, width=10)
d.ellipse([cx - 30, cy - 30, cx + 30, cy + 30], fill=(255, 210, 80, 255), outline=EDGE, width=5)
label(d, (W / 2, 30), "SNAP! energy released", 38, ACCENT)
im.save(f"{OUT}/fault_snap.png")

# 4. seismic waves: cross-section, rings spreading from the focus to the surface
im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
d = ImageDraw.Draw(im)
ground = 230
d.rectangle([40, ground, W - 40, H - 40], fill=PLATE_B, outline=EDGE, width=8)
for i in range(4):  # rock layers
    y = ground + 110 + i * 95
    d.line([(48, y + 14 * math.sin(i)), (W - 48, y - 14 * math.sin(i))], fill=PLATE_A, width=6)
fx, fy = W / 2, 560
d.rectangle([40, ground, W - 40, H - 40], outline=EDGE, width=8)
layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
ld = ImageDraw.Draw(layer)
for r in (90, 170, 250, 330, 410):
    ld.ellipse([fx - r, fy - r, fx + r, fy + r], outline=(255, 160, 120, 230), width=9)
mask = Image.new("L", (W, H), 0)
ImageDraw.Draw(mask).rectangle([48, ground + 4, W - 48, H - 48], fill=255)
im.paste(layer, (0, 0), Image.composite(layer, Image.new("RGBA", (W, H)), mask).split()[3])
d = ImageDraw.Draw(im)
d.ellipse([fx - 26, fy - 26, fx + 26, fy + 26], fill=(255, 210, 80, 255), outline=EDGE, width=5)
label(d, (fx + 150, fy + 70), "focus", 38)
# houses on the surface, with shake marks
for hx in (300, 600, 900):
    d.rectangle([hx - 50, ground - 80, hx + 50, ground], fill=(235, 230, 215, 255), outline=EDGE, width=5)
    d.polygon([(hx - 64, ground - 78), (hx, ground - 135), (hx + 64, ground - 78)], fill=ACCENT, outline=EDGE)
    for s in (-1, 1):
        for j in range(3):
            x = hx + s * (75 + j * 16)
            d.arc([x - 10, ground - 110 + j * 4, x + 10, ground - 40 - j * 4], 270 if s > 0 else 90,
                  90 if s > 0 else 270, fill=WHITE, width=5)
d.line([(fx, ground - 10), (fx, ground + 10)], fill=WHITE, width=6)
label(d, (fx, ground - 175), "epicentre", 38, (255, 220, 190, 255))
im.save(f"{OUT}/seismic_waves.png")
print("ok")
