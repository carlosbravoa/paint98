"""Floating selections (rectangular or free-form)."""

import cairo

from . import imageops


class Selection:
    def __init__(self, content, x, y, mask=None, floating=False):
        self.content = content
        # Free-form and magic wand selections have a shape, not just a box.
        self.shaped = mask is not None
        self._outline = None
        self.mask = mask  # A8 surface in content coordinates (free-form only)
        self.x, self.y = x, y
        self.w, self.h = content.get_width(), content.get_height()
        self.origin = (x, y, self.w, self.h)
        self.floating = floating
        self._baked = None
        self._keyed = None

    def contains(self, x, y):
        return self.x <= x < self.x + self.w and self.y <= y < self.y + self.h

    def hit(self, x, y):
        """True when (x, y) is on the selected pixels (not just in the box)."""
        if not self.contains(x, y):
            return False
        if not self.shaped:
            return True
        surf = self.baked()
        surf.flush()
        px = surf.get_data().cast("I")
        return (px[(y - self.y) * (surf.get_stride() // 4) + (x - self.x)] >> 24) > 0

    def outline(self):
        """A8 mask of the shape's edge pixels (None for plain boxes)."""
        if not self.shaped:
            return None
        surf = self.baked()
        key = (id(surf), self.w, self.h)
        if self._outline is None or self._outline[0] != key:
            self._outline = (key, imageops.alpha_edges(surf))
        return self._outline[1]

    def set_content(self, surf):
        self.content = surf
        self.w, self.h = surf.get_width(), surf.get_height()
        self.mask = None
        self._baked = None
        self._keyed = None
        self._outline = None

    def baked(self):
        """Content scaled to the current on-canvas size."""
        if (self.w, self.h) == (self.content.get_width(), self.content.get_height()):
            return self.content
        if self._baked is None or self._baked[0] != (self.w, self.h):
            self._baked = ((self.w, self.h), imageops.scale(self.content, self.w, self.h))
        return self._baked[1]

    def bake(self):
        if (self.w, self.h) != (self.content.get_width(), self.content.get_height()):
            self.set_content(self.baked())

    def render(self, transparent, bg):
        src = self.baked()
        if not transparent:
            return src
        key = (id(src), (self.w, self.h), tuple(bg))
        if self._keyed is None or self._keyed[0] != key:
            self._keyed = (key, imageops.key_out(src, bg))
        return self._keyed[1]

    def paint(self, cr, transparent, bg):
        cr.save()
        cr.set_source_surface(self.render(transparent, bg), self.x, self.y)
        cr.get_source().set_filter(cairo.FILTER_NEAREST)
        cr.paint()
        cr.restore()
