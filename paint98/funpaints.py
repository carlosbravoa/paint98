"""Fun Colors: multi-colour paints (colour cycles and patterns) for kids.

A "paint" anywhere in the app is either a plain (r, g, b) tuple or a
FunPaint. Tools call set_paint() instead of set_rgb() so both just work.
"""

import math
import random

import cairo


def _lerp(a, b, t):
    return tuple(round(a[i] + (b[i] - a[i]) * t) for i in range(3))


class FunPaint:
    """Base class. `color` is the representative solid colour, used where a
    single colour is needed (right-click, colour eraser, indicators)."""

    def __init__(self, name, color):
        self.name = name
        self.color = color

    def pattern(self, bbox=None, progress=None):
        raise NotImplementedError

    def draw_swatch(self, cr, x, y, w, h):
        cr.save()
        cr.rectangle(x, y, w, h)
        cr.clip()
        cr.translate(x, y)
        cr.set_source(self.pattern((0, 0, w - 1, h - 1)))
        cr.paint()
        cr.restore()


class CyclePaint(FunPaint):
    """Colours that cycle along a stroke (and spread across a shape)."""

    PERIOD = 240.0  # pixels of stroke per full cycle

    def __init__(self, name, stops):
        super().__init__(name, stops[0])
        self.stops = list(stops)

    def color_at(self, progress):
        stops = self.stops + [self.stops[0]]
        t = (progress / self.PERIOD) % 1.0 * (len(stops) - 1)
        i = int(t)
        return _lerp(stops[i], stops[i + 1], t - i)

    def pattern(self, bbox=None, progress=None):
        if progress is not None:
            r, g, b = self.color_at(progress)
            return cairo.SolidPattern(r / 255, g / 255, b / 255)
        x0, y0, x1, y1 = bbox or (0, 0, 255, 255)
        pat = cairo.LinearGradient(x0, y0, x1 + 1, y1 + 1)
        stops = self.stops + [self.stops[0]]
        for i, c in enumerate(stops):
            pat.add_color_stop_rgb(i / (len(stops) - 1), c[0] / 255, c[1] / 255, c[2] / 255)
        return pat

    def draw_swatch(self, cr, x, y, w, h):
        # Vertical bands read better than a tiny gradient at swatch size.
        for i in range(w):
            c = self.color_at(i * self.PERIOD / max(1, w) * 0.999)
            cr.set_source_rgb(c[0] / 255, c[1] / 255, c[2] / 255)
            cr.rectangle(x + i, y, 1, h)
            cr.fill()


class TilePaint(FunPaint):
    """A repeating picture pinned to the canvas, so strokes line up."""

    def __init__(self, name, color, painter, size):
        super().__init__(name, color)
        self.size = size
        self.painter = painter
        self._tile = None

    def tile(self):
        if self._tile is None:
            self._tile = cairo.ImageSurface(cairo.FORMAT_ARGB32, self.size, self.size)
            self.painter(cairo.Context(self._tile), self.size)
        return self._tile

    def pattern(self, bbox=None, progress=None):
        pat = cairo.SurfacePattern(self.tile())
        pat.set_extend(cairo.EXTEND_REPEAT)
        pat.set_filter(cairo.FILTER_NEAREST)
        return pat


# ---------------------------------------------------------------------------
# Tile painters
# ---------------------------------------------------------------------------

def _rgb(cr, c):
    cr.set_source_rgb(c[0] / 255, c[1] / 255, c[2] / 255)


def _candy(cr, n):
    _rgb(cr, (255, 255, 255))
    cr.paint()
    _rgb(cr, (255, 60, 150))
    cr.set_antialias(cairo.ANTIALIAS_NONE)
    for k in range(-n, 2 * n, 8):
        cr.move_to(k, 0)
        cr.line_to(k + 4, 0)
        cr.line_to(k + 4 - n, n)
        cr.line_to(k - n, n)
        cr.close_path()
    cr.fill()


def _polka(cr, n):
    _rgb(cr, (255, 230, 60))
    cr.paint()
    _rgb(cr, (230, 30, 60))
    for cx, cy in ((n / 4, n / 4), (3 * n / 4, 3 * n / 4)):
        cr.arc(cx, cy, n / 6, 0, 2 * math.pi)
        cr.fill()


def _star_path(cr, cx, cy, r_out, r_in):
    for i in range(10):
        r = r_out if i % 2 == 0 else r_in
        a = -math.pi / 2 + i * math.pi / 5
        fn = cr.move_to if i == 0 else cr.line_to
        fn(cx + r * math.cos(a), cy + r * math.sin(a))
    cr.close_path()


