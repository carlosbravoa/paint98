"""The classic dialogs: Attributes, Flip and Rotate, Stretch and Skew, Custom Zoom,
Edit Colors, About and Help."""

import colorsys

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gdk, GLib, Gtk  # noqa: E402

from . import pixmaps, win98  # noqa: E402
from .win98 import Win98Dialog, make_button  # noqa: E402

OK = Gtk.ResponseType.OK
CANCEL = Gtk.ResponseType.CANCEL


def group(title, child):
    f = Gtk.Frame(label=title)
    f.get_style_context().add_class("win98-group")
    child.set_border_width(8)
    f.add(child)
    return f


def radio_row(labels, orientation=Gtk.Orientation.VERTICAL, spacing=4):
    box = Gtk.Box(orientation=orientation, spacing=spacing)
    buttons = []
    first = None
    for text in labels:
        r = Gtk.RadioButton.new_with_mnemonic_from_widget(first, text)
        first = first or r
        buttons.append(r)
        box.pack_start(r, False, False, 0)
    return box, buttons


def side_buttons(dlg, extra=()):
    col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
    ok = make_button("OK", lambda: dlg.finish(OK), default=True)
    col.pack_start(ok, False, False, 0)
    col.pack_start(make_button("Cancel", lambda: dlg.finish(CANCEL)), False, False, 0)
    for label, cb in extra:
        col.pack_start(make_button(label, cb), False, False, 0)
    dlg.set_default(ok)
    return col


def number_entry(value, width=5):
    e = Gtk.Entry()
    e.set_width_chars(width)
    e.set_max_width_chars(width)
    e.set_text(str(value))
    e.set_activates_default(True)
    return e


def entry_int(e, default):
    try:
        return int(float(e.get_text().strip()))
    except (ValueError, OverflowError):
        return default


class AttributesDialog(Win98Dialog):
    UNITS = {"in": 96.0, "cm": 96.0 / 2.54, "px": 1.0}

    def __init__(self, parent, width, height, saved_info=None, colors=True):
        super().__init__(parent, "Attributes")
        self.px = (width, height)
        outer = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        left = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        last, size = saved_info or ("Not Available", "Not Available")
        info = Gtk.Grid(column_spacing=8, row_spacing=2)
        info.attach(Gtk.Label(label="File last saved:", xalign=0), 0, 0, 1, 1)
        info.attach(Gtk.Label(label=last, xalign=0), 1, 0, 1, 1)
        info.attach(Gtk.Label(label="Size on disk:", xalign=0), 0, 1, 1, 1)
        info.attach(Gtk.Label(label=size, xalign=0), 1, 1, 1, 1)
        left.pack_start(info, False, False, 0)

        dims = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self.w_entry = number_entry(width)
        self.h_entry = number_entry(height)
        lw = Gtk.Label.new_with_mnemonic("_Width:")
        lw.set_mnemonic_widget(self.w_entry)
        lh = Gtk.Label.new_with_mnemonic("_Height:")
        lh.set_mnemonic_widget(self.h_entry)
        for wdg in (lw, self.w_entry, lh, self.h_entry):
            dims.pack_start(wdg, False, False, 0)
        left.pack_start(dims, False, False, 4)

        ubox, self.unit_radios = radio_row(["_Inches", "C_m", "_Pels"], Gtk.Orientation.HORIZONTAL, 14)
        self.unit_radios[2].set_active(True)
        self.unit = "px"
        for r, u in zip(self.unit_radios, ("in", "cm", "px")):
            r.connect("toggled", self.on_unit, u)
        left.pack_start(group("Units", ubox), False, False, 0)

        cbox, self.color_radios = radio_row(["_Black and white", "Co_lors"], Gtk.Orientation.HORIZONTAL, 14)
        self.color_radios[1 if colors else 0].set_active(True)
        left.pack_start(group("Colors", cbox), False, False, 0)

        outer.pack_start(left, True, True, 0)
        outer.pack_start(side_buttons(self, [("_Default", self.on_default)]), False, False, 0)
        self.content.pack_start(outer, True, True, 0)

    def _read_px(self):
        f = self.UNITS[self.unit]
        try:
            w = float(self.w_entry.get_text()) * f
            h = float(self.h_entry.get_text()) * f
            return max(1, round(w)), max(1, round(h))
        except (ValueError, OverflowError):
            return self.px

    def _show(self):
        f = self.UNITS[self.unit]
        if self.unit == "px":
            self.w_entry.set_text(str(self.px[0]))
            self.h_entry.set_text(str(self.px[1]))
        else:
            self.w_entry.set_text("%.2f" % (self.px[0] / f))
            self.h_entry.set_text("%.2f" % (self.px[1] / f))

    def on_unit(self, radio, unit):
        if not radio.get_active():
            return
        self.px = self._read_px()
        self.unit = unit
        self._show()

    def on_default(self):
        self.px = (640, 480)
        self._show()

    def result(self):
        return self._read_px() + (self.color_radios[1].get_active(),)


