"""The Fonts toolbar shown while editing text."""

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Pango", "1.0")
from gi.repository import Gdk, GLib, GObject, Gtk, Pango  # noqa: E402

SIZES = [8, 9, 10, 11, 12, 14, 16, 18, 20, 22, 24, 26, 28, 36, 48, 72]
PREFERRED = ["Arial", "Liberation Sans", "DejaVu Sans", "Sans"]
LIST_ROWS = 12


def latin_families(pango_context):
    """Font families that can draw basic Latin text, sorted by name.

    Script-only families (dozens of Noto variants, emoji fonts...) are left
    out so the list stays usable, like the original font box.
    """
    names = set()
    for fam in pango_context.list_families():
        faces = fam.list_faces()
        if not faces:
            continue
        desc = faces[0].describe()
        desc.set_size(12 * Pango.SCALE)
        font = pango_context.load_font(desc)
        if font is not None and all(font.has_char(c) for c in "Aaz09"):
            names.add(fam.get_name())
    return sorted(names, key=str.lower)


class DropDown(Gtk.EventBox):
    """A classic drop-down list: a white field with an arrow button that
    opens a fixed-height scrolling list underneath."""

    __gsignals__ = {
        "changed": (GObject.SignalFlags.RUN_FIRST, None, (str,)),
        "done": (GObject.SignalFlags.RUN_FIRST, None, ()),
    }

    def __init__(self, items, active, width, rows=LIST_ROWS):
        super().__init__()
        self.items = list(items)
        self.active = active
        self.rows = rows
        self.set_size_request(width, -1)
        field = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        field.get_style_context().add_class("dropdown-field")
        self.label = Gtk.Label(label=active, xalign=0)
        self.label.set_ellipsize(Pango.EllipsizeMode.END)
        field.pack_start(self.label, True, True, 0)
        arrow = Gtk.Box()
        arrow.get_style_context().add_class("dropdown-arrow")
        field.pack_start(arrow, False, False, 0)
        self.add(field)
        self.add_events(Gdk.EventMask.BUTTON_PRESS_MASK)
        self.connect("button-press-event", self.on_press)
        self.popover = None

    def build_popover(self):
        pop = Gtk.Popover.new(self)
        pop.set_position(Gtk.PositionType.BOTTOM)
        pop.get_style_context().add_class("dropdown-popup")
        pop.connect("closed", lambda *a: self.emit("done"))
        sw = Gtk.ScrolledWindow()
        sw.set_overlay_scrolling(False)
        sw.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.listbox = Gtk.ListBox()
        self.listbox.set_activate_on_single_click(True)
        for name in self.items:
            lbl = Gtk.Label(label=name, xalign=0)
            lbl.set_ellipsize(Pango.EllipsizeMode.END)
            self.listbox.add(lbl)
        self.listbox.connect("row-activated", self.on_row)
        sw.add(self.listbox)
        sw.show_all()
        row_h = max(16, self.listbox.get_row_at_index(0).get_preferred_height()[1]) if self.items else 16
        sw.set_size_request(self.get_allocated_width(), row_h * min(self.rows, max(1, len(self.items))) + 2)
        self.scroller = sw
        pop.add(sw)
        self.popover = pop

    def on_press(self, w, ev):
        if ev.button != 1 or ev.type != Gdk.EventType.BUTTON_PRESS:
            return True
        if self.popover is None:
            self.build_popover()
        if self.active in self.items:
            row = self.listbox.get_row_at_index(self.items.index(self.active))
            self.listbox.select_row(row)
        self.popover.popup()
        self.popover.show_all()
        if self.active in self.items:
            row = self.listbox.get_row_at_index(self.items.index(self.active))

            def scroll():
                adj = self.scroller.get_vadjustment()
                a = row.get_allocation()
                adj.set_value(max(0, a.y - adj.get_page_size() / 2 + a.height / 2))
                row.grab_focus()
                return False
            GLib.idle_add(scroll)
        return True

    def on_row(self, listbox, row):
        self.set_active(self.items[row.get_index()])
        self.popover.popdown()
        self.emit("changed", self.active)
        self.emit("done")

    def set_active(self, value):
        self.active = value
        self.label.set_text(value)


class TextToolbar(Gtk.Box):
    def __init__(self, state):
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        self.state = state
        self.get_style_context().add_class("fonts-toolbar")

        families = latin_families(self.get_pango_context())
        if state.font_family not in families:
            for name in PREFERRED:
                if name in families:
                    state.font_family = name
                    break
            else:
                state.font_family = families[0] if families else "Sans"

        self.family = DropDown(families, state.font_family, 170)
        self.family.connect("changed", lambda w, v: self.state.set_option("font_family", v))
        # Give the keyboard back to the text box after picking from a list.
        self.refocus = lambda: None
        self.family.connect("done", lambda *a: self.refocus())
        self.pack_start(self.family, False, False, 0)

        self.size = DropDown([str(s) for s in SIZES], str(state.font_size), 44)
        self.size.connect("changed", lambda w, v: self.state.set_option("font_size", int(v)))
        self.size.connect("done", lambda *a: self.refocus())
        self.pack_start(self.size, False, False, 0)

        self.toggles = {}
        for attr, markup in (("font_bold", "<b>B</b>"),
                             ("font_italic", "<i>I</i>"),
                             ("font_underline", "<u>U</u>")):
            b = Gtk.ToggleButton()
            lbl = Gtk.Label()
            lbl.set_markup(markup)
            b.add(lbl)
            b.get_style_context().add_class("toolbutton")
            b.set_can_focus(False)  # keep the caret in the text box
            b.set_active(getattr(state, attr))
            b.connect("toggled", self.on_toggle, attr)
            b.set_tooltip_text({"font_bold": "Bold", "font_italic": "Italic",
                                "font_underline": "Underline"}[attr])
            self.toggles[attr] = b
            self.pack_start(b, False, False, 0)

    def on_toggle(self, button, attr):
        self.state.set_option(attr, button.get_active())
