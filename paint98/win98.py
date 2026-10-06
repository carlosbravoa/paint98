"""Classic 3D chrome: bevels, title bars, windows, dialogs and message boxes."""

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gdk, GLib, Gtk, Pango  # noqa: E402

import cairo  # noqa: E402

from . import pixmaps  # noqa: E402

WHITE = (1, 1, 1)
LIGHT = (0xDF / 255,) * 3
FACE = (0xC0 / 255,) * 3
SHADOW = (0x80 / 255,) * 3
DARK = (0, 0, 0)
NAVY = (0, 0, 0x80 / 255)


def _hline(cr, x, y, w, c):
    cr.set_source_rgb(*c)
    cr.rectangle(x, y, w, 1)
    cr.fill()


def _vline(cr, x, y, h, c):
    cr.set_source_rgb(*c)
    cr.rectangle(x, y, 1, h)
    cr.fill()


def frame(cr, x, y, w, h, tl_out, br_out, tl_in=None, br_in=None):
    """Two-pixel classic frame. Colors for outer/inner top-left/bottom-right."""
    _hline(cr, x, y, w - 1, tl_out)
    _vline(cr, x, y, h - 1, tl_out)
    _hline(cr, x, y + h - 1, w, br_out)
    _vline(cr, x + w - 1, y, h, br_out)
    if tl_in is not None:
        _hline(cr, x + 1, y + 1, w - 3, tl_in)
        _vline(cr, x + 1, y + 1, h - 3, tl_in)
    if br_in is not None:
        _hline(cr, x + 1, y + h - 2, w - 2, br_in)
        _vline(cr, x + w - 2, y + 1, h - 2, br_in)


def raised(cr, x, y, w, h, fill=True):
    if fill:
        cr.set_source_rgb(*FACE)
        cr.rectangle(x, y, w, h)
        cr.fill()
    frame(cr, x, y, w, h, WHITE, DARK, LIGHT, SHADOW)


def pressed(cr, x, y, w, h, fill=True):
    if fill:
        cr.set_source_rgb(*FACE)
        cr.rectangle(x, y, w, h)
        cr.fill()
    frame(cr, x, y, w, h, DARK, WHITE, SHADOW, LIGHT)


def sunken_field(cr, x, y, w, h, fill=None):
    if fill is not None:
        cr.set_source_rgb(*fill)
        cr.rectangle(x, y, w, h)
        cr.fill()
    frame(cr, x, y, w, h, SHADOW, WHITE, DARK, LIGHT)


def sunken_thin(cr, x, y, w, h):
    frame(cr, x, y, w, h, SHADOW, WHITE)


_dither = None


def dither_pattern():
    """The white/silver checkerboard used for pushed toolbar buttons."""
    global _dither
    if _dither is None:
        s = cairo.ImageSurface(cairo.FORMAT_RGB24, 2, 2)
        cr = cairo.Context(s)
        cr.set_source_rgb(*FACE)
        cr.paint()
        cr.set_source_rgb(*WHITE)
        cr.rectangle(0, 0, 1, 1)
        cr.rectangle(1, 1, 1, 1)
        cr.fill()
        _dither = cairo.SurfacePattern(s)
        _dither.set_extend(cairo.EXTEND_REPEAT)
        _dither.set_filter(cairo.FILTER_NEAREST)
    return _dither


def dither_fill(cr, x, y, w, h):
    cr.save()
    cr.translate(x, y)
    cr.set_source(dither_pattern())
    cr.rectangle(0, 0, w, h)
    cr.fill()
    cr.restore()


def dotted_rect(cr, x, y, w, h, color=DARK):
    """1px dotted focus rectangle (every other pixel)."""
    x, y, w, h = round(x), round(y), round(w), round(h)
    cr.set_source_rgb(*color)
    for i in range(0, w, 2):
        cr.rectangle(x + i, y, 1, 1)
        cr.rectangle(x + i, y + h - 1, 1, 1)
    for i in range(0, h, 2):
        cr.rectangle(x, y + i, 1, 1)
        cr.rectangle(x + w - 1, y + i, 1, 1)
    cr.fill()


