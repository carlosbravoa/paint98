"""The Tool Settings toolbar: opacity for painting tools, tolerance for fill."""

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gdk, GObject, Gtk  # noqa: E402

from . import win98  # noqa: E402
from .state import TOOL_NAMES  # noqa: E402


class Trackbar(Gtk.DrawingArea):
    """A classic trackbar: sunken groove, raised thumb and tick marks."""

    __gsignals__ = {
        "value-changed": (GObject.SignalFlags.RUN_FIRST, None, (int,)),
    }
    PAD = 7
    HEIGHT = 20

    def __init__(self, lo, hi, value, width=110):
        super().__init__()
        self.lo, self.hi = lo, hi
        self.value = value
        self.dragging = False
        self.set_size_request(width, self.HEIGHT)
        self.set_can_focus(True)
        self.add_events(Gdk.EventMask.BUTTON_PRESS_MASK | Gdk.EventMask.BUTTON_RELEASE_MASK
                        | Gdk.EventMask.BUTTON_MOTION_MASK | Gdk.EventMask.SCROLL_MASK
                        | Gdk.EventMask.KEY_PRESS_MASK)
        self.connect("draw", self.on_draw)
        self.connect("button-press-event", self.on_press)
        self.connect("button-release-event", self.on_release)
        self.connect("motion-notify-event", self.on_motion)
        self.connect("scroll-event", self.on_scroll)
        self.connect("key-press-event", self.on_key)

    def _span(self):
        return self.get_allocated_width() - 2 * self.PAD

    def _x_for(self, value):
        return self.PAD + round((value - self.lo) * self._span() / (self.hi - self.lo))

    def _value_at(self, x):
        v = self.lo + (x - self.PAD) * (self.hi - self.lo) / max(1, self._span())
        return int(round(max(self.lo, min(self.hi, v))))

    def set_value(self, value, emit=True):
        value = int(max(self.lo, min(self.hi, value)))
        if value != self.value:
            self.value = value
            self.queue_draw()
            if emit:
                self.emit("value-changed", value)

    def on_press(self, w, ev):
        if ev.button == 1 and self.get_sensitive():
            self.grab_focus()
            self.dragging = True
            self.set_value(self._value_at(ev.x))
        return True

    def on_motion(self, w, ev):
        if self.dragging:
            self.set_value(self._value_at(ev.x))
        return True

    def on_release(self, w, ev):
        self.dragging = False
        return True

    def on_scroll(self, w, ev):
        step = max(1, (self.hi - self.lo) // 20)
        if ev.direction == Gdk.ScrollDirection.UP:
            self.set_value(self.value + step)
        elif ev.direction == Gdk.ScrollDirection.DOWN:
            self.set_value(self.value - step)
        elif ev.direction == Gdk.ScrollDirection.SMOOTH:
            self.set_value(self.value - step * (1 if ev.delta_y > 0 else -1 if ev.delta_y < 0 else 0))
        return True

    def on_key(self, w, ev):
        page = max(1, (self.hi - self.lo) // 10)
        moves = {Gdk.KEY_Left: -1, Gdk.KEY_Down: -1, Gdk.KEY_Right: 1, Gdk.KEY_Up: 1,
                 Gdk.KEY_Page_Down: -page, Gdk.KEY_Page_Up: page}
        if ev.keyval in moves:
            self.set_value(self.value + moves[ev.keyval])
            return True
        if ev.keyval == Gdk.KEY_Home:
            self.set_value(self.lo)
            return True
        if ev.keyval == Gdk.KEY_End:
            self.set_value(self.hi)
            return True
        return False

    def on_draw(self, w, cr):
        width = self.get_allocated_width()
        cy = 6
        # Groove
        win98.sunken_field(cr, self.PAD - 2, cy - 2, width - 2 * self.PAD + 4, 4, (1, 1, 1))
        # Ticks every 10%
        cr.set_source_rgb(0, 0, 0)
        for i in range(11):
            x = self.PAD + round(i * self._span() / 10)
            cr.rectangle(x, 17, 1, 3 if i in (0, 10) else 2)
        cr.fill()
        # Thumb: raised block with a pointed bottom.
        tw, th, tip = 11, 10, 5
        tx = self._x_for(self.value) - tw // 2
        cr.set_source_rgb(*win98.FACE)
        cr.move_to(tx, 0)
        cr.line_to(tx + tw, 0)
        cr.line_to(tx + tw, th)
        cr.line_to(tx + tw // 2 + 0.5, th + tip)
        cr.line_to(tx, th)
        cr.close_path()
        cr.fill()
        win98._hline(cr, tx, 0, tw - 1, win98.WHITE)
        win98._vline(cr, tx, 0, th, win98.WHITE)
        win98._vline(cr, tx + tw - 1, 0, th + 1, win98.DARK)
        win98._vline(cr, tx + tw - 2, 1, th, win98.SHADOW)
        for i in range(tip):
            win98._hline(cr, tx + i, th + i, 1, win98.WHITE)
            win98._hline(cr, tx + tw - 1 - i, th + i, 1, win98.DARK)
            win98._hline(cr, tx + tw - 2 - i, th + i, 1, win98.SHADOW)
        if self.has_focus():
            win98.dotted_rect(cr, 0, 0, width, self.HEIGHT)
        return True


class ValueControl(Gtk.Box):
    """Label + trackbar + numeric entry + unit."""

    __gsignals__ = {
        "value-changed": (GObject.SignalFlags.RUN_FIRST, None, (int,)),
    }

    def __init__(self, label, lo, hi, value, unit="%"):
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        self.lo, self.hi = lo, hi
        self.label = Gtk.Label.new_with_mnemonic(label)
        self.label.set_xalign(1)
        self.label.set_width_chars(9)
        self.pack_start(self.label, False, False, 0)
        self.track = Trackbar(lo, hi, value)
        self.label.set_mnemonic_widget(self.track)
        self.pack_start(self.track, False, False, 0)
        self.entry = Gtk.Entry()
        self.entry.set_width_chars(3)
        self.entry.set_max_width_chars(3)
        self.entry.set_text(str(value))
        self.pack_start(self.entry, False, False, 0)
        self.unit = Gtk.Label(label=unit, xalign=0)
        self.unit.set_width_chars(2)
        self.pack_start(self.unit, False, False, 0)
        self.track.connect("value-changed", self.on_track)
        self.entry.connect("activate", self.on_entry)
        self.entry.connect("focus-out-event", lambda *a: self.on_entry() or False)

    def on_track(self, track, value):
        self.entry.set_text(str(value))
        self.emit("value-changed", value)

    def on_entry(self, *a):
        try:
            v = int(self.entry.get_text().strip().rstrip("%"))
        except ValueError:
            v = self.track.value
        v = max(self.lo, min(self.hi, v))
        self.entry.set_text(str(v))
        if v != self.track.value:
            self.track.set_value(v)

    def set_value(self, value):
        self.track.set_value(value, emit=False)
        self.entry.set_text(str(value))

    def set_range(self, lo, hi):
        self.lo, self.hi = lo, hi
        self.track.lo, self.track.hi = lo, hi
        self.track.queue_draw()


class ToolSettingsPanel(Gtk.Box):
    """Opacity / Size / Tolerance controls next to the colour box.

    It keeps a fixed size so the layout never jumps; each tool shows only
    the rows that apply to it (at most two)."""

    def __init__(self, state):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        self.state = state
        self.get_style_context().add_class("tool-settings")
        self.set_valign(Gtk.Align.CENTER)
        self.set_size_request(260, 44)
        self.opacity = ValueControl("_Opacity:", 1, 100, 100)
        self.opacity.connect("value-changed", lambda w, v: self.state.set_opacity(self.state.tool, v))
        self.size = ValueControl("Si_ze:", 1, 64, 1, "px")
        self.size.connect("value-changed", lambda w, v: self.state.set_tool_size(self.state.tool, v))
        self.tolerance = ValueControl("To_lerance:", 0, 100, state.tolerance)
        self.tolerance.connect("value-changed", lambda w, v: self.state.set_option("tolerance", v))
        for row in (self.opacity, self.size, self.tolerance):
            row.set_no_show_all(True)
            self.pack_start(row, False, False, 0)
        state.connect("tool-changed", lambda *a: self.sync())
        state.connect("options-changed", lambda *a: self.sync())
        self.sync()

    @staticmethod
    def _show(row, visible):
        if visible:
            for child in row.get_children():
                child.show()
            row.show()
        else:
            row.hide()

    def sync(self):
        st = self.state
        tool = st.tool
        self._show(self.opacity, tool in st.opacity)
        self.opacity.set_value(st.opacity.get(tool, 100))
        size = st.tool_size(tool)
        self._show(self.size, size is not None)
        if size is not None:
            self.size.set_range(*st.SIZE_LIMITS[tool])
            self.size.set_value(size)
        self._show(self.tolerance, tool == "fill")
        self.tolerance.set_value(st.tolerance)
