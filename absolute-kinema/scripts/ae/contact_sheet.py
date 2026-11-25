"""Build the preview contact sheet.

v0.1 laid stills into a fixed-size grid (e.g. 3 columns) and left any cells past the
last still as plain black - at a glance, indistinguishable from a black/frozen video
frame. This cost a fresh user real time working out whether the video itself had a
problem. v0.2 fills unused cells with a distinct, clearly-not-video slate colour, a
diagonal hatch, and an "(unused)" label, and draws a thin border around every cell
(used or not) so the grid itself is unambiguous.
"""
from PIL import Image, ImageDraw, ImageFont

CELL_W, CELL_H = 640, 360
UNUSED_FILL = (52, 58, 74)       # a slate-blue, far from any theme's background colours
BORDER = (110, 116, 132)
HATCH = (70, 77, 96)


def _font(size=22):
    try:
        return ImageFont.truetype("DejaVuSans-Bold.ttf", size)
    except Exception:
        return ImageFont.load_default()


def _unused_cell():
    im = Image.new("RGB", (CELL_W, CELL_H), UNUSED_FILL)
    d = ImageDraw.Draw(im)
    step = 28
    for x in range(-CELL_H, CELL_W, step):
        d.line([(x, CELL_H), (x + CELL_H, 0)], fill=HATCH, width=2)
    text = "(unused - no still here)"
    f = _font(22)
    bbox = d.textbbox((0, 0), text, font=f)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    d.rectangle([CELL_W / 2 - tw / 2 - 14, CELL_H / 2 - th / 2 - 10,
                 CELL_W / 2 + tw / 2 + 14, CELL_H / 2 + th / 2 + 10], fill=(30, 33, 42))
    d.text((CELL_W / 2 - tw / 2, CELL_H / 2 - th / 2 - bbox[1]), text, fill=(200, 204, 214), font=f)
    return im


def build_contact_sheet(ims, cols=None):
    """ims: list of PIL Images (stills). Returns a PIL Image: a grid with every real
    still placed, and any remaining cells clearly marked as unused rather than left
    black. Raises ValueError for an empty list (nothing to lay out)."""
    if not ims:
        raise ValueError("build_contact_sheet needs at least one image")
    cols = cols or min(3, len(ims))
    rows = (len(ims) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * CELL_W, rows * CELL_H), UNUSED_FILL)
    unused = _unused_cell()
    for k in range(cols * rows):
        x, y = (k % cols) * CELL_W, (k // cols) * CELL_H
        if k < len(ims):
            sheet.paste(ims[k].resize((CELL_W, CELL_H)), (x, y))
        else:
            sheet.paste(unused, (x, y))
    d = ImageDraw.Draw(sheet)
    for k in range(cols * rows):
        x, y = (k % cols) * CELL_W, (k // cols) * CELL_H
        d.rectangle([x, y, x + CELL_W - 1, y + CELL_H - 1], outline=BORDER, width=2)
    return sheet