# ---------------------------------------------------------------------------
# Title bar
# ---------------------------------------------------------------------------

class CaptionButton(Gtk.DrawingArea):
    W, H = 16, 14

    def __init__(self, kind, callback):
        super().__init__()
        self.kind = kind
        self.callback = callback
        self.down = False
        self.inside = False
        self.set_size_request(self.W, self.H)
        self.set_valign(Gtk.Align.CENTER)
        self.add_events(Gdk.EventMask.BUTTON_PRESS_MASK | Gdk.EventMask.BUTTON_RELEASE_MASK
                        | Gdk.EventMask.POINTER_MOTION_MASK)
        self.connect("draw", self._draw)
        self.connect("button-press-event", self._press)
        self.connect("button-release-event", self._release)
        self.connect("motion-notify-event", self._motion)

    def _draw(self, widget, cr):
        w, h = self.get_allocated_width(), self.get_allocated_height()
        sunk = self.down and self.inside
        if sunk:
            pressed(cr, 0, 0, w, h)
        else:
            raised(cr, 0, 0, w, h)
        glyph = {
            "min": "GLYPH_MIN",
            "max": "GLYPH_MAX",
            "restore": "GLYPH_RESTORE",
            "close": "GLYPH_CLOSE",
            "help": "GLYPH_HELP",
        }[self.kind]
        rows = getattr(pixmaps, glyph)
        gw, gh = len(rows[0]), len(rows)
        gx = (w - gw) // 2 + (1 if sunk else 0)
        gy = (h - gh) // 2 + (1 if sunk else 0)
        if self.kind == "min":
            gy += 1
        pixmaps.paint(cr, glyph, gx, gy, disabled=not self.get_sensitive())
        return True

    def set_kind(self, kind):
        self.kind = kind
        self.queue_draw()

    def _press(self, w, ev):
        if ev.button == 1 and ev.type == Gdk.EventType.BUTTON_PRESS:
            self.down = True
            self.inside = True
            self.queue_draw()
        return True

    def _motion(self, w, ev):
        if self.down:
            a = self.get_allocation()
            inside = 0 <= ev.x < a.width and 0 <= ev.y < a.height
            if inside != self.inside:
                self.inside = inside
                self.queue_draw()
        return True

    def _release(self, w, ev):
        if ev.button == 1 and self.down:
            fire = self.inside
            self.down = False
            self.queue_draw()
            if fire:
                self.callback()
        return True


