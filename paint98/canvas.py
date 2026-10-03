"""The drawing surface widget: zoom, handles, selection and event routing."""

import math

import cairo
import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gdk, GLib, GObject, Gtk  # noqa: E402

from . import imageops, pixmaps, symmetry, win98  # noqa: E402
from .selection import Selection  # noqa: E402
from .tools import TOOL_CLASSES  # noqa: E402

ORIGIN = 3   # gap between the workspace edge and the picture
HANDLE = 3   # size of the sizing handles
WORKSPACE = (0x80 / 255,) * 3
HANDLE_COLOR = (0, 0, 0x80 / 255)


_ants = None


def ants_pattern():
    """Alternating black/white pixels for selection outlines."""
    global _ants
    if _ants is None:
        s = cairo.ImageSurface(cairo.FORMAT_RGB24, 2, 2)
        c = cairo.Context(s)
        c.set_source_rgb(1, 1, 1)
        c.paint()
        c.set_source_rgb(0, 0, 0)
        c.rectangle(0, 0, 1, 1)
        c.rectangle(1, 1, 1, 1)
        c.fill()
        _ants = cairo.SurfacePattern(s)
        _ants.set_extend(cairo.EXTEND_REPEAT)
        _ants.set_filter(cairo.FILTER_NEAREST)
    return _ants