class FlipRotateDialog(Win98Dialog):
    def __init__(self, parent):
        super().__init__(parent, "Flip and Rotate")
        outer = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        box, self.radios = radio_row(["_Flip horizontal", "Flip _vertical", "_Rotate by angle"])
        angles, self.angle_radios = radio_row(["_90°", "_180°", "_270°"])
        angles.set_margin_start(22)
        box.pack_start(angles, False, False, 0)
        self.radios[0].set_active(True)
        self.radios[2].connect("toggled", self._sync)
        self._sync()
        outer.pack_start(group("Flip or rotate", box), True, True, 0)
        outer.pack_start(side_buttons(self), False, False, 0)
        self.content.pack_start(outer, True, True, 0)

    def _sync(self, *a):
        on = self.radios[2].get_active()
        for r in self.angle_radios:
            r.set_sensitive(on)

    def result(self):
        if self.radios[0].get_active():
            return ("flip", True)
        if self.radios[1].get_active():
            return ("flip", False)
        for r, a in zip(self.angle_radios, (90, 180, 270)):
            if r.get_active():
                return ("rotate", a)


def _stretch_icon(kind):
    """Small illustrative glyphs next to the stretch/skew entries."""
    da = Gtk.DrawingArea()
    da.set_size_request(32, 24)

    def draw(w, cr):
        cr.set_source_rgb(0, 0, 0)
        cr.set_line_width(1)
        if kind == "sh":
            cr.rectangle(4.5, 6.5, 8, 10)
            cr.stroke()
            cr.rectangle(16.5, 6.5, 13, 10)
        elif kind == "sv":
            cr.rectangle(4.5, 9.5, 10, 7)
            cr.stroke()
            cr.rectangle(18.5, 3.5, 10, 13)
        elif kind == "kh":
            cr.rectangle(4.5, 6.5, 8, 10)
            cr.stroke()
            cr.move_to(18.5, 16.5)
            cr.line_to(26.5, 16.5)
            cr.line_to(30.5, 6.5)
            cr.line_to(22.5, 6.5)
            cr.close_path()
        else:
            cr.rectangle(4.5, 6.5, 8, 10)
            cr.stroke()
            cr.move_to(18.5, 9.5)
            cr.line_to(26.5, 5.5)
            cr.line_to(26.5, 15.5)
            cr.line_to(18.5, 19.5)
            cr.close_path()
        cr.stroke()
        return True

    da.connect("draw", draw)
    return da


