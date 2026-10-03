"""The Sticker Book: a classic tool window to browse and pick stickers."""

import cairo
import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gdk, GObject, Gtk  # noqa: E402

from . import stickers, win98  # noqa: E402
from .win98 import Win98Window, make_button, message_box  # noqa: E402

CELL = 44
COLS = 7


class StickerGrid(Gtk.DrawingArea):
    __gsignals__ = {
        "picked": (GObject.SignalFlags.RUN_FIRST, None, (str,)),
        "hovered": (GObject.SignalFlags.RUN_FIRST, None, (str,)),
    }

    def __init__(self):
        super().__init__()
        self.ids = []
        self.selected = None
        self.hot = None
        self.add_events(Gdk.EventMask.BUTTON_PRESS_MASK | Gdk.EventMask.POINTER_MOTION_MASK
                        | Gdk.EventMask.LEAVE_NOTIFY_MASK)
        self.connect("draw", self.on_draw)
        self.connect("button-press-event", self.on_press)
        self.connect("motion-notify-event", self.on_motion)
        self.connect("leave-notify-event", self.on_leave)

    def set_ids(self, ids, selected=None):
        self.ids = list(ids)
        self.selected = selected
        rows = max(1, (len(self.ids) + COLS - 1) // COLS)
        self.set_size_request(COLS * CELL, rows * CELL)
        self.queue_draw()

    def index_at(self, x, y):
        col, row = int(x // CELL), int(y // CELL)
        i = row * COLS + col
        if 0 <= col < COLS and 0 <= i < len(self.ids):
            return i
        return None

    def on_press(self, w, ev):
        i = self.index_at(ev.x, ev.y)
        if i is not None and ev.button == 1:
            self.selected = self.ids[i]
            self.queue_draw()
            self.emit("picked", self.selected)
        return True

    def on_motion(self, w, ev):
        i = self.index_at(ev.x, ev.y)
        hot = self.ids[i] if i is not None else None
        if hot != self.hot:
            self.hot = hot
            self.queue_draw()
            self.emit("hovered", hot or "")
        return True

    def on_leave(self, w, ev):
        self.hot = None
        self.queue_draw()
        self.emit("hovered", "")
        return False

    def on_draw(self, w, cr):
        cr.set_source_rgb(1, 1, 1)
        cr.paint()
        for i, sid in enumerate(self.ids):
            r, c = divmod(i, COLS)
            x, y = c * CELL, r * CELL
            if sid == self.selected:
                cr.set_source_rgb(0, 0, 0.5)
                cr.rectangle(x + 1, y + 1, CELL - 2, CELL - 2)
                cr.fill()
            elif sid == self.hot:
                win98.raised(cr, x + 1, y + 1, CELL - 2, CELL - 2, fill=False)
            img = stickers.render(sid, CELL - 10)
            cr.set_source_surface(img, x + 5, y + 5)
            cr.paint()
        return True


class StickerBook(Win98Window):
    """Non-modal tool window. `get_selection_surface` returns the current
    selection's pixels (or None) for "Add Selection"."""

    def __init__(self, parent, state, get_selection_surface):
        super().__init__("Sticker Book", buttons=("close",), icon=False)
        self.set_transient_for(parent)
        self.set_destroy_with_parent(True)
        self.set_type_hint(Gdk.WindowTypeHint.UTILITY)
        self.set_skip_taskbar_hint(True)
        self.state = state
        self.get_selection_surface = get_selection_surface
        self.cats = []

        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        row.set_border_width(8)
        self.list = Gtk.ListBox()
        self.list.connect("row-selected", self.on_category)
        left = Gtk.ScrolledWindow()
        left.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        left.set_overlay_scrolling(False)
        left.get_style_context().add_class("win98-field")
        left.set_size_request(110, -1)
        left.add(self.list)
        row.pack_start(left, False, False, 0)

        self.grid = StickerGrid()
        self.grid.connect("picked", lambda g, sid: self.state.choose_sticker(sid))
        self.grid.connect("picked", lambda g, sid: self.sync_buttons())
        self.grid.connect("hovered", self.on_hover)
        right = Gtk.ScrolledWindow()
        right.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        right.set_overlay_scrolling(False)
        right.get_style_context().add_class("win98-field")
        right.get_style_context().add_class("white")
        right.set_size_request(COLS * CELL + 4 + 16, 5 * CELL + 4)
        right.add(self.grid)
        row.pack_start(right, True, True, 0)
        self.body.pack_start(row, True, True, 0)

        bottom = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        bottom.set_border_width(8)
        bottom.set_margin_top(0)
        self.info = Gtk.Label(xalign=0)
        bottom.pack_start(self.info, True, True, 0)
        self.add_btn = make_button("_Add Selection", self.on_add)
        self.add_btn.set_tooltip_text("Make a sticker from the current selection "
                                      "(tip: use the Magic Wand or transparent mode)")
        bottom.pack_start(self.add_btn, False, False, 0)
        self.del_btn = make_button("_Delete", self.on_delete)
        bottom.pack_start(self.del_btn, False, False, 0)
        bottom.pack_start(make_button("_Close", self.close), False, False, 0)
        self.body.pack_start(bottom, False, False, 0)

        self.connect("delete-event", lambda *a: self.hide() or True)
        self.reload()

    def request_close(self):
        self.hide()

    def close(self):
        self.hide()

    def reload(self, select_title=None):
        current = select_title or self.current_title()
        self.cats = stickers.categories()
        for child in self.list.get_children():
            self.list.remove(child)
        for title, _ in self.cats:
            lbl = Gtk.Label(label=title, xalign=0)
            lbl.set_margin_start(4)
            lbl.set_margin_end(4)
            self.list.add(lbl)
        self.list.show_all()
        titles = [t for t, _ in self.cats]
        idx = titles.index(current) if current in titles else 0
        self.list.select_row(self.list.get_row_at_index(idx))

    def current_title(self):
        row = self.list.get_selected_row() if self.cats else None
        return self.cats[row.get_index()][0] if row is not None else None

    def on_category(self, lb, row):
        if row is None:
            return
        title, ids = self.cats[row.get_index()]
        self.grid.set_ids(ids, self.state.sticker)
        if title == "My Stickers" and not ids:
            self.info.set_text("Select something, then click Add Selection.")
        else:
            self.info.set_text("%d stickers" % len(ids))
        self.sync_buttons()

    def on_hover(self, grid, sid):
        if sid:
            self.info.set_text(stickers.name(sid))
        else:
            title = self.current_title()
            ids = dict(self.cats).get(title, [])
            self.info.set_text("%d stickers" % len(ids))

    def sync_buttons(self, *a):
        self.add_btn.set_sensitive(self.get_selection_surface() is not None)
        self.del_btn.set_sensitive((self.grid.selected or "").startswith("user:")
                                   and self.current_title() == "My Stickers")

    def on_add(self):
        surf = self.get_selection_surface()
        if surf is None:
            return
        try:
            sid = stickers.save_user_sticker(surf)
        except (OSError, cairo.Error) as e:
            message_box(self, "Sticker Book", "Paint98 cannot save the sticker.\n\n%s" % e, ("OK",))
            return
        if sid is None:
            message_box(self, "Sticker Book", "The selection is empty.", ("OK",), icon="info")
            return
        self.reload("My Stickers")
        self.state.choose_sticker(sid)
        self.grid.selected = sid
        self.grid.queue_draw()
        self.sync_buttons()

    def on_delete(self):
        sid = self.grid.selected
        if not sid or not sid.startswith("user:"):
            return
        if message_box(self, "Sticker Book", "Delete this sticker?", ("Yes", "No"), default=1) != 0:
            return
        stickers.delete_user_sticker(sid)
        st = self.state
        st.sticker_recent = [s for s in st.sticker_recent if s != sid]
        if st.sticker == sid:
            st.sticker = stickers.DEFAULT
        st.emit("options-changed")
        self.reload("My Stickers")
