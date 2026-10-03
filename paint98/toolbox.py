"""The tool box: 16 tool buttons plus the tool options box below them."""

import random

import cairo

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gdk, GObject, Gtk, Pango, PangoCairo  # noqa: E402

from . import pixmaps, stickers, win98  # noqa: E402
from .state import (AIRBRUSH_SIZES, BRUSH_SHAPES, ERASER_SIZES,  # noqa: E402
                    MAGNIFY_LEVELS, TOOL_HELP, TOOL_NAMES, TOOLS)
from .imageops import disc_offsets, square_offsets  # noqa: E402
from .tools import brush_offsets  # noqa: E402

BTN = 25
X0, Y0 = 3, 2
WIDTH = 56
OPT_X = 6
ROWS = (len(TOOLS) + 1) // 2
OPT_Y = Y0 + ROWS * BTN + 4
OPT_W, OPT_H = 44, 100
NAVY = (0, 0, 0x80 / 255)


def _airbrush_dots(size, seed):
    rnd = random.Random(seed)
    r = size / 2
    pts = set()
    while len(pts) < size * 2:
        x, y = rnd.uniform(-r, r), rnd.uniform(-r, r)
        if x * x + y * y <= r * r:
            pts.add((int(x), int(y)))
    return sorted(pts)


AIR_DOTS = [_airbrush_dots(s, i) for i, s in enumerate(AIRBRUSH_SIZES)]