class TitleBar(Gtk.EventBox):
    def __init__(self, window, title, buttons=("min", "max", "close"), icon=True):
        super().__init__()
        self.window = window
        self.box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        self.box.get_style_context().add_class("win98-titlebar")
        self.add(self.box)

        if icon:
            ic = Gtk.DrawingArea()
            ic.set_size_request(16, 16)
            ic.set_margin_end(3)
            ic.connect("draw", lambda w, cr: pixmaps.paint(cr, "APP_ICON", 0, 0) or True)
            self.box.pack_start(ic, False, False, 0)
        self.label = Gtk.Label(label=title, xalign=0)
        self.label.set_ellipsize(Pango.EllipsizeMode.END)
        self.box.pack_start(self.label, True, True, 0)

        self.buttons = {}
        for kind in buttons:
            if kind == "close":
                b = CaptionButton("close", self.window.request_close)
                b.set_margin_start(2)
            elif kind == "min":
                b = CaptionButton("min", self.window.iconify)
            elif kind == "max":
                b = CaptionButton("max", self._toggle_max)
            elif kind == "help":
                b = CaptionButton("help", lambda: self.window.emit_help())
            self.buttons[kind] = b
            self.box.pack_start(b, False, False, 0)

        self.add_events(Gdk.EventMask.BUTTON_PRESS_MASK)
        self.connect("button-press-event", self._press)
        window.connect("window-state-event", self._state)

    def set_text(self, text):
        self.label.set_text(text)

    def _toggle_max(self):
        if not self.window.get_resizable():
            return
        if self.window.is_maximized():
            self.window.unmaximize()
        else:
            self.window.maximize()

    def _state(self, win, ev):
        b = self.buttons.get("max")
        if b is not None:
            maxed = bool(ev.new_window_state & Gdk.WindowState.MAXIMIZED)
            b.set_kind("restore" if maxed else "max")
        return False

    def _press(self, w, ev):
        if ev.button == 1 and ev.type == Gdk.EventType._2BUTTON_PRESS:
            if "max" in self.buttons:
                self._toggle_max()
            return True
        if ev.button == 1 and ev.type == Gdk.EventType.BUTTON_PRESS:
            self.window.begin_move_drag(ev.button, int(ev.x_root), int(ev.y_root), ev.time)
            return True
        if ev.button == 3:
            gdkwin = self.window.get_window()
            if gdkwin is not None:
                gdkwin.show_window_menu(ev)
            return True
        return False


# ---------------------------------------------------------------------------
# Windows
# ---------------------------------------------------------------------------

def always_underline(label):
    """Underline a mnemonic label's access key even when GTK hides mnemonics."""
    text = label.get_label()
    i = text.find("_")
    if i < 0 or i + 1 >= len(text):
        return
    shown = text[:i] + text[i + 1:]
    start = len(shown[:i].encode("utf-8"))
    attr = Pango.attr_underline_new(Pango.Underline.SINGLE)
    attr.start_index = start
    attr.end_index = start + len(shown[i].encode("utf-8"))
    attrs = Pango.AttrList()
    attrs.insert(attr)
    label.set_attributes(attrs)


def keep_mnemonics_visible(window):
    """Classic menus and dialogs always underline their access keys."""
    def force(w, *a):
        if not w.get_mnemonics_visible():
            w.set_mnemonics_visible(True)
    window.connect("notify::mnemonics-visible", force)
    window.set_mnemonics_visible(True)


class Win98Window(Gtk.Window):
    """A top-level window drawn entirely in the classic style."""

    def __init__(self, title="", buttons=("min", "max", "close"), icon=True, **kw):
        super().__init__(**kw)
        self.get_style_context().add_class("paint98")
        hidden = Gtk.Box()
        hidden.get_style_context().add_class("win98-hidden-titlebar")
        hidden.show()
        self.set_titlebar(hidden)

        self.frame = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.frame.get_style_context().add_class("win98-frame")
        self.titlebar = TitleBar(self, title, buttons, icon)
        self.frame.pack_start(self.titlebar, False, False, 0)
        self.body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.frame.pack_start(self.body, True, True, 0)
        Gtk.Window.add(self, self.frame)
        Gtk.Window.set_title(self, title)
        keep_mnemonics_visible(self)

    def set_title(self, title):
        Gtk.Window.set_title(self, title)
        self.titlebar.set_text(title)

    def request_close(self):
        self.close()

    def emit_help(self):
        pass


