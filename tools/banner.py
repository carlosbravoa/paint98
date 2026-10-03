#!/usr/bin/env python3
"""Draw the store banner (1218x406, 3:1): usage tools/banner.py OUT.png"""

import math
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import cairo  # noqa: E402

from paint98 import pixmaps  # noqa: E402
from paint98.funpaints import RAINBOW  # noqa: E402

W, H = 1218, 406
s = cairo.ImageSurface(cairo.FORMAT_RGB24, W, H)
cr = cairo.Context(s)
cr.set_source_rgb(0, 0.5, 0.5)
cr.paint()
# A chunky rainbow behind everything.
cr.set_line_width(22)
for i, c in enumerate(RAINBOW):
    cr.set_source_rgb(*(v / 255 for v in c))
    cr.arc(W - 120, H + 30, 270 - i * 22, math.pi, 2 * math.pi)
    cr.stroke()
# Pixel icon, scaled up without smoothing.
icon = pixmaps.make_surface(pixmaps.APP_ICON, scale=14)
cr.set_source_surface(icon, 70, (H - icon.get_height()) // 2)
cr.get_source().set_filter(cairo.FILTER_NEAREST)
cr.paint()
# Title with a classic 3D drop shadow.
cr.select_font_face("Liberation Sans", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
cr.set_font_size(120)
for dx, col in ((6, (0, 0, 0)), (0, (1, 1, 1))):
    cr.move_to(330 + dx, 215 + dx)
    cr.set_source_rgb(*col)
    cr.show_text("Paint98")
cr.set_font_size(32)
for dx, col in ((3, (0, 0, 0)), (0, (1, 1, 0.85))):
    cr.move_to(336 + dx, 282 + dx)
    cr.set_source_rgb(*col)
    cr.show_text("The classic paint program, with a little magic")
s.write_to_png(sys.argv[1])
