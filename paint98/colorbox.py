"""The colour box: foreground/background indicator and the 28 colour palette."""

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gdk, GObject, Gtk  # noqa: E402

from . import win98  # noqa: E402
from .funpaints import RAINBOW, is_fun  # noqa: E402

CELL = 16
IND_X, IND_Y, IND_W, IND_H = 3, 6, 30, 31
PAL_X, PAL_Y = IND_X + IND_W + 2, 6
SWAP_X, SWAP_Y, SWAP_W, SWAP_H = PAL_X + 14 * CELL + 4, PAL_Y, 22, 2 * CELL
FUN_X = SWAP_X + SWAP_W + 2
HEIGHT = 44


def _rgb(c):
    return (c[0] / 255, c[1] / 255, c[2] / 255)


class ColorBox(Gtk.DrawingArea):
    __gsignals__ = {
        "edit-color": (GObject.SignalFlags.RUN_FIRST, None, (int,)),
        # The palette cell last clicked (used by Options > Edit Colors).
        "palette-index": (GObject.SignalFlags.RUN_FIRST, None, (int,)),
        # Double-click on the foreground ("fg") or background ("bg") swatch.
        "edit-indicator": (GObject.SignalFlags.RUN_FIRST, None, (str,)),
        "hint": (GObject.SignalFlags.RUN_FIRST, None, (str,)),
    }

    def __init__(self, state):
        super().__init__()
        self.state = state
        self.set_size_request(FUN_X + SWAP_W + 4, HEIGHT)
        self.swap_down = False
        self.fun_down = False
        self.set_has_tooltip(True)
        self.connect("query-tooltip", self.on_tooltip)
        self.add_events(Gdk.EventMask.BUTTON_PRESS_MASK | Gdk.EventMask.BUTTON_RELEASE_MASK
                        | Gdk.EventMask.POINTER_MOTION_MASK | Gdk.EventMask.LEAVE_NOTIFY_MASK)
        self.connect("button-release-event", self.on_release)
        self.connect("draw", self.on_draw)
        self.connect("button-press-event", self.on_press)
        self.connect("motion-notify-event", self.on_motion)
        self.connect("leave-notify-event", lambda *a: self.emit("hint", ""))
        state.connect("colors-changed", lambda *a: self.queue_draw())
        state.connect("palette-changed", lambda *a: self.queue_draw())

    def index_at(self, x, y):
        col = int((x - PAL_X) // CELL)
        row = int((y - PAL_Y) // CELL)
        if x >= PAL_X and y >= PAL_Y and 0 <= col < 14 and 0 <= row < 2:
            return row * 14 + col
        return None

    def indicator_at(self, x, y):
        """'fg' or 'bg' for the two swatches in the indicator, else None."""
        fx, fy = IND_X + 4, IND_Y + 4
        bx, by = IND_X + 12, IND_Y + 13
        if fx <= x < fx + 15 and fy <= y < fy + 15:
            return "fg"
        if bx <= x < bx + 15 and by <= y < by + 15:
            return "bg"
        return None

    def on_swap(self, x, y):
        return SWAP_X <= x < SWAP_X + SWAP_W and SWAP_Y <= y < SWAP_Y + SWAP_H

    def on_fun(self, x, y):
        return FUN_X <= x < FUN_X + SWAP_W and SWAP_Y <= y < SWAP_Y + SWAP_H

    def swap_text(self):
        if self.state.palette_mode == "custom":
            return "Custom palette. Click to show the original colors."
        if self.state.palette_mode == "fun":
            return "Click to go back to the %s colors." % self.state.last_plain
        return "Original palette. Click to show your custom colors."

    def fun_text(self):
        if self.state.palette_mode == "fun":
            return "Fun Colors are on. Click to go back to the normal colors."
        return "Fun Colors: rainbow, fire, stars, hearts and more. Click to try them!"

    def on_tooltip(self, w, x, y, keyboard, tooltip):
        if self.on_fun(x, y):
            tooltip.set_text("Fun Colors")
            return True
        if not self.on_swap(x, y):
            return False
        tooltip.set_text("Custom Colors" if self.state.last_plain == "custom" else "Original Colors")
        return True

    def on_release(self, w, ev):
        st = self.state
        if self.swap_down:
            self.swap_down = False
            self.queue_draw()
            if self.on_swap(ev.x, ev.y):
                if st.palette_mode == "fun":
                    st.set_palette_mode(st.last_plain)
                else:
                    st.set_use_custom(not st.use_custom)
        if self.fun_down:
            self.fun_down = False
            self.queue_draw()
            if self.on_fun(ev.x, ev.y):
                st.set_palette_mode(st.last_plain if st.palette_mode == "fun" else "fun")
        return True

    def on_motion(self, w, ev):
        if self.indicator_at(ev.x, ev.y):
            self.emit("hint", "Click to edit the foreground or background color (hex too).")
        elif self.on_fun(ev.x, ev.y):
            self.emit("hint", self.fun_text())
        elif self.on_swap(ev.x, ev.y):
            self.emit("hint", self.swap_text())
        elif self.index_at(ev.x, ev.y) is not None:
            i = self.index_at(ev.x, ev.y)
            c = self.state.palette[i]
            if is_fun(c):
                self.emit("hint", "%s: a magic paint for every tool. Left-click to paint with it." % c.name)
            else:
                self.emit("hint", "Selects colors. Left-click selects the foreground; "
                                  "right-click selects the background.")
        else:
            self.emit("hint", "")
        return True

    def on_press(self, w, ev):
        if ev.button == 1 and self.on_swap(ev.x, ev.y):
            if ev.type == Gdk.EventType.BUTTON_PRESS:
                self.swap_down = True
                self.queue_draw()
            return True
        if ev.button == 1 and self.on_fun(ev.x, ev.y):
            if ev.type == Gdk.EventType.BUTTON_PRESS:
                self.fun_down = True
                self.queue_draw()
            return True
        which = self.indicator_at(ev.x, ev.y)
        if which:
            if ev.button == 1 and ev.type == Gdk.EventType.BUTTON_PRESS:
                self.emit("edit-indicator", which)
            return True
        i = self.index_at(ev.x, ev.y)
        if i is None:
            return True
        color = self.state.palette[i]
        self.emit("palette-index", i)
        if ev.type == Gdk.EventType._2BUTTON_PRESS and ev.button == 1 and not is_fun(color):
            self.emit("edit-color", i)
            return True
        if ev.type != Gdk.EventType.BUTTON_PRESS:
            return True
        if ev.button == 1:
            self.state.set_fg(color)
        elif ev.button == 3:
            self.state.set_bg(color)
        return True

    def on_draw(self, w, cr):
        cr.set_source_rgb(*win98.FACE)
        cr.paint()
        # Foreground / background indicator.
        win98.dither_fill(cr, IND_X, IND_Y, IND_W, IND_H)
        win98.sunken_field(cr, IND_X, IND_Y, IND_W, IND_H)
        self._swatch(cr, IND_X + 12, IND_Y + 13, 15, 15, self.state.bg)
        self._swatch(cr, IND_X + 4, IND_Y + 4, 15, 15, self.state.fg)
        # Palette.
        for i, c in enumerate(self.state.palette):
            row, col = divmod(i, 14)
            x, y = PAL_X + col * CELL, PAL_Y + row * CELL
            if is_fun(c):
                win98.sunken_field(cr, x, y, CELL, CELL)
                c.draw_swatch(cr, x + 2, y + 2, CELL - 4, CELL - 4)
            else:
                win98.sunken_field(cr, x, y, CELL, CELL, _rgb(c))
        self.draw_swap(cr)
        self.draw_fun(cr)
        return True

    def draw_swap(self, cr):
        """Toggle button: up = original palette, down (dithered) = custom."""
        x, y, w, h = SWAP_X, SWAP_Y, SWAP_W, SWAP_H
        down = self.state.palette_mode == "custom" or self.swap_down
        if down:
            win98.dither_fill(cr, x, y, w, h)
            win98.pressed(cr, x, y, w, h, fill=False)
        else:
            win98.raised(cr, x, y, w, h)
        o = 1 if down else 0
        # Two little swatch columns: the palette that is showing on top.
        pal = self.state.custom_palette if self.state.last_plain == "custom" else self.state.original_palette
        cols = [pal[16], pal[17], pal[18], pal[20]]
        for i, c in enumerate(cols):
            cx = x + 5 + o + (i % 2) * 6
            cy = y + 5 + o + (i // 2) * 6
            cr.set_source_rgb(0, 0, 0)
            cr.rectangle(cx, cy, 6, 6)
            cr.fill()
            cr.set_source_rgb(*_rgb(c))
            cr.rectangle(cx + 1, cy + 1, 4, 4)
            cr.fill()
        # Letter O(riginal) / C(ustom) underneath.
        cr.set_source_rgb(0, 0, 0)
        lx, ly = x + 7 + o, y + 20 + o
        if self.state.last_plain == "custom":
            for px, py in ((1, 0), (2, 0), (3, 0), (0, 1), (0, 2), (0, 3), (0, 4), (1, 5), (2, 5), (3, 5)):
                cr.rectangle(lx + px, ly + py, 1, 1)
        else:
            for px, py in ((1, 0), (2, 0), (0, 1), (3, 1), (0, 2), (3, 2), (0, 3), (3, 3), (0, 4), (3, 4),
                           (1, 5), (2, 5)):
                cr.rectangle(lx + px, ly + py, 1, 1)
        cr.fill()

    def draw_fun(self, cr):
        """The Fun Colors toggle: a rainbow over a cloud, with a star."""
        x, y, w, h = FUN_X, SWAP_Y, SWAP_W, SWAP_H
        down = self.state.palette_mode == "fun" or self.fun_down
        if down:
            win98.dither_fill(cr, x, y, w, h)
            win98.pressed(cr, x, y, w, h, fill=False)
        else:
            win98.raised(cr, x, y, w, h)
        o = 1 if down else 0
        cx, cy = x + w / 2 + o, y + 17 + o
        cr.save()
        cr.set_line_width(1.6)
        for i, c in enumerate(RAINBOW[:6]):
            cr.set_source_rgb(*_rgb(c))
            cr.arc(cx, cy, 8 - i * 1.4, 3.1416, 2 * 3.1416)
            cr.stroke()
        cr.restore()
        # little star
        cr.set_source_rgb(1, 0.85, 0)
        sx, sy = x + 11 + o, y + 23 + o
        for dx, dy in ((0, -2), (0, -1), (-2, 0), (-1, 0), (0, 0), (1, 0), (2, 0), (0, 1), (-1, 2), (1, 2)):
            cr.rectangle(sx + dx, sy + dy, 1, 1)
        cr.fill()

    def _swatch(self, cr, x, y, w, h, c):
        cr.set_source_rgb(*win98.FACE)
        cr.rectangle(x, y, w, h)
        cr.fill()
        win98.frame(cr, x, y, w, h, win98.WHITE, win98.SHADOW)
        cr.set_source_rgb(*win98.DARK)
        cr.rectangle(x + 1, y + 1, w - 2, h - 2)
        cr.fill()
        if is_fun(c):
            c.draw_swatch(cr, x + 2, y + 2, w - 4, h - 4)
        else:
            cr.set_source_rgb(*_rgb(c))
            cr.rectangle(x + 2, y + 2, w - 4, h - 4)
            cr.fill()
