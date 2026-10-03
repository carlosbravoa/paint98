"""The picture being edited: pixels, file name and undo history."""

import os

import cairo
import gi

gi.require_version("Gdk", "3.0")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import Gdk, GdkPixbuf, GObject  # noqa: E402

from . import imageops  # noqa: E402

UNDO_LEVELS = 30

SAVE_FORMATS = {
    ".png": "png",
    ".bmp": "bmp",
    ".jpg": "jpeg",
    ".jpeg": "jpeg",
    ".tif": "tiff",
    ".tiff": "tiff",
    ".ico": "ico",
}


def surface_to_pixbuf(surf):
    return Gdk.pixbuf_get_from_surface(surf, 0, 0, surf.get_width(), surf.get_height())


def pixbuf_to_surface(pb, background=(255, 255, 255)):
    w, h = pb.get_width(), pb.get_height()
    surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, w, h)
    cr = cairo.Context(surf)
    if background is not None:
        imageops.set_rgb(cr, background)
        cr.paint()
    Gdk.cairo_set_source_pixbuf(cr, pb, 0, 0)
    cr.paint()
    return surf


class Document(GObject.Object):
    __gsignals__ = {
        "changed": (GObject.SignalFlags.RUN_FIRST, None, ()),
        "size-changed": (GObject.SignalFlags.RUN_FIRST, None, ()),
        "state-changed": (GObject.SignalFlags.RUN_FIRST, None, ()),
    }

    def __init__(self, width=640, height=480):
        super().__init__()
        self.filename = None
        self.modified = False
        self.undo_stack = []
        self.redo_stack = []
        self.surface = imageops.new_surface(width, height, (255, 255, 255))

    @property
    def width(self):
        return self.surface.get_width()

    @property
    def height(self):
        return self.surface.get_height()

    @property
    def display_name(self):
        if self.filename:
            return os.path.basename(self.filename)
        return "untitled"

    # -- history -----------------------------------------------------------
    def push_undo(self):
        self.undo_stack.append(imageops.copy_surface(self.surface))
        del self.undo_stack[:-UNDO_LEVELS]
        self.redo_stack.clear()
        self.set_modified(True)
        self.emit("state-changed")

    def _swap(self, src, dst):
        if not src:
            return False
        old_size = (self.width, self.height)
        dst.append(self.surface)
        self.surface = src.pop()
        if old_size != (self.width, self.height):
            self.emit("size-changed")
        self.set_modified(True)
        self.emit("changed")
        self.emit("state-changed")
        return True

    def undo(self):
        return self._swap(self.undo_stack, self.redo_stack)

    def redo(self):
        return self._swap(self.redo_stack, self.undo_stack)

    def can_undo(self):
        return bool(self.undo_stack)

    def can_redo(self):
        return bool(self.redo_stack)

    def set_modified(self, value):
        if self.modified != value:
            self.modified = value
            self.emit("state-changed")

    # -- whole-image changes ----------------------------------------------
    def changed(self):
        self.set_modified(True)
        self.emit("changed")

    def replace_surface(self, surf, undo=True):
        if undo:
            self.push_undo()
        size_changed = (surf.get_width(), surf.get_height()) != (self.width, self.height)
        self.surface = surf
        if size_changed:
            self.emit("size-changed")
        self.changed()

    def resize(self, w, h, bg):
        w, h = max(1, int(w)), max(1, int(h))
        if (w, h) == (self.width, self.height):
            return
        new = imageops.new_surface(w, h, bg)
        cr = cairo.Context(new)
        cr.set_source_surface(self.surface, 0, 0)
        cr.paint()
        self.replace_surface(new)

    def new(self, w, h):
        self.surface = imageops.new_surface(w, h, (255, 255, 255))
        self.filename = None
        self.undo_stack.clear()
        self.redo_stack.clear()
        self.modified = False
        self.emit("size-changed")
        self.emit("changed")
        self.emit("state-changed")

    # -- files ---------------------------------------------------------------
    def load(self, path):
        pb = GdkPixbuf.Pixbuf.new_from_file(path)
        pb = pb.apply_embedded_orientation() or pb
        self.surface = pixbuf_to_surface(pb)
        self.filename = path
        self.undo_stack.clear()
        self.redo_stack.clear()
        self.modified = False
        self.emit("size-changed")
        self.emit("changed")
        self.emit("state-changed")

    @staticmethod
    def format_for(path):
        ext = os.path.splitext(path)[1].lower()
        return SAVE_FORMATS.get(ext)

    def save(self, path, surface=None):
        fmt = self.format_for(path) or "png"
        surf = surface or self.surface
        pb = surface_to_pixbuf(surf)
        if fmt in ("jpeg", "bmp"):
            if pb.get_has_alpha():
                # Flatten: these formats carry no alpha channel.
                flat = GdkPixbuf.Pixbuf.new(GdkPixbuf.Colorspace.RGB, False, 8,
                                            pb.get_width(), pb.get_height())
                flat.fill(0xFFFFFFFF)
                pb.composite(flat, 0, 0, pb.get_width(), pb.get_height(), 0, 0, 1, 1,
                             GdkPixbuf.InterpType.NEAREST, 255)
                pb = flat
        keys, values = [], []
        if fmt == "jpeg":
            keys, values = ["quality"], ["92"]
        pb.savev(path, fmt, keys, values)
        if surface is None:
            self.filename = path
            self.modified = False
            self.emit("state-changed")