class Canvas(Gtk.DrawingArea):
    __gsignals__ = {
        "pointer-info": (GObject.SignalFlags.RUN_FIRST, None, (int, int, bool)),
        "size-info": (GObject.SignalFlags.RUN_FIRST, None, (int, int, bool)),
        "zoom-changed": (GObject.SignalFlags.RUN_FIRST, None, ()),
        "selection-changed": (GObject.SignalFlags.RUN_FIRST, None, ()),
        "text-box-changed": (GObject.SignalFlags.RUN_FIRST, None, ()),
        "context-menu": (GObject.SignalFlags.RUN_FIRST, None, ()),
        # The visible picture changed without the document changing
        # (shape previews, moving a selection).
        "picture-changed": (GObject.SignalFlags.RUN_FIRST, None, ()),
    }

    def __init__(self, state, doc):
        super().__init__()
        self.state = state
        self.doc = doc
        self.zoom = 1
        self.preview = None
        self._selection = None
        self.drag_button = 0
        self.resizing = None
        self.last_widget_pos = (0, 0)
        self.hadj = None
        self.vadj = None
        self._cursors = {}
        self._cursor_name = None
        self.tools = {name: cls(self) for name, cls in TOOL_CLASSES.items()}
        self.tool = self.tools[state.tool]

        self.set_can_focus(True)
        self.add_events(Gdk.EventMask.BUTTON_PRESS_MASK | Gdk.EventMask.BUTTON_RELEASE_MASK
                        | Gdk.EventMask.POINTER_MOTION_MASK | Gdk.EventMask.LEAVE_NOTIFY_MASK
                        | Gdk.EventMask.KEY_PRESS_MASK | Gdk.EventMask.FOCUS_CHANGE_MASK)
        self.connect("draw", self.on_draw)
        self.connect("button-press-event", self.on_press)
        self.connect("button-release-event", self.on_release)
        self.connect("motion-notify-event", self.on_motion)
        self.connect("leave-notify-event", self.on_leave)
        self.connect("realize", self.on_realize)
        self.connect("unrealize", self.on_unrealize)
        self.connect("focus-in-event", self.on_focus_in)
        self.connect("focus-out-event", self.on_focus_out)

        self.im = Gtk.IMMulticontext()
        self.im.connect("commit", self.on_im_commit)

        doc.connect("changed", lambda *a: self.queue_draw())
        doc.connect("size-changed", lambda *a: self.update_size())
        state.connect("tool-changed", self.on_tool_changed)
        state.connect("colors-changed", lambda *a: self.on_options_changed())
        state.connect("options-changed", lambda *a: self.on_options_changed())
        self.update_size()

    # -- geometry ---------------------------------------------------------------
    def update_size(self):
        z = self.zoom
        self.set_size_request(ORIGIN + self.doc.width * z + HANDLE + 8,
                              ORIGIN + self.doc.height * z + HANDLE + 8)
        self.queue_draw()

    def to_widget(self, x, y):
        return ORIGIN + x * self.zoom, ORIGIN + y * self.zoom

    def to_image(self, wx, wy):
        return (int(math.floor((wx - ORIGIN) / self.zoom)),
                int(math.floor((wy - ORIGIN) / self.zoom)))

    def visible_size(self):
        if self.hadj is not None:
            return self.hadj.get_page_size(), self.vadj.get_page_size()
        a = self.get_allocation()
        return a.width, a.height

    def set_zoom(self, z, point=None, center=False):
        """Zoom; point (image coords) becomes the top-left (or centre) of the view."""
        if point is None:
            vw, vh = self.visible_size()
            point = self.to_image(self.hadj.get_value() + vw / 2 if self.hadj else 0,
                                  self.vadj.get_value() + vh / 2 if self.vadj else 0)
            center = True
        self.zoom = z
        self.update_size()
        self.emit("zoom-changed")

        def scroll():
            if self.hadj is None:
                return False
            vw, vh = self.visible_size()
            px, py = point[0] * z + ORIGIN, point[1] * z + ORIGIN
            if center:
                px -= vw / 2
                py -= vh / 2
            self.hadj.set_value(max(0, min(px, self.hadj.get_upper() - vw)))
            self.vadj.set_value(max(0, min(py, self.vadj.get_upper() - vh)))
            return False

        # Wait for the new size to be allocated before scrolling.
        GLib.timeout_add(30, scroll)

    # -- cursors --------------------------------------------------------------------
    def _cursor(self, name):
        if name in self._cursors:
            return self._cursors[name]
        display = self.get_display()
        cur = None
        if name in pixmaps.CURSOR_ICONS:
            pm, hx, hy = pixmaps.CURSOR_ICONS[name]
            surf = pixmaps.get(pm)
            cur = Gdk.Cursor.new_from_surface(display, surf, hx, hy)
        else:
            cur = Gdk.Cursor.new_from_name(display, name)
            if cur is None:
                cur = Gdk.Cursor.new_from_name(display, "default")
        self._cursors[name] = cur
        return cur

    def set_cursor_name(self, name):
        if name == self._cursor_name:
            return
        self._cursor_name = name
        win = self.get_window()
        if win is not None:
            win.set_cursor(self._cursor(name))

    def tool_cursor(self):
        self.set_cursor_name(self.tool.cursor)

    # -- tool switching ----------------------------------------------------
    def on_tool_changed(self, state):
        if self.drag_button:
            self.tool.cancel()
            self.drag_button = 0
        self.tool.deactivate()
        self.tool = self.tools[state.tool]
        self.tool.activate()
        self.tool_cursor()
        self.queue_draw()
        self.emit("text-box-changed")

    def on_options_changed(self):
        self.tool.options_changed()
        self.queue_draw()

    def commit_all(self):
        """Finish anything in progress (text, curve, polygon, selection)."""
        if self.drag_button:
            self.tool.cancel()
            self.drag_button = 0
        self.tool.commit()
        self.commit_selection()

    def text_box_changed(self):
        self.emit("text-box-changed")

    def text_active(self):
        return self.tool.has_text_input and self.tool.is_busy()

    # -- events -------------------------------------------------------------------
    def _mods(self, ev):
        return ev.state

    def on_press(self, w, ev):
        self.grab_focus()
        self.last_widget_pos = (ev.x, ev.y)
        x, y = self.to_image(ev.x, ev.y)
        if ev.type == Gdk.EventType._2BUTTON_PRESS:
            self.tool.double_click(x, y, ev.button)
            return True
        if ev.type != Gdk.EventType.BUTTON_PRESS:
            return True
        if self.drag_button:
            # A second button while drawing cancels the operation.
            self.tool.cancel()
            self.drag_button = 0
            return True
        if ev.button == 1 and not self.tool.is_busy():
            h = self.resize_handle_at(ev.x, ev.y)
            if h:
                self.commit_all()
                self.resizing = [h, self.doc.width, self.doc.height]
                return True
        if ev.button not in (1, 3):
            return True
        self.drag_button = ev.button
        self.tool.press(x, y, ev.button, self._mods(ev))
        return True

    def on_motion(self, w, ev):
        self.last_widget_pos = (ev.x, ev.y)
        x, y = self.to_image(ev.x, ev.y)
        inside = 0 <= x < self.doc.width and 0 <= y < self.doc.height
        self.emit("pointer-info", x, y, inside)
        if self.resizing:
            h = self.resizing[0]
            nw = max(1, x) if h in ("e", "se") else self.doc.width
            nh = max(1, y) if h in ("s", "se") else self.doc.height
            self.resizing[1:] = [nw, nh]
            self.emit_size(nw, nh)
            self.queue_draw()
            return True
        if self.drag_button:
            self.tool.drag(x, y, self._mods(ev))
            return True
        h = self.resize_handle_at(ev.x, ev.y) if not self.tool.is_busy() else None
        if h:
            self.set_cursor_name({"e": "ew-resize", "s": "ns-resize", "se": "nwse-resize"}[h])
        else:
            self.tool_cursor()
            self.tool.hover(x, y)
        return True

    def on_release(self, w, ev):
        self.last_widget_pos = (ev.x, ev.y)
        x, y = self.to_image(ev.x, ev.y)
        if self.resizing:
            _, nw, nh = self.resizing
            self.resizing = None
            self.emit_size(None)
            self.doc.resize(nw, nh, self.state.bg)
            self.queue_draw()
            return True
        if self.drag_button and ev.button == self.drag_button:
            self.drag_button = 0
            self.tool.release(x, y, ev.button, self._mods(ev))
        return True

    def on_leave(self, w, ev):
        self.emit("pointer-info", 0, 0, False)
        if not self.drag_button:
            self.tool.leave()
        return False

    def on_realize(self, w):
        self.im.set_client_window(self.get_window())
        self.tool_cursor()

    def on_unrealize(self, w):
        self.im.set_client_window(None)

    def on_focus_in(self, w, ev):
        self.im.focus_in()
        self.queue_draw()
        return False

    def on_focus_out(self, w, ev):
        self.im.focus_out()
        self.queue_draw()
        return False

    def on_im_commit(self, im, text):
        if self.text_active():
            self.tool.insert(text)

    def handle_key(self, ev):
        """Called by the window before accelerators so typing reaches text."""
        if not self.text_active():
            return False
        if self.tool.key_press(ev):
            return True
        if ev.state & (Gdk.ModifierType.CONTROL_MASK | Gdk.ModifierType.MOD1_MASK):
            return False
        return self.im.filter_keypress(ev)

    # -- previews and status -----------------------------------------------
    def set_preview(self, surf):
        self.preview = surf
        self.queue_draw()
        self.emit("picture-changed")

    def picture_changed(self):
        self.queue_draw()
        self.emit("picture-changed")

    def composite_picture(self):
        """The picture as currently shown: preview and floating selection."""
        surf = imageops.copy_surface(self.preview or self.doc.surface)
        sel = self._selection
        if sel is not None and sel.floating:
            cr = cairo.Context(surf)
            sel.paint(cr, self.state.transparent, self.state.bg)
        return surf

    def emit_size(self, w, h=0):
        if w is None:
            self.emit("size-info", 0, 0, False)
        else:
            self.emit("size-info", int(w), int(h), True)

    def show_context_menu(self):
        self.emit("context-menu")

    # -- handles -----------------------------------------------------------------
    def _handle_points(self, x, y, w, h):
        """Widget-space rects for the 8 handles around an image-space box."""
        z = self.zoom
        x0, y0 = ORIGIN + x * z, ORIGIN + y * z
        x1, y1 = x0 + w * z, y0 + h * z
        xm, ym = (x0 + x1) // 2 - 1, (y0 + y1) // 2 - 1
        return {
            "nw": (x0 - HANDLE, y0 - HANDLE), "n": (xm, y0 - HANDLE), "ne": (x1, y0 - HANDLE),
            "w": (x0 - HANDLE, ym), "e": (x1, ym),
            "sw": (x0 - HANDLE, y1), "s": (xm, y1), "se": (x1, y1),
        }

    def resize_handle_at(self, wx, wy):
        pts = self._handle_points(0, 0, self.doc.width, self.doc.height)
        for name in ("se", "e", "s"):
            hx, hy = pts[name]
            if hx - 2 <= wx < hx + HANDLE + 2 and hy - 2 <= wy < hy + HANDLE + 2:
                return name
        return None

    def selection_handle_at(self, wx, wy):
        sel = self._selection
        if sel is None:
            return None
        for name, (hx, hy) in self._handle_points(sel.x, sel.y, sel.w, sel.h).items():
            if hx - 1 <= wx < hx + HANDLE + 1 and hy - 1 <= wy < hy + HANDLE + 1:
                return name
        return None

    # -- selection -----------------------------------------------------------------
    @property
    def selection(self):
        return self._selection

    @selection.setter
    def selection(self, sel):
        self._selection = sel
        self.queue_draw()
        self.emit("selection-changed")

    def create_selection(self, x, y, w, h):
        content = imageops.copy_surface(self.doc.surface, x, y, w, h)
        self.selection = Selection(content, x, y)

    def create_free_selection(self, pts):
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        x0 = max(0, min(xs))
        y0 = max(0, min(ys))
        x1 = min(self.doc.width - 1, max(xs))
        y1 = min(self.doc.height - 1, max(ys))
        if x1 < x0 or y1 < y0:
            return
        w, h = x1 - x0 + 1, y1 - y0 + 1
        mask = cairo.ImageSurface(cairo.FORMAT_A8, w, h)
        mcr = cairo.Context(mask)
        mcr.set_antialias(cairo.ANTIALIAS_NONE)
        for i, (px, py) in enumerate(pts):
            fn = mcr.move_to if i == 0 else mcr.line_to
            fn(px - x0 + 0.5, py - y0 + 0.5)
        mcr.close_path()
        mcr.fill_preserve()
        mcr.set_line_width(1)
        mcr.stroke()
        self._select_masked(mask, x0, y0)

    def _select_masked(self, mask, x0, y0):
        """Select the pixels under an A8 mask placed at (x0, y0)."""
        w, h = mask.get_width(), mask.get_height()
        region = imageops.copy_surface(self.doc.surface, x0, y0, w, h)
        content = imageops.new_surface(w, h)
        cr = cairo.Context(content)
        cr.set_source_surface(region, 0, 0)
        cr.mask_surface(mask, 0, 0)
        self.selection = Selection(content, x0, y0, mask=mask)

    def create_mask_selection(self, full_mask, bbox, add=False):
        """Select from a picture-sized A8 mask. With add=True the current
        (not yet moved) selection is merged in."""
        x0, y0, x1, y1 = bbox
        sel = self._selection
        if add and sel is not None and not sel.floating:
            union = imageops.new_mask(self.doc.width, self.doc.height)
            ucr = cairo.Context(union)
            ucr.set_source_rgb(0, 0, 0)
            ucr.mask_surface(imageops.alpha_mask(sel.content), sel.x, sel.y)
            ucr.mask_surface(full_mask, 0, 0)
            full_mask = union
            x0, y0 = min(x0, sel.x), min(y0, sel.y)
            x1, y1 = max(x1, sel.x + sel.w - 1), max(y1, sel.y + sel.h - 1)
        w, h = x1 - x0 + 1, y1 - y0 + 1
        crop = imageops.new_mask(w, h)
        ccr = cairo.Context(crop)
        ccr.set_operator(cairo.OPERATOR_SOURCE)
        ccr.set_source_surface(full_mask, -x0, -y0)
        ccr.paint()
        self._select_masked(crop, x0, y0)

    def lift_selection(self, erase=True):
        sel = self._selection
        if sel is None or sel.floating:
            return
        self.doc.push_undo()
        if erase:
            cr = cairo.Context(self.doc.surface)
            imageops.set_rgb(cr, self.state.bg)
            ox, oy, ow, oh = sel.origin
            if sel.mask is not None:
                cr.mask_surface(sel.mask, ox, oy)
            else:
                cr.rectangle(ox, oy, ow, oh)
                cr.fill()
        sel.floating = True
        self.doc.changed()

    def stamp_selection(self):
        sel = self._selection
        if sel is None:
            return
        cr = cairo.Context(self.doc.surface)
        sel.paint(cr, self.state.transparent, self.state.bg)
        self.doc.changed()

    def commit_selection(self):
        sel = self._selection
        if sel is None:
            return
        if sel.floating:
            self.stamp_selection()
        self.selection = None

    def discard_selection(self):
        self.selection = None

    def float_surface(self, surf, x, y):
        """Paste a surface as a new floating selection."""
        self.commit_all()
        if self.state.tool not in ("rect_select", "free_select"):
            self.state.set_tool("rect_select")
        self.doc.push_undo()
        self.selection = Selection(surf, x, y, floating=True)

    def visible_origin(self):
        if self.hadj is None:
            return 0, 0
        x, y = self.to_image(self.hadj.get_value(), self.vadj.get_value())
        return max(0, x), max(0, y)

    # -- history ---------------------------------------------------------------------
    def undo(self):
        if self.drag_button:
            self.tool.cancel()
            self.drag_button = 0
        if self.tool.is_busy():
            self.tool.cancel()
            if hasattr(self.tool, "box") and self.tool.box is not None:
                self.tool.box = None
                self.text_box_changed()
            self.set_preview(None)
            return
        self.selection = None
        self.doc.undo()

    def redo(self):
        self.commit_all()
        self.doc.redo()

    # -- drawing ---------------------------------------------------------------------
    def on_draw(self, w, cr):
        z = self.zoom
        cr.set_source_rgb(*WORKSPACE)
        cr.paint()
        iw, ih = self.doc.width, self.doc.height

        cr.save()
        cr.translate(ORIGIN, ORIGIN)
        cr.rectangle(0, 0, iw * z, ih * z)
        cr.clip()
        cr.scale(z, z)
        src = self.preview or self.doc.surface
        cr.set_source_surface(src, 0, 0)
        cr.get_source().set_filter(cairo.FILTER_NEAREST)
        cr.paint()
        sel = self._selection
        if sel is not None and sel.floating:
            sel.paint(cr, self.state.transparent, self.state.bg)
        self.tool.draw_image_layer(cr)
        cr.restore()

        if self.state.show_grid and z >= 4:
            self.draw_grid(cr, iw, ih, z)

        # Picture sizing handles.
        for name, (hx, hy) in self._handle_points(0, 0, iw, ih).items():
            if name in ("e", "s", "se"):
                cr.set_source_rgb(*HANDLE_COLOR)
                cr.rectangle(hx, hy, HANDLE, HANDLE)
                cr.fill()
            else:
                cr.set_source_rgb(1, 1, 1)
                cr.rectangle(hx, hy, HANDLE, HANDLE)
                cr.fill()

        if sel is not None:
            edges = sel.outline()
            if edges is not None:
                # Marching-ants style outline of the real shape.
                cr.save()
                cr.translate(ORIGIN, ORIGIN)
                cr.scale(z, z)
                cr.set_source(ants_pattern())
                cr.mask_surface(edges, sel.x, sel.y)
                cr.restore()
            sx, sy = self.to_widget(sel.x, sel.y)
            win98.dotted_rect(cr, int(sx) - 1, int(sy) - 1, sel.w * z + 2, sel.h * z + 2, HANDLE_COLOR)
            cr.set_source_rgb(*HANDLE_COLOR)
            for hx, hy in self._handle_points(sel.x, sel.y, sel.w, sel.h).values():
                cr.rectangle(hx, hy, HANDLE, HANDLE)
            cr.fill()

        if symmetry.active(self.state, self.state.tool):
            symmetry.draw_guides(cr, self.state.symmetry, ORIGIN, ORIGIN, iw, ih, z)

        self.tool.draw_overlay(cr)

        if self.resizing:
            _, nw, nh = self.resizing
            win98.dotted_rect(cr, ORIGIN, ORIGIN, nw * z, nh * z, (0, 0, 0))
        return True

    def draw_grid(self, cr, iw, ih, z):
        clip = cr.clip_extents()
        x0 = max(0, int((clip[0] - ORIGIN) // z))
        y0 = max(0, int((clip[1] - ORIGIN) // z))
        x1 = min(iw, int((clip[2] - ORIGIN) // z) + 1)
        y1 = min(ih, int((clip[3] - ORIGIN) // z) + 1)
        cr.set_source_rgb(0.5, 0.5, 0.5)
        for x in range(x0, x1 + 1):
            cr.rectangle(ORIGIN + x * z, ORIGIN + y0 * z, 1, (y1 - y0) * z)
        for y in range(y0, y1 + 1):
            cr.rectangle(ORIGIN + x0 * z, ORIGIN + y * z, (x1 - x0) * z, 1)
        cr.fill()
