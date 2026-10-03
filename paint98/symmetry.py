"""Mirror and kaleidoscope drawing: every stroke is repeated around the
centre of the picture."""

import math

import cairo

# (id, menu label with mnemonic, short name)
MODES = [
    ("off", "_Off", "Off"),
    ("mirror", "_Mirror", "Mirror"),
    ("quad", "_Four-Way", "Four-Way"),
    ("radial6", "_Radial (6)", "Radial"),
    ("kaleido8", "_Kaleidoscope (8)", "Kaleidoscope"),
]

HINTS = {
    "off": "Draws normally, without symmetry.",
    "mirror": "Mirrors everything you draw from left to right.",
    "quad": "Mirrors everything you draw into all four corners.",
    "radial6": "Repeats everything you draw six times around the centre.",
    "kaleido8": "Kaleidoscope: repeats and mirrors everything you draw eight times.",
}

# Tools whose strokes and shapes are repeated.
TOOLS = ("pencil", "brush", "airbrush", "eraser", "line", "curve",
         "rectangle", "polygon", "ellipse", "rounded_rect", "sticker")


def _rotation(cx, cy, degrees):
    a = math.radians(degrees)
    c, s = math.cos(a), math.sin(a)
    if abs(c) < 1e-9:
        c = 0.0
    if abs(s) < 1e-9:
        s = 0.0
    return cairo.Matrix(c, s, -s, c, cx - c * cx + s * cy, cy - s * cx - c * cy)


def transforms(mode, w, h):
    """Matrices (picture -> picture) for each copy, identity first."""
    ident = cairo.Matrix()
    flip_x = cairo.Matrix(-1, 0, 0, 1, w, 0)
    flip_y = cairo.Matrix(1, 0, 0, -1, 0, h)
    cx, cy = w / 2, h / 2
    if mode == "mirror":
        return [ident, flip_x]
    if mode == "quad":
        return [ident, flip_x, flip_y, flip_x.multiply(flip_y)]
    if mode == "radial6":
        return [_rotation(cx, cy, k * 60) for k in range(6)]
    if mode == "kaleido8":
        rots = [_rotation(cx, cy, k * 90) for k in range(4)]
        # A diagonal mirror combined with the four rotations gives 8 copies.
        diag = cairo.Matrix(0, 1, 1, 0, cx - cy, cy - cx)
        return rots + [diag.multiply(r) for r in rots]
    return [ident]


def map_points(pts, m):
    """Map pixel coordinates through a matrix (pixel centres)."""
    out = []
    for x, y in pts:
        X, Y = m.transform_point(x + 0.5, y + 0.5)
        out.append((int(round(X - 0.5)), int(round(Y - 0.5))))
    return out


def active(state, tool=None):
    return state.symmetry != "off" and (tool or state.tool) in TOOLS


def draw_guides(cr, mode, ox, oy, w, h, z):
    """Dotted guide lines through the centre, in widget coordinates."""
    cx, cy = ox + w * z / 2, oy + h * z / 2
    if mode in ("mirror", "quad"):
        angles = [90] if mode == "mirror" else [0, 90]
    elif mode == "radial6":
        angles = [90, 30, 150]
    else:
        angles = [0, 45, 90, 135]
    r = math.hypot(w * z, h * z)
    cr.save()
    cr.rectangle(ox, oy, w * z, h * z)
    cr.clip()
    cr.set_line_width(1)
    for a in angles:
        dx, dy = math.cos(math.radians(a)) * r, math.sin(math.radians(a)) * r
        for color, offset in (((1, 1, 1), 0), ((0, 0, 0.5), 4)):
            cr.set_source_rgba(*color, 0.8)
            cr.set_dash([4, 4], offset)
            cr.move_to(int(cx - dx) + 0.5, int(cy - dy) + 0.5)
            cr.line_to(int(cx + dx) + 0.5, int(cy + dy) + 0.5)
            cr.stroke()
    cr.restore()


def draw_icon(cr, mode, x, y, color=(0, 0, 0)):
    """16x16 glyph for a symmetry mode."""
    cr.save()
    cr.set_antialias(cairo.ANTIALIAS_NONE)
    cr.set_source_rgb(*color)

    def dot(px, py, s=3):
        cr.rectangle(x + px - s // 2, y + py - s // 2, s, s)

    def dashed(x0, y0, x1, y1):
        n = max(abs(x1 - x0), abs(y1 - y0))
        for i in range(0, n + 1, 2):
            t = i / max(1, n)
            cr.rectangle(x + round(x0 + (x1 - x0) * t), y + round(y0 + (y1 - y0) * t), 1, 1)

    if mode == "off":
        dot(8, 8, 4)
    elif mode == "mirror":
        dashed(8, 1, 8, 15)
        dot(4, 8)
        dot(12, 8)
    elif mode == "quad":
        dashed(8, 1, 8, 15)
        dashed(1, 8, 15, 8)
        for px, py in ((4, 4), (12, 4), (4, 12), (12, 12)):
            dot(px, py)
    else:
        n = 6 if mode == "radial6" else 8
        for k in range(n):
            a = math.radians(-90 + k * 360 / n)
            dot(8 + round(6 * math.cos(a)), 8 + round(6 * math.sin(a)), 2 if n == 8 else 3)
        if mode == "kaleido8":
            dot(8, 8, 2)
    cr.fill()
    cr.restore()