class ToolBox(Gtk.DrawingArea):
    __gsignals__ = {
        "hint": (GObject.SignalFlags.RUN_FIRST, None, (str,)),
        "open-sticker-book": (GObject.SignalFlags.RUN_FIRST, None, ()),
    }

    def __init__(self, state):
        super().__init__()
        self.state = state
        self.pressed = None
        self.set_size_request(WIDTH, OPT_Y + OPT_H + 4)
        self.add_events(Gdk.EventMask.BUTTON_PRESS_MASK | Gdk.EventMask.BUTTON_RELEASE_MASK
                        | Gdk.EventMask.POINTER_MOTION_MASK | Gdk.EventMask.LEAVE_NOTIFY_MASK)
        self.set_has_tooltip(True)
        self.connect("draw", self.on_draw)
        self.connect("button-press-event", self.on_press)
        self.connect("button-release-event", self.on_release)
        self.connect("motion-notify-event", self.on_motion)
        self.connect("leave-notify-event", lambda *a: self.emit("hint", ""))
        self.connect("query-tooltip", self.on_tooltip)
        state.connect("tool-changed", lambda *a: self.queue_draw())
        state.connect("options-changed", lambda *a: self.queue_draw())
        state.connect("colors-changed", lambda *a: self.queue_draw())

    # -- geometry ------------------------------------------------------------
    def tool_at(self, x, y):
        col = int((x - X0) // BTN)
        row = int((y - Y0) // BTN)
        if 0 <= col < 2 and 0 <= row < ROWS and x >= X0 and y >= Y0 and row * 2 + col < len(TOOLS):
            return TOOLS[row * 2 + col]
        return None

    def option_items(self):
        """List of (rect, option_name, value) for the active tool."""
        t = self.state.tool
        bx, by = OPT_X + 2, OPT_Y + 2
        bw, bh = OPT_W - 4, OPT_H - 4
        items = []
        if t in ("rect_select", "free_select", "text"):
            for i in range(2):
                items.append(((bx + 1, by + 4 + i * 26, bw - 2, 24), "transparent", bool(i)))
        elif t == "eraser":
            # Square sizes on the left, round sizes on the right.
            for col, shape in enumerate(("square", "circle")):
                for i in range(4):
                    items.append(((bx + 1 + col * 19, by + 4 + i * 16, 18, 16),
                                  ("eraser_shape", "eraser_size"), (shape, i)))
        elif t == "sticker":
            # Recent stickers in a 2x3 grid, then a button for the book.
            for i, sid in enumerate(self.state.sticker_recent[:6]):
                r, c = divmod(i, 2)
                items.append(((bx + 1 + c * 19, by + 2 + r * 19, 18, 18), "sticker", sid))
            items.append(((bx + 1, by + 62, bw - 2, 30), "sticker_book", True))
        elif t == "magic_wand":
            for i in range(2):
                items.append(((bx + 2, by + 4 + i * 26, bw - 4, 24), "wand_global", bool(i)))
        elif t == "fill":
            for i in range(3):
                items.append(((bx + 2, by + 4 + i * 20, bw - 4, 18), "fill_mode", i))
        elif t == "magnifier":
            for i in range(4):
                items.append(((bx + 1, by + 4 + i * 14, bw - 2, 14), "magnify", i))
        elif t == "brush":
            for i in range(12):
                r, c = divmod(i, 3)
                items.append(((bx + 2 + c * 12, by + 4 + r * 13, 12, 13), "brush", i))
        elif t == "airbrush":
            items.append(((bx + 1, by + 3, 16, 18), "airbrush_size", 0))
            items.append(((bx + 18, by + 3, 20, 22), "airbrush_size", 1))
            items.append(((bx + 4, by + 27, 30, 30), "airbrush_size", 2))
        elif t in ("line", "curve"):
            for i in range(5):
                items.append(((bx + 2, by + 4 + i * 12, bw - 4, 11), "line_width", i + 1))
        elif t in ("rectangle", "polygon", "ellipse", "rounded_rect"):
            for i in range(3):
                items.append(((bx + 2, by + 4 + i * 20, bw - 4, 18), "fill_style", i))
        return items

    def option_at(self, x, y):
        for rect, name, value in self.option_items():
            rx, ry, rw, rh = rect
            if rx <= x < rx + rw and ry <= y < ry + rh:
                return name, value
        return None

    def is_selected(self, name, value):
        if name == "sticker_book":
            return False
        if isinstance(name, tuple):
            return all(getattr(self.state, n) == v for n, v in zip(name, value))
        return getattr(self.state, name) == value

    # -- events ----------------------------------------------------------------
    def on_press(self, w, ev):
        if ev.button != 1:
            return True
        tool = self.tool_at(ev.x, ev.y)
        if tool:
            self.state.set_tool(tool)
            return True
        opt = self.option_at(ev.x, ev.y)
        if opt:
            name, value = opt
            if name == "brush":
                self.state.choose_brush_preset(value)
            elif name == "sticker":
                self.state.choose_sticker(value)
            elif name == "sticker_book":
                self.emit("open-sticker-book")
            elif name == ("eraser_shape", "eraser_size"):
                self.state.choose_eraser_preset(*value)
            elif isinstance(name, tuple):
                for n, v in zip(name, value):
                    self.state.set_option(n, v)
            else:
                self.state.set_option(name, value)
        return True

    def on_release(self, w, ev):
        return True

    def on_motion(self, w, ev):
        tool = self.tool_at(ev.x, ev.y)
        self.emit("hint", TOOL_HELP[tool] if tool else "")
        return True

    def on_tooltip(self, w, x, y, keyboard, tooltip):
        tool = self.tool_at(x, y)
        if not tool:
            return False
        tooltip.set_text(TOOL_NAMES[tool])
        col, row = TOOLS.index(tool) % 2, TOOLS.index(tool) // 2
        rect = Gdk.Rectangle()
        rect.x, rect.y, rect.width, rect.height = X0 + col * BTN, Y0 + row * BTN, BTN, BTN
        tooltip.set_tip_area(rect)
        return True

    # -- drawing ---------------------------------------------------------------
    def on_draw(self, w, cr):
        cr.set_source_rgb(*win98.FACE)
        cr.paint()
        for i, tool in enumerate(TOOLS):
            col, row = i % 2, i // 2
            x, y = X0 + col * BTN, Y0 + row * BTN
            active = tool == self.state.tool
            if active:
                win98.dither_fill(cr, x, y, BTN, BTN)
                win98.pressed(cr, x, y, BTN, BTN, fill=False)
            else:
                win98.raised(cr, x, y, BTN, BTN)
            off = 1 if active else 0
            pixmaps.paint(cr, tool, x + 4 + off, y + 4 + off)

        win98.sunken_thin(cr, OPT_X, OPT_Y, OPT_W, OPT_H)
        self.draw_options(cr)
        return True

    def draw_options(self, cr):
        st = self.state
        for rect, name, value in self.option_items():
            x, y, w, h = rect
            sel = self.is_selected(name, value)
            if sel:
                cr.set_source_rgb(*NAVY)
                cr.rectangle(x, y, w, h)
                cr.fill()
            fg = (1, 1, 1) if sel else (0, 0, 0)
            if name == "transparent":
                self.draw_mode_icon(cr, x + (w - 32) // 2, y + (h - 20) // 2, value)
            elif name == ("eraser_shape", "eraser_size"):
                shape, idx = value
                size = ERASER_SIZES[idx]
                offs = disc_offsets(size) if shape == "circle" else square_offsets(size)
                cx, cy = x + w // 2, y + h // 2
                cr.set_source_rgb(*fg)
                for ox, oy in offs:
                    cr.rectangle(cx + ox, cy + oy, 1, 1)
                cr.fill()
            elif name == "sticker":
                if stickers.exists(value):
                    img = stickers.render(value, 16)
                    cr.set_source_surface(img, x + 1, y + 1)
                    cr.paint()
            elif name == "sticker_book":
                win98.raised(cr, x, y, w, h)
                pixmaps.paint(cr, "sticker", x + (w - 16) // 2, y + 2)
                layout = PangoCairo.create_layout(cr)
                layout.set_font_description(Pango.FontDescription("Sans 6"))
                layout.set_text("Book", -1)
                _, lr = layout.get_pixel_extents()
                cr.set_source_rgb(0, 0, 0)
                cr.move_to(x + (w - lr.width) // 2, y + 18)
                PangoCairo.show_layout(cr, layout)
            elif name == "wand_global":
                self.draw_wand_mode(cr, x + (w - 28) // 2, y + 4, value)
            elif name == "fill_mode":
                self.draw_fill_mode(cr, x + 4, y + 3, w - 8, h - 6, value)
            elif name == "magnify":
                layout = PangoCairo.create_layout(cr)
                layout.set_font_description(Pango.FontDescription("Sans 7"))
                layout.set_text("%dx" % MAGNIFY_LEVELS[value], -1)
                _, lr = layout.get_pixel_extents()
                cr.set_source_rgb(*fg)
                cr.move_to(x + (w - lr.width) // 2, y + (h - lr.height) // 2)
                PangoCairo.show_layout(cr, layout)
            elif name == "brush":
                kind, size = BRUSH_SHAPES[value]
                cx, cy = x + w // 2, y + h // 2
                cr.set_source_rgb(*fg)
                for ox, oy in brush_offsets(kind, size):
                    cr.rectangle(cx + ox, cy + oy, 1, 1)
                cr.fill()
            elif name == "airbrush":
                pass
            elif name == "airbrush_size":
                cx, cy = x + w // 2, y + h // 2
                cr.set_source_rgb(*fg)
                for ox, oy in AIR_DOTS[value]:
                    cr.rectangle(cx + ox, cy + oy, 1, 1)
                cr.fill()
            elif name == "line_width":
                cr.set_source_rgb(*fg)
                cr.rectangle(x + 3, y + (h - value) // 2, w - 6, value)
                cr.fill()
            elif name == "fill_style":
                rx, ry, rw, rh = x + 4, y + 4, w - 8, h - 8
                if value in (0, 1):
                    cr.set_source_rgb(*fg)
                    cr.rectangle(rx, ry, rw, rh)
                    cr.fill()
                    if value == 0:
                        cr.set_source_rgb(*(NAVY if sel else win98.FACE))
                    else:
                        cr.set_source_rgb(*win98.SHADOW)
                    cr.rectangle(rx + 1, ry + 1, rw - 2, rh - 2)
                    cr.fill()
                else:
                    cr.set_source_rgb(*win98.SHADOW)
                    cr.rectangle(rx, ry, rw, rh)
                    cr.fill()

    @staticmethod
    def draw_mode_icon(cr, x, y, transparent):
        """Little picture of shapes over (or without) a background."""
        cr.save()
        cr.set_antialias(cairo.ANTIALIAS_NONE)
        if not transparent:
            cr.set_source_rgb(0, 0, 0)
            cr.rectangle(x, y, 32, 20)
            cr.fill()
            cr.set_source_rgb(1, 1, 1)
            cr.rectangle(x + 1, y + 1, 30, 18)
            cr.fill()
        cr.set_source_rgb(0, 0, 1)
        cr.rectangle(x + 4, y + 4, 11, 11)
        cr.fill()
        cr.set_source_rgb(1, 0, 0)
        cr.move_to(x + 23, y + 3)
        cr.line_to(x + 30, y + 17)
        cr.line_to(x + 16, y + 17)
        cr.close_path()
        cr.fill()
        cr.set_source_rgb(1, 1, 0)
        cr.arc(x + 16, y + 12, 5, 0, 6.2832)
        cr.fill()
        cr.restore()

    @staticmethod
    def draw_fill_mode(cr, x, y, w, h, mode):
        """Solid, linear gradient or radial gradient swatch."""
        cr.save()
        cr.set_source_rgb(0, 0, 0)
        cr.rectangle(x, y, w, h)
        cr.fill()
        if mode == 0:
            cr.set_source_rgb(*win98.SHADOW)
        elif mode == 1:
            pat = cairo.LinearGradient(x + 1, 0, x + w - 1, 0)
            pat.add_color_stop_rgb(0, 0, 0, 0)
            pat.add_color_stop_rgb(1, 1, 1, 1)
            cr.set_source(pat)
        else:
            cx, cy = x + w / 2, y + h / 2
            pat = cairo.RadialGradient(cx, cy, 0, cx, cy, w / 2)
            pat.add_color_stop_rgb(0, 1, 1, 1)
            pat.add_color_stop_rgb(1, 0, 0, 0)
            cr.set_source(pat)
        cr.rectangle(x + 1, y + 1, w - 2, h - 2)
        cr.fill()
        cr.restore()

    @staticmethod
    def draw_wand_mode(cr, x, y, everywhere):
        """Touching area only (one blob) or all similar colours (scattered)."""
        cr.save()
        cr.set_antialias(cairo.ANTIALIAS_NONE)
        cr.set_source_rgb(1, 1, 1)
        cr.rectangle(x, y, 28, 16)
        cr.fill()
        cr.set_source_rgb(0, 0, 0)
        cr.rectangle(x + 0.5, y + 0.5, 27, 15)
        cr.set_line_width(1)
        cr.stroke()
        cr.set_source_rgb(0.85, 0, 0)
        spots = ([(3, 3, 9, 7)] if not everywhere else
                 [(3, 3, 6, 5), (16, 2, 7, 5), (8, 10, 6, 4), (20, 9, 5, 5)])
        for sx, sy, sw, sh in spots:
            cr.rectangle(x + sx, y + sy, sw, sh)
        cr.fill()
        if not everywhere:
            # A second red area that is not touching stays unselected (outlined).
            cr.set_source_rgb(0.85, 0.6, 0.6)
            cr.rectangle(x + 17, y + 8, 7, 5)
            cr.fill()
        cr.restore()