class Win98Dialog(Win98Window):
    """Modal dialog with a '?' and close caption button."""

    def __init__(self, parent, title, help_button=True):
        buttons = ("help", "close") if help_button else ("close",)
        super().__init__(title, buttons=buttons, icon=False)
        self.set_transient_for(parent)
        self.set_modal(True)
        self.set_resizable(False)
        self.set_type_hint(Gdk.WindowTypeHint.DIALOG)
        self.set_skip_taskbar_hint(True)
        self.response = None
        self._loop = None
        self.content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.content.set_border_width(8)
        self.body.pack_start(self.content, True, True, 0)
        self.connect("delete-event", self._on_delete)
        self.connect("key-press-event", self._on_key)

    def _on_delete(self, *a):
        self.finish(Gtk.ResponseType.CANCEL)
        return True

    def _on_key(self, w, ev):
        if ev.keyval == Gdk.KEY_Escape:
            self.finish(Gtk.ResponseType.CANCEL)
            return True
        return False

    def request_close(self):
        self.finish(Gtk.ResponseType.CANCEL)

    def finish(self, response):
        self.response = response
        if self._loop is not None and self._loop.is_running():
            self._loop.quit()

    def run(self):
        self.show_all()
        self.present()
        self._loop = GLib.MainLoop()
        self._loop.run()
        self.hide()
        return self.response


def make_button(label, callback=None, default=False):
    b = Gtk.Button.new_with_mnemonic(label)
    b.get_style_context().add_class("win98")
    if default:
        b.get_style_context().add_class("default")
        b.set_can_default(True)
    if callback is not None:
        b.connect("clicked", lambda *a: callback())
    return b


def warning_icon():
    """32x32 yellow triangle with an exclamation mark."""
    da = Gtk.DrawingArea()
    da.set_size_request(32, 32)

    def draw(w, cr):
        cr.set_antialias(cairo.ANTIALIAS_NONE)
        cr.move_to(16, 1)
        cr.line_to(31, 29)
        cr.line_to(1, 29)
        cr.close_path()
        cr.set_source_rgb(0, 0, 0)
        cr.fill()
        cr.move_to(16, 3)
        cr.line_to(29, 28)
        cr.line_to(3, 28)
        cr.close_path()
        cr.set_source_rgb(1, 1, 0)
        cr.fill()
        cr.set_source_rgb(0, 0, 0)
        cr.rectangle(15, 10, 3, 11)
        cr.rectangle(15, 23, 3, 3)
        cr.fill()
        return True

    da.connect("draw", draw)
    return da


def info_icon():
    da = Gtk.DrawingArea()
    da.set_size_request(32, 32)

    def draw(w, cr):
        cr.set_antialias(cairo.ANTIALIAS_NONE)
        cr.arc(16, 15, 14, 0, 6.3)
        cr.set_source_rgb(0, 0, 0)
        cr.fill()
        cr.arc(16, 15, 13, 0, 6.3)
        cr.set_source_rgb(1, 1, 1)
        cr.fill()
        cr.set_source_rgb(0, 0, 1)
        cr.rectangle(14, 7, 4, 3)
        cr.rectangle(14, 12, 4, 10)
        cr.rectangle(12, 12, 2, 2)
        cr.rectangle(12, 22, 8, 2)
        cr.fill()
        return True

    da.connect("draw", draw)
    return da


def message_box(parent, title, text, buttons=("OK",), icon="warning", default=0):
    """Show a classic message box. Returns the index of the pressed button or -1."""
    dlg = Win98Dialog(parent, title, help_button=False)
    row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=14)
    row.set_border_width(6)
    if icon == "warning":
        row.pack_start(warning_icon(), False, False, 0)
    elif icon == "info":
        row.pack_start(info_icon(), False, False, 0)
    lbl = Gtk.Label(label=text, xalign=0)
    lbl.set_line_wrap(True)
    lbl.set_max_width_chars(60)
    row.pack_start(lbl, True, True, 0)
    dlg.content.pack_start(row, True, True, 0)

    bbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
    bbox.set_halign(Gtk.Align.CENTER)
    for i, name in enumerate(buttons):
        b = make_button(name, lambda i=i: dlg.finish(i), default=(i == default))
        bbox.pack_start(b, False, False, 0)
        if i == default:
            dlg.set_default(b)
            GLib.idle_add(b.grab_focus)
    dlg.content.pack_start(bbox, False, False, 4)
    res = dlg.run()
    dlg.destroy()
    if res == Gtk.ResponseType.CANCEL:
        return -1
    return res