class StretchSkewDialog(Win98Dialog):
    def __init__(self, parent):
        super().__init__(parent, "Stretch and Skew")
        outer = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        left = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)

        def rows(spec):
            g = Gtk.Grid(column_spacing=8, row_spacing=6)
            entries = []
            for i, (icon, label, value, unit) in enumerate(spec):
                g.attach(_stretch_icon(icon), 0, i, 1, 1)
                lbl = Gtk.Label.new_with_mnemonic(label)
                lbl.set_xalign(0)
                e = number_entry(value, 4)
                lbl.set_mnemonic_widget(e)
                g.attach(lbl, 1, i, 1, 1)
                g.attach(e, 2, i, 1, 1)
                g.attach(Gtk.Label(label=unit, xalign=0), 3, i, 1, 1)
                entries.append(e)
            return g, entries

        g1, self.stretch = rows([("sh", "_Horizontal:", 100, "%"), ("sv", "_Vertical:", 100, "%")])
        g2, self.skew = rows([("kh", "H_orizontal:", 0, "Degrees"), ("kv", "V_ertical:", 0, "Degrees")])
        left.pack_start(group("Stretch", g1), False, False, 0)
        left.pack_start(group("Skew", g2), False, False, 0)
        outer.pack_start(left, True, True, 0)
        outer.pack_start(side_buttons(self), False, False, 0)
        self.content.pack_start(outer, True, True, 0)

    def result(self):
        sh = max(1, min(500, entry_int(self.stretch[0], 100)))
        sv = max(1, min(500, entry_int(self.stretch[1], 100)))
        kh = max(-89, min(89, entry_int(self.skew[0], 0)))
        kv = max(-89, min(89, entry_int(self.skew[1], 0)))
        return sh, sv, kh, kv


