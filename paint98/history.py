"""The History window: every step of the picture, click one to go back to it."""

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gdk, GLib, Gtk  # noqa: E402

from . import pixmaps  # noqa: E402
from .state import TOOL_NAMES  # noqa: E402
from .win98 import Win98Window, make_button  # noqa: E402

# Step names that come from tools get the tool's icon.
_ICON_FOR = {name: tool for tool, name in TOOL_NAMES.items()}


class HistoryWindow(Win98Window):
    def __init__(self, main):
        super().__init__("History", buttons=("close",), icon=False)
        self.main = main
        self.set_transient_for(main)
        self.set_destroy_with_parent(True)
        self.set_type_hint(Gdk.WindowTypeHint.UTILITY)
        self.set_skip_taskbar_hint(True)
        self.set_default_size(220, 320)
        self._updating = False

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        box.set_border_width(8)
        self.list = Gtk.ListBox()
        self.list.set_activate_on_single_click(True)
        self.list.connect("row-activated", self.on_row)
        sw = Gtk.ScrolledWindow()
        sw.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        sw.set_overlay_scrolling(False)
        sw.get_style_context().add_class("win98-field")
        sw.get_style_context().add_class("white")
        sw.set_size_request(200, 260)
        sw.add(self.list)
        self.scroller = sw
        box.pack_start(sw, True, True, 0)
        bottom = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self.info = Gtk.Label(xalign=0)
        bottom.pack_start(self.info, True, True, 0)
        bottom.pack_end(make_button("_Close", self.request_close), False, False, 0)
        box.pack_start(bottom, False, False, 0)
        self.body.pack_start(box, True, True, 0)

        self.connect("delete-event", lambda *a: self.request_close() or True)
        main.doc.connect("state-changed", lambda *a: self.refresh())
        self.refresh()

    def request_close(self):
        self.hide()
        self.main.set_check("v_history", False)

    def refresh(self):
        if not self.get_visible() and self.list.get_children():
            return  # rebuilt when shown again
        names, current = self.main.doc.history()
        self._updating = True
        for child in self.list.get_children():
            self.list.remove(child)
        for i, name in enumerate(names):
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
            row.set_margin_start(2)
            icon = Gtk.DrawingArea()
            icon.set_size_request(16, 16)
            tool = _ICON_FOR.get(name)
            future = i > current
            if tool:
                icon.connect("draw", lambda w, cr, t=tool, f=future:
                             pixmaps.paint(cr, t, 0, 0, disabled=f) or True)
            row.pack_start(icon, False, False, 0)
            lbl = Gtk.Label(label=name, xalign=0)
            lbl.set_sensitive(not future)  # undone steps are greyed out
            row.pack_start(lbl, True, True, 0)
            self.list.add(row)
        self.list.show_all()
        row = self.list.get_row_at_index(current)
        self.list.select_row(row)
        undone = len(names) - 1 - current
        self.info.set_text("%d steps" % (len(names) - 1) + (", %d undone" % undone if undone else ""))
        self._updating = False
        GLib.idle_add(self._scroll_to, current)

    def _scroll_to(self, index):
        row = self.list.get_row_at_index(index)
        if row is not None:
            adj = self.scroller.get_vadjustment()
            a = row.get_allocation()
            if a.y < adj.get_value() or a.y + a.height > adj.get_value() + adj.get_page_size():
                adj.set_value(max(0, a.y - adj.get_page_size() / 2))
        return False

    def on_row(self, listbox, row):
        if not self._updating:
            self.main.jump_to_history(row.get_index())

    def show_window(self):
        self.show_all()
        self.refresh()
        self.present()