def _stars(cr, n):
    _rgb(cr, (20, 20, 110))
    cr.paint()
    _rgb(cr, (255, 220, 0))
    _star_path(cr, n * 0.3, n * 0.32, n * 0.26, n * 0.11)
    cr.fill()
    _rgb(cr, (255, 255, 255))
    _star_path(cr, n * 0.78, n * 0.78, n * 0.14, n * 0.06)
    cr.fill()


def _heart_path(cr, cx, cy, s):
    cr.move_to(cx, cy + s * 0.9)
    cr.curve_to(cx - s * 1.4, cy - s * 0.1, cx - s * 0.6, cy - s * 1.1, cx, cy - s * 0.35)
    cr.curve_to(cx + s * 0.6, cy - s * 1.1, cx + s * 1.4, cy - s * 0.1, cx, cy + s * 0.9)
    cr.close_path()


def _hearts(cr, n):
    _rgb(cr, (255, 200, 225))
    cr.paint()
    _rgb(cr, (230, 20, 80))
    _heart_path(cr, n * 0.3, n * 0.3, n * 0.2)
    cr.fill()
    _rgb(cr, (255, 90, 160))
    _heart_path(cr, n * 0.75, n * 0.75, n * 0.15)
    cr.fill()


def _speckles(colors, seed):
    def painter(cr, n):
        rnd = random.Random(seed)
        cr.set_antialias(cairo.ANTIALIAS_NONE)
        for y in range(0, n, 2):
            for x in range(0, n, 2):
                _rgb(cr, rnd.choice(colors))
                cr.rectangle(x, y, 2, 2)
                cr.fill()
    return painter


def _checker(cr, n):
    _rgb(cr, (255, 255, 255))
    cr.paint()
    _rgb(cr, (0, 0, 0))
    h = n // 2
    cr.rectangle(0, 0, h, h)
    cr.rectangle(h, h, h, h)
    cr.fill()


RAINBOW = [(255, 0, 0), (255, 140, 0), (255, 230, 0), (0, 200, 0),
           (0, 120, 255), (75, 0, 200), (170, 0, 220)]

FUN_PAINTS = [
    CyclePaint("Rainbow", RAINBOW),
    CyclePaint("Pastel Rainbow", [(255, 170, 170), (255, 210, 150), (255, 250, 160), (170, 240, 170),
                                  (160, 210, 255), (200, 170, 255)]),
    CyclePaint("Fire", [(200, 0, 0), (255, 90, 0), (255, 200, 0), (255, 90, 0)]),
    CyclePaint("Ocean", [(0, 40, 160), (0, 120, 255), (0, 220, 255), (0, 160, 190)]),
    CyclePaint("Forest", [(0, 100, 0), (60, 180, 50), (160, 220, 50), (30, 140, 70)]),
    CyclePaint("Neon", [(255, 0, 255), (0, 255, 255), (0, 255, 0), (255, 255, 0)]),
    CyclePaint("Sunset", [(255, 90, 100), (255, 160, 0), (200, 60, 160), (110, 40, 170)]),
    TilePaint("Candy Stripes", (255, 60, 150), _candy, 16),
    TilePaint("Polka Dots", (255, 230, 60), _polka, 14),
    TilePaint("Stars", (255, 220, 0), _stars, 20),
    TilePaint("Hearts", (230, 20, 80), _hearts, 20),
    TilePaint("Confetti", (255, 0, 255), _speckles(
        [(255, 0, 0), (255, 160, 0), (255, 240, 0), (0, 210, 0), (0, 150, 255),
         (170, 0, 255), (255, 0, 160), (255, 255, 255)], 7), 32),
    TilePaint("Checkerboard", (0, 0, 0), _checker, 8),
    TilePaint("Gold Glitter", (230, 180, 30), _speckles(
        [(255, 215, 0), (255, 240, 120), (220, 160, 20), (255, 255, 220), (190, 130, 10)], 3), 32),
]

CRAYONS = [(237, 28, 36), (255, 127, 39), (255, 242, 0), (181, 230, 29), (34, 177, 76),
           (0, 162, 154), (0, 183, 239), (63, 72, 204), (143, 63, 191), (255, 0, 200),
           (255, 174, 201), (156, 90, 60), (0, 0, 0), (255, 255, 255)]

FUN_PALETTE = FUN_PAINTS + CRAYONS


def is_fun(paint):
    return isinstance(paint, FunPaint)


def solid(paint):
    """Representative (r, g, b) of any paint."""
    return paint.color if is_fun(paint) else tuple(paint)


def set_paint(cr, paint, bbox=None, progress=None):
    """Use any paint as the cairo source.

    bbox spreads colour cycles across a shape; progress (stroke length so
    far) picks the current colour of a cycle while drawing a stroke."""
    if is_fun(paint):
        cr.set_source(paint.pattern(bbox, progress))
    else:
        r, g, b = paint
        cr.set_source_rgb(r / 255, g / 255, b / 255)