class CustomZoomDialog(Win98Dialog):
    LEVELS = [1, 2, 4, 6, 8]

    def __init__(self, parent, current):
        super().__init__(parent, "Custom Zoom")
        outer = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        left = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        left.pack_start(Gtk.Label(label="Current zoom:    %d%%" % (current * 100), xalign=0), False, False, 0)
        grid = Gtk.Grid(column_spacing=16, row_spacing=4)
        first = None
        self.radios = []
        for i, lv in enumerate(self.LEVELS):
            r = Gtk.RadioButton.new_with_mnemonic_from_widget(first, "_%d%%" % (lv * 100))
            first = first or r
            self.radios.append(r)
            grid.attach(r, i % 3, i // 3, 1, 1)
            if lv == current:
                r.set_active(True)
        left.pack_start(group("Zoom to", grid), False, False, 0)
        outer.pack_start(left, True, True, 0)
        outer.pack_start(side_buttons(self), False, False, 0)
        self.content.pack_start(outer, True, True, 0)

    def result(self):
        for r, lv in zip(self.radios, self.LEVELS):
            if r.get_active():
                return lv
        return 1


# ---------------------------------------------------------------------------
# Edit Colors (the classic colour chooser)
# ---------------------------------------------------------------------------

BASIC_COLORS = [
    "FF8080", "FFFF80", "80FF80", "00FF80", "80FFFF", "0080FF", "FF80C0", "FF80FF",
    "FF0000", "FFFF00", "80FF00", "00FF40", "00FFFF", "0080C0", "8080C0", "FF00FF",
    "804040", "FF8040", "00FF00", "008080", "004080", "8080FF", "800040", "FF0080",
    "800000", "FF8000", "008000", "008040", "0000FF", "0000A0", "800080", "8000FF",
    "400000", "804000", "004000", "004040", "000080", "000040", "400040", "400080",
    "000000", "808000", "808040", "808080", "408080", "C0C0C0", "400040", "FFFFFF",
]
def _hex(h):
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


def parse_hex(text):
    """'#FF8040', 'ff8040', '#f84' -> (r, g, b); None if not a colour."""
    t = text.strip().lstrip("#")
    if len(t) == 3:
        t = "".join(c * 2 for c in t)
    if len(t) != 6:
        return None
    try:
        v = int(t, 16)
    except ValueError:
        return None
    return ((v >> 16) & 255, (v >> 8) & 255, v & 255)


def rgb_to_hsl240(rgb):
    h, l, s = colorsys.rgb_to_hls(*(c / 255 for c in rgb))
    return round(h * 239), round(s * 240), round(l * 240)


def hsl240_to_rgb(h, s, l):
    r, g, b = colorsys.hls_to_rgb(h / 239, l / 240, s / 240)
    return (round(r * 255), round(g * 255), round(b * 255))


class SwatchGrid(Gtk.DrawingArea):
    CW, CH = 21, 17  # cell size including spacing

    def __init__(self, colors, cols, on_pick):
        super().__init__()
        self.colors = colors
        self.cols = cols
        self.rows = (len(colors) + cols - 1) // cols
        self.selected = None
        self.on_pick = on_pick
        self.set_size_request(cols * self.CW, self.rows * self.CH)
        self.add_events(Gdk.EventMask.BUTTON_PRESS_MASK)
        self.connect("draw", self.draw)
        self.connect("button-press-event", self.press)

    def draw(self, w, cr):
        for i, c in enumerate(self.colors):
            r, col = divmod(i, self.cols)
            x, y = col * self.CW + 2, r * self.CH + 2
            if i == self.selected:
                cr.set_source_rgb(0, 0, 0)
                cr.rectangle(x - 2, y - 2, 18 + 4, 13 + 4)
                cr.fill()
                cr.set_source_rgb(*win98.FACE)
                cr.rectangle(x - 1, y - 1, 18 + 2, 13 + 2)
                cr.fill()
            win98.sunken_field(cr, x, y, 18, 13, tuple(v / 255 for v in c))
        return True

    def press(self, w, ev):
        col = int(ev.x // self.CW)
        row = int(ev.y // self.CH)
        i = row * self.cols + col
        if 0 <= col < self.cols and 0 <= i < len(self.colors):
            self.selected = i
            self.queue_draw()
            self.on_pick(self, i)
        return True


class EditColorsDialog(Win98Dialog):
    SPEC_W, SPEC_H = 175, 187

    def __init__(self, parent, color, custom=None, start_index=0):
        """custom: the main window's custom palette (28 colours). Colours
        added here are kept in self.custom; self.custom_changed tells the
        caller to apply them."""
        super().__init__(parent, "Edit Colors")
        self.color = tuple(color)
        self.custom = [tuple(c) for c in (custom or [(255, 255, 255)] * 28)]
        self.custom_changed = False
        self.h, self.s, self.l = rgb_to_hsl240(self.color)
        self.basic = [_hex(h) for h in BASIC_COLORS]
        self.custom_index = max(0, min(len(self.custom) - 1, start_index))
        self._spectrum = None

        outer = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        left = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        lbl = Gtk.Label.new_with_mnemonic("_Basic colors:")
        lbl.set_xalign(0)
        left.pack_start(lbl, False, False, 0)
        self.basic_grid = SwatchGrid(self.basic, 8, self.on_swatch)
        if self.color in self.basic:
            self.basic_grid.selected = self.basic.index(self.color)
        left.pack_start(self.basic_grid, False, False, 0)
        lbl = Gtk.Label.new_with_mnemonic("_Custom colors:")
        lbl.set_xalign(0)
        left.pack_start(lbl, False, False, 6)
        # Same 14 x 2 layout as the colour box's custom palette.
        self.custom_grid = SwatchGrid(self.custom, 14, self.on_swatch)
        self.custom_grid.selected = self.custom_index
        left.pack_start(self.custom_grid, False, False, 0)
        # Hex input: type or paste #RRGGBB (also RGB or #RGB).
        hex_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        lbl = Gtk.Label.new_with_mnemonic("He_x:")
        self.hex_entry = Gtk.Entry()
        self.hex_entry.set_width_chars(8)
        self.hex_entry.set_max_length(7)
        self.hex_entry.set_activates_default(True)
        lbl.set_mnemonic_widget(self.hex_entry)
        self.hex_entry.connect("changed", self.on_hex)
        self.hex_swatch = Gtk.DrawingArea()
        self.hex_swatch.set_size_request(30, 20)
        self.hex_swatch.connect("draw", self.draw_hex_swatch)
        hex_row.pack_start(lbl, False, False, 0)
        hex_row.pack_start(self.hex_entry, False, False, 0)
        hex_row.pack_start(self.hex_swatch, False, False, 0)
        left.pack_start(hex_row, False, False, 6)
        bb = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        ok = make_button("OK", lambda: self.finish(OK), default=True)
        bb.pack_start(ok, False, False, 0)
        bb.pack_start(make_button("Cancel", lambda: self.finish(CANCEL)), False, False, 0)
        self.set_default(ok)
        left.pack_start(bb, False, False, 0)
        outer.pack_start(left, False, False, 0)

        self.right = self._build_custom_panel()
        outer.pack_start(self.right, False, False, 0)
        self.content.pack_start(outer, True, True, 0)

    def _build_custom_panel(self):
        right = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        top = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self.spec = Gtk.DrawingArea()
        self.spec.set_size_request(self.SPEC_W + 4, self.SPEC_H + 4)
        self.spec.add_events(Gdk.EventMask.BUTTON_PRESS_MASK | Gdk.EventMask.BUTTON_MOTION_MASK)
        self.spec.connect("draw", self.draw_spectrum)
        self.spec.connect("button-press-event", self.spec_event)
        self.spec.connect("motion-notify-event", self.spec_event)
        top.pack_start(self.spec, False, False, 0)
        self.lum = Gtk.DrawingArea()
        self.lum.set_size_request(22, self.SPEC_H + 4)
        self.lum.add_events(Gdk.EventMask.BUTTON_PRESS_MASK | Gdk.EventMask.BUTTON_MOTION_MASK)
        self.lum.connect("draw", self.draw_lum)
        self.lum.connect("button-press-event", self.lum_event)
        self.lum.connect("motion-notify-event", self.lum_event)
        top.pack_start(self.lum, False, False, 0)
        right.pack_start(top, False, False, 0)

        mid = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        prev_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        self.preview = Gtk.DrawingArea()
        self.preview.set_size_request(60, 40)
        self.preview.connect("draw", self.draw_preview)
        prev_box.pack_start(self.preview, False, False, 0)
        prev_box.pack_start(Gtk.Label(label="Color|Solid"), False, False, 0)
        mid.pack_start(prev_box, False, False, 0)

        grid = Gtk.Grid(column_spacing=4, row_spacing=4)
        self.entries = {}
        for i, (key, label) in enumerate((("h", "Hu_e:"), ("s", "_Sat:"), ("l", "_Lum:"))):
            self._num(grid, key, label, 0, i)
        for i, (key, label) in enumerate((("r", "_Red:"), ("g", "_Green:"), ("b", "Bl_ue:"))):
            self._num(grid, key, label, 2, i)
        mid.pack_start(grid, False, False, 0)
        right.pack_start(mid, False, False, 0)
        right.pack_start(make_button("_Add to Custom Colors", self.on_add), False, False, 0)
        self._sync_entries()
        return right

    def _num(self, grid, key, label, col, row):
        lbl = Gtk.Label.new_with_mnemonic(label)
        lbl.set_xalign(1)
        e = number_entry(0, 3)
        lbl.set_mnemonic_widget(e)
        e.connect("changed", self.on_entry, key)
        grid.attach(lbl, col, row, 1, 1)
        grid.attach(e, col + 1, row, 1, 1)
        self.entries[key] = e

    # -- state sync -----------------------------------------------------------
    _syncing = False

    def _set_rgb(self, rgb, from_hsl=False):
        self.color = tuple(rgb)
        if not from_hsl:
            self.h, self.s, self.l = rgb_to_hsl240(self.color)
        self._sync_entries()
        for w in (self.spec, self.lum, self.preview):
            w.queue_draw()

    def _sync_entries(self):
        self._syncing = True
        vals = {"h": self.h, "s": self.s, "l": self.l,
                "r": self.color[0], "g": self.color[1], "b": self.color[2]}
        for k, e in self.entries.items():
            if e.get_text() != str(vals[k]):
                e.set_text(str(vals[k]))
        hex_text = "#%02X%02X%02X" % tuple(self.color)
        if self.hex_entry.get_text().upper() != hex_text and parse_hex(self.hex_entry.get_text()) != self.color:
            self.hex_entry.set_text(hex_text)
        self.hex_swatch.queue_draw()
        self._syncing = False

    def on_hex(self, entry):
        if self._syncing:
            return
        rgb = parse_hex(entry.get_text())
        if rgb is not None and rgb != self.color:
            # _sync_entries leaves the hex text alone while it already
            # spells this colour, so typing isn't interrupted.
            self._set_rgb(rgb)

    def draw_hex_swatch(self, w, cr):
        width, height = w.get_allocated_width(), w.get_allocated_height()
        win98.sunken_field(cr, 0, 0, width, height, tuple(c / 255 for c in self.color))
        return True

    def on_entry(self, e, key):
        if self._syncing:
            return
        v = entry_int(e, 0)
        if key in "hsl":
            lim = 239 if key == "h" else 240
            setattr(self, key, max(0, min(lim, v)))
            self._set_rgb(hsl240_to_rgb(self.h, self.s, self.l), from_hsl=True)
        else:
            rgb = list(self.color)
            rgb["rgb".index(key)] = max(0, min(255, v))
            self._set_rgb(rgb)

    def on_swatch(self, grid, i):
        other = self.custom_grid if grid is self.basic_grid else self.basic_grid
        other.selected = None
        other.queue_draw()
        if grid is self.custom_grid:
            self.custom_index = i
        self._set_rgb(grid.colors[i])

    def on_add(self):
        """Put the colour in the selected custom box and move to the next."""
        self.custom[self.custom_index] = self.color
        self.custom_changed = True
        self.custom_index = (self.custom_index + 1) % len(self.custom)
        self.custom_grid.selected = self.custom_index
        self.basic_grid.selected = None
        self.basic_grid.queue_draw()
        self.custom_grid.queue_draw()

    # -- drawing --------------------------------------------------------------
    def draw_spectrum(self, w, cr):
        import cairo
        if self._spectrum is None:
            surf = cairo.ImageSurface(cairo.FORMAT_RGB24, self.SPEC_W, self.SPEC_H)
            data = surf.get_data()
            stride = surf.get_stride()
            for y in range(self.SPEC_H):
                s = 240 - y * 240 / (self.SPEC_H - 1)
                for x in range(self.SPEC_W):
                    h = x * 239 / (self.SPEC_W - 1)
                    r, g, b = hsl240_to_rgb(h, s, 120)
                    o = y * stride + x * 4
                    data[o] = b
                    data[o + 1] = g
                    data[o + 2] = r
            surf.mark_dirty()
            self._spectrum = surf
        win98.sunken_field(cr, 0, 0, self.SPEC_W + 4, self.SPEC_H + 4)
        cr.set_source_surface(self._spectrum, 2, 2)
        cr.paint()
        # Cross-hair cursor
        cx = 2 + round(self.h * (self.SPEC_W - 1) / 239)
        cy = 2 + round((240 - self.s) * (self.SPEC_H - 1) / 240)
        cr.set_source_rgb(0, 0, 0)
        for dx, dy, ww, hh in ((-9, -1, 6, 3), (4, -1, 6, 3), (-1, -9, 3, 6), (-1, 4, 3, 6)):
            cr.rectangle(cx + dx, cy + dy, ww, hh)
        cr.fill()
        return True

    def draw_lum(self, w, cr):
        h = self.SPEC_H
        for y in range(h):
            l = 240 - y * 240 / (h - 1)
            r, g, b = hsl240_to_rgb(self.h, self.s, l)
            cr.set_source_rgb(r / 255, g / 255, b / 255)
            cr.rectangle(2, y + 2, 10, 1)
            cr.fill()
        ay = 2 + round((240 - self.l) * (h - 1) / 240)
        cr.set_source_rgb(0, 0, 0)
        for i in range(5):
            cr.rectangle(14 + i, ay - (4 - i), 1, (4 - i) * 2 + 1)
        cr.fill()
        return True

    def draw_preview(self, w, cr):
        win98.sunken_field(cr, 0, 0, 60, 40)
        cr.set_source_rgb(*(c / 255 for c in self.color))
        cr.rectangle(2, 2, 56, 36)
        cr.fill()
        return True

    def spec_event(self, w, ev):
        x = max(0, min(self.SPEC_W - 1, ev.x - 2))
        y = max(0, min(self.SPEC_H - 1, ev.y - 2))
        self.h = round(x * 239 / (self.SPEC_W - 1))
        self.s = round(240 - y * 240 / (self.SPEC_H - 1))
        if self.l in (0, 240):
            self.l = 120
        self._set_rgb(hsl240_to_rgb(self.h, self.s, self.l), from_hsl=True)
        return True

    def lum_event(self, w, ev):
        y = max(0, min(self.SPEC_H - 1, ev.y - 2))
        self.l = round(240 - y * 240 / (self.SPEC_H - 1))
        self._set_rgb(hsl240_to_rgb(self.h, self.s, self.l), from_hsl=True)
        return True


# ---------------------------------------------------------------------------
# About and Help
# ---------------------------------------------------------------------------

def about(parent, version):
    dlg = Win98Dialog(parent, "About Paint98", help_button=False)
    row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=16)
    icon = Gtk.DrawingArea()
    icon.set_size_request(32, 32)

    def draw_icon(w, cr):
        import cairo
        cr.scale(2, 2)
        cr.set_source_surface(pixmaps.get("APP_ICON"), 0, 0)
        cr.get_source().set_filter(cairo.FILTER_NEAREST)
        cr.paint()
        return True

    icon.connect("draw", draw_icon)
    row.pack_start(icon, False, False, 0)
    text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
    for line in ("Paint98", "Version %s" % version,
                 "A classic-style paint program for the GNOME desktop.", "",
                 "Made for people who miss the old days.", "",
                 "Released under the MIT License."):
        text.pack_start(Gtk.Label(label=line, xalign=0), False, False, 0)
    sep = Gtk.Box()
    sep.get_style_context().add_class("win98-separator")
    text.pack_start(sep, False, False, 6)
    mem = Gtk.Label(label="Physical memory available to Paint98:   plenty", xalign=0)
    text.pack_start(mem, False, False, 0)
    row.pack_start(text, True, True, 0)
    col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
    ok = make_button("OK", lambda: dlg.finish(OK), default=True)
    col.pack_start(ok, False, False, 0)
    row.pack_start(col, False, False, 0)
    dlg.content.pack_start(row, True, True, 6)
    dlg.set_default(ok)
    GLib.idle_add(ok.grab_focus)
    dlg.run()
    dlg.destroy()


HELP_TOPICS = [
    ("Paint98 overview",
     "Paint98 is a drawing tool you can use to create simple or elaborate drawings. "
     "These drawings can be either black-and-white or color, and can be saved as "
     "bitmap or PNG files.\n\nYou can also use Paint98 to view and edit pictures, "
     "and to make one of your pictures the desktop wallpaper."),
    ("Drawing lines and shapes",
     "Click the Line, Curve, Rectangle, Polygon, Ellipse or Rounded Rectangle tool, "
     "choose a line width or fill style in the box below the tools, then drag in the "
     "picture. Use the left mouse button for the foreground color and the right mouse "
     "button for the background color. Hold down SHIFT to draw perfect squares, "
     "circles and straight lines at 45-degree angles.\n\nCurve: drag a straight line, "
     "then click (or drag) twice to bend it.\nPolygon: drag the first side, then click "
     "each further corner. Double-click to finish."),
    ("Working with selections",
     "Use Select or Free-Form Select, then drag the selection to move it. Hold down CTRL "
     "while dragging to move a copy; hold down SHIFT to leave a trail. Drag a handle to "
     "stretch the selection. Choose the transparent option to let the background color "
     "show through."),
    ("Working with colors",
     "Left-click a color in the color box to set the foreground color and right-click to "
     "set the background color. Double-click a color, or click Edit Colors on the Options "
     "menu, to change it. Use Pick Color to take a color from the picture."),
    ("Adding text",
     "Click the Text tool, drag a text frame and type. Use the Fonts toolbar to change the "
     "font, size and style. Click outside the frame to place the text on the picture."),
    ("Setting the wallpaper",
     "On the File menu click Set As Wallpaper (Tiled) or Set As Wallpaper (Centered) to "
     "use the current picture as your GNOME desktop background. Save the picture first."),
    ("Keyboard shortcuts",
     "CTRL+N New      CTRL+O Open      CTRL+S Save\nCTRL+Z Undo     F4 Repeat\n"
     "CTRL+X Cut      CTRL+C Copy     CTRL+V Paste    DEL Clear Selection\n"
     "CTRL+L Select All\nCTRL+R Flip/Rotate   CTRL+W Stretch/Skew   CTRL+I Invert Colors\n"
     "CTRL+SHIFT+F Recolor Selection\n"
     "CTRL+E Attributes   CTRL+SHIFT+N Clear Image\nCTRL+T Tool Box   CTRL+A Color Box\n"
     "CTRL+PAGE UP Normal Size   CTRL+PAGE DOWN Large Size   CTRL+G Show Grid\n"
     "CTRL+F View Bitmap   CTRL+B Sticker Book   CTRL+SHIFT+R Replay"),
]


def help_topics(parent):
    dlg = Win98Dialog(parent, "Paint98 Help", help_button=False)
    dlg.set_resizable(True)
    dlg.set_modal(False)
    row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
    listbox = Gtk.ListBox()
    listbox.get_style_context().add_class("win98-list")
    for title, _ in HELP_TOPICS:
        lbl = Gtk.Label(label=title, xalign=0)
        lbl.set_margin_start(4)
        lbl.set_margin_end(4)
        listbox.add(lbl)
    left = Gtk.ScrolledWindow()
    left.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
    left.set_overlay_scrolling(False)
    left.get_style_context().add_class("win98-field")
    left.set_size_request(190, 300)
    left.add(listbox)
    row.pack_start(left, False, False, 0)
    body = Gtk.Label(xalign=0, yalign=0)
    body.set_line_wrap(True)
    body.set_max_width_chars(48)
    body.set_selectable(False)
    right = Gtk.ScrolledWindow()
    right.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
    right.set_overlay_scrolling(False)
    right.get_style_context().add_class("win98-field")
    right.get_style_context().add_class("white")
    right.set_size_request(360, 300)
    vb = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
    vb.set_border_width(8)
    title = Gtk.Label(xalign=0)
    vb.pack_start(title, False, False, 4)
    vb.pack_start(body, False, False, 0)
    right.add(vb)
    row.pack_start(right, True, True, 0)

    def select(lb, r):
        if r is None:
            return
        t, txt = HELP_TOPICS[r.get_index()]
        title.set_markup("<b>%s</b>" % GLib.markup_escape_text(t))
        body.set_text(txt)

    listbox.connect("row-selected", select)
    listbox.select_row(listbox.get_row_at_index(0))
    dlg.content.pack_start(row, True, True, 0)
    bb = Gtk.Box()
    bb.set_halign(Gtk.Align.END)
    bb.pack_start(make_button("Close", lambda: dlg.finish(OK)), False, False, 0)
    dlg.content.pack_start(bb, False, False, 0)
    dlg.connect("unmap", lambda *a: GLib.idle_add(dlg.destroy))
    dlg.show_all()
    dlg.present()
    dlg.finish = lambda r: dlg.hide()
