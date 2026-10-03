"""Drawing tools. Coordinates passed to tools are image pixel coordinates."""

import math
import random

import cairo
import gi

gi.require_version("Gtk", "3.0")
gi.require_version("PangoCairo", "1.0")
from gi.repository import Gdk, GLib, Pango, PangoCairo  # noqa: E402

from . import imageops, stickers, symmetry, win98  # noqa: E402
from .funpaints import is_fun, set_paint, solid  # noqa: E402
from .imageops import bresenham, disc_offsets, set_rgb, square_offsets, stamp_path  # noqa: E402
from .state import AIRBRUSH_SIZES, BRUSH_SHAPES, MAGNIFY_LEVELS  # noqa: E402

SHIFT = Gdk.ModifierType.SHIFT_MASK
CTRL = Gdk.ModifierType.CONTROL_MASK


def brush_offsets(kind, size):
    h = size // 2
    if kind == "circle":
        return disc_offsets(size)
    if kind == "square":
        return square_offsets(size)
    if kind == "slash":
        return [(i - h, (size - 1 - i) - h) for i in range(size)]
    return [(i - h, i - h) for i in range(size)]


def paint_dabs(cr, pts, kind, size):
    """Fill the footprint of a (kind, size) tip along consecutive points.

    Small tips are stamped pixel by pixel (exact classic shapes); big round
    tips use a round-capped stroke so large brushes stay fast."""
    if not pts:
        return
    if kind == "circle" and size > 8:
        cr.save()
        cr.set_line_width(size)
        cr.set_line_cap(cairo.LINE_CAP_ROUND)
        cr.set_line_join(cairo.LINE_JOIN_ROUND)
        off = 0.5 if size % 2 else 0.0
        cr.move_to(pts[0][0] + off, pts[0][1] + off)
        for x, y in pts[1:]:
            cr.line_to(x + off, y + off)
        if len(pts) == 1:
            cr.line_to(pts[0][0] + off, pts[0][1] + off)
        cr.stroke()
        cr.restore()
    elif kind == "square":
        h = size // 2
        for x, y in pts:
            cr.rectangle(x - h, y - h, size, size)
        cr.fill()
    else:
        offs = brush_offsets(kind, size)
        stamp_path(cr, pts, offs)
        if size > 1 and len(pts) > 1:
            # A slanted tip leaves holes when it moves across its own
            # direction; fill the band it sweeps between each pair of points.
            (ax, ay), (bx, by) = offs[0], offs[-1]
            for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
                if (x0, y0) == (x1, y1):
                    continue
                cr.move_to(x0 + ax + 0.5, y0 + ay + 0.5)
                cr.line_to(x0 + bx + 0.5, y0 + by + 0.5)
                cr.line_to(x1 + bx + 0.5, y1 + by + 0.5)
                cr.line_to(x1 + ax + 0.5, y1 + ay + 0.5)
                cr.close_path()
            cr.fill()


def draw_footprint(cr, canvas, pos, kind, size, fill=None):
    """Show a tip's exact pixel footprint at the pointer: optionally filled,
    always traced in black so it is visible over any colour."""
    z = canvas.zoom
    r = size // 2 + 1
    fp = imageops.new_mask(2 * r + 1, 2 * r + 1)
    fcr = cairo.Context(fp)
    fcr.set_antialias(cairo.ANTIALIAS_NONE)
    paint_dabs(fcr, [(r, r)], kind, size)
    fp.flush()
    data, stride = fp.get_data(), fp.get_stride()
    n = 2 * r + 1

    def on(x, y):
        return 0 <= x < n and 0 <= y < n and data[y * stride + x] > 127

    wx, wy = canvas.to_widget(pos[0] - r, pos[1] - r)
    if fill is not None:
        set_rgb(cr, fill)
        cr.save()
        cr.translate(wx, wy)
        cr.scale(z, z)
        cr.mask_surface(fp, 0, 0)
        cr.restore()
    cr.set_source_rgb(0, 0, 0)
    for y in range(n):
        for x in range(n):
            if not on(x, y):
                continue
            px, py = wx + x * z, wy + y * z
            if not on(x, y - 1):
                cr.rectangle(px, py, z, 1)
            if not on(x, y + 1):
                cr.rectangle(px, py + z - 1, z, 1)
            if not on(x - 1, y):
                cr.rectangle(px, py, 1, z)
            if not on(x + 1, y):
                cr.rectangle(px + z - 1, py, 1, z)
    cr.fill()


def constrain_45(x0, y0, x1, y1):
    dx, dy = x1 - x0, y1 - y0
    adx, ady = abs(dx), abs(dy)
    if adx > 2 * ady:
        return x1, y0
    if ady > 2 * adx:
        return x0, y1
    d = max(adx, ady)
    return x0 + (d if dx >= 0 else -d), y0 + (d if dy >= 0 else -d)


def constrain_square(x0, y0, x1, y1):
    d = max(abs(x1 - x0), abs(y1 - y0))
    return x0 + (d if x1 >= x0 else -d), y0 + (d if y1 >= y0 else -d)


class Tool:
    name = None
    cursor = "crosshair"
    has_text_input = False

    def __init__(self, canvas):
        self.c = canvas

    @property
    def state(self):
        return self.c.state

    @property
    def doc(self):
        return self.c.doc

    def color(self, button):
        return self.state.fg if button == 1 else self.state.bg

    def other_color(self, button):
        return self.state.bg if button == 1 else self.state.fg

    def symmetry_transforms(self):
        if symmetry.active(self.state, self.name):
            return symmetry.transforms(self.state.symmetry, self.doc.width, self.doc.height)
        return [cairo.Matrix()]

    def context(self, surf=None):
        cr = cairo.Context(surf or self.doc.surface)
        cr.set_antialias(cairo.ANTIALIAS_NONE)
        return cr

    def activate(self):
        pass

    def deactivate(self):
        self.commit()

    def commit(self):
        pass

    def cancel(self):
        pass

    def is_busy(self):
        return False

    def press(self, x, y, button, mods):
        pass

    def drag(self, x, y, mods):
        pass

    def release(self, x, y, button, mods):
        pass

    def hover(self, x, y):
        pass

    def leave(self):
        pass

    def double_click(self, x, y, button):
        pass

    def draw_image_layer(self, cr):
        pass

    def draw_overlay(self, cr):
        pass

    def key_press(self, ev):
        return False

    def options_changed(self):
        pass


# ---------------------------------------------------------------------------
# Freehand tools
# ---------------------------------------------------------------------------

class StrokeTool(Tool):
    """Base for tools that paint a stroke with an opacity.

    Stamps are painted opaque onto a stroke layer; the picture is recomposed
    as base + layer at the tool's opacity, so overlapping stamps never build
    up past it. Colour-cycling paints change colour along the stroke.
    """

    def begin_stroke(self, paint):
        self.doc.push_undo()
        self.base = self.doc.undo_stack[-1]
        self.layer = imageops.new_surface(self.doc.width, self.doc.height)
        self.paint = paint
        self.alpha = self.state.tool_opacity(self.name)
        self.progress = 0.0
        self.match = None

    def stamp(self, pts, tip):
        """Add a (kind, size) tip along pts to the stroke layer."""
        if not pts:
            return
        kind, size = tip
        lcr = cairo.Context(self.layer)
        lcr.set_antialias(cairo.ANTIALIAS_NONE)
        set_paint(lcr, self.paint, progress=self.progress)
        xs, ys = [], []
        for m in self.symmetry_transforms():
            copy = symmetry.map_points(pts, m)
            paint_dabs(lcr, copy, kind, size)
            xs += [p[0] for p in copy]
            ys += [p[1] for p in copy]
        self.progress += math.dist(pts[0], pts[-1]) + 1
        r = size // 2 + 2
        self.composite((min(xs) - r, min(ys) - r, max(xs) + r + 1, max(ys) + r + 1))

    def composite(self, box):
        x0, y0, x1, y1 = box
        cr = cairo.Context(self.doc.surface)
        cr.rectangle(x0, y0, x1 - x0, y1 - y0)
        cr.clip()
        cr.set_operator(cairo.OPERATOR_SOURCE)
        cr.set_source_surface(self.base, 0, 0)
        cr.paint()
        cr.set_operator(cairo.OPERATOR_OVER)
        cr.set_source_surface(self.layer, 0, 0)
        if self.match is None:
            cr.paint_with_alpha(self.alpha)
        else:
            cr.push_group()
            cr.set_source_surface(self.layer, 0, 0)
            cr.paint_with_alpha(self.alpha)
            cr.pop_group_to_source()
            cr.mask_surface(self.match, 0, 0)
        self.doc.changed()


class FreehandTool(StrokeTool):
    def tip(self):
        return ("circle", 1)

    def press(self, x, y, button, mods):
        self.begin_stroke(self.color(button))
        self.last = (x, y)
        self.stamp([(x, y)], self.tip())

    def drag(self, x, y, mods):
        self.stamp(bresenham(self.last[0], self.last[1], x, y), self.tip())
        self.last = (x, y)


class PencilTool(FreehandTool):
    name = "pencil"
    cursor = "pencil"

    def __init__(self, canvas):
        super().__init__(canvas)
        self.pos = None

    def tip(self):
        return ("circle", self.state.pencil_size)

    def hover(self, x, y):
        self.pos = (x, y)
        if self.state.pencil_size > 1:
            self.c.queue_draw()

    def drag(self, x, y, mods):
        super().drag(x, y, mods)
        self.pos = (x, y)

    def leave(self):
        self.pos = None
        self.c.queue_draw()

    def draw_overlay(self, cr):
        # A thick pencil shows the outline of its tip under the pointer.
        if self.pos is not None and self.state.pencil_size > 1:
            draw_footprint(cr, self.c, self.pos, *self.tip())


class BrushTool(FreehandTool):
    name = "brush"
    cursor = "none"

    def __init__(self, canvas):
        super().__init__(canvas)
        self.pos = None

    def tip(self):
        return (BRUSH_SHAPES[self.state.brush][0], self.state.brush_size)

    def hover(self, x, y):
        self.pos = (x, y)
        self.c.queue_draw()

    def drag(self, x, y, mods):
        super().drag(x, y, mods)
        self.pos = (x, y)

    def leave(self):
        self.pos = None
        self.c.queue_draw()

    def draw_image_layer(self, cr):
        if self.pos is None or self.c.drag_button:
            return
        cr.save()
        cr.set_antialias(cairo.ANTIALIAS_NONE)
        set_paint(cr, self.state.fg, progress=0)
        paint_dabs(cr, [self.pos], *self.tip())
        cr.restore()


class EraserTool(StrokeTool):
    """Left button paints the background colour; right button replaces only
    the foreground colour (colour eraser). Square or round, with opacity."""
    name = "eraser"
    cursor = "none"

    def __init__(self, canvas):
        super().__init__(canvas)
        self.pos = None

    def tip(self):
        return (self.state.eraser_shape, self.state.eraser_px)

    def press(self, x, y, button, mods):
        self.begin_stroke(self.state.bg)
        self.button = button
        # The colour eraser only touches pixels that had the foreground colour.
        self.match = imageops.color_mask(self.base, solid(self.state.fg)) if button == 3 else None
        self.last = self.pos = (x, y)
        self.stamp([(x, y)], self.tip())

    def drag(self, x, y, mods):
        self.stamp(bresenham(self.last[0], self.last[1], x, y), self.tip())
        self.last = self.pos = (x, y)

    def hover(self, x, y):
        self.pos = (x, y)
        self.c.queue_draw()

    def leave(self):
        self.pos = None
        self.c.queue_draw()

    def draw_overlay(self, cr):
        if self.pos is not None:
            draw_footprint(cr, self.c, self.pos, *self.tip(), fill=self.state.bg)


class AirbrushTool(StrokeTool):
    name = "airbrush"
    cursor = "airbrush"

    def __init__(self, canvas):
        super().__init__(canvas)
        self.timer = None

    def press(self, x, y, button, mods):
        self.begin_stroke(self.color(button))
        self.pos = (x, y)
        self.spray()
        self.timer = GLib.timeout_add(25, self.spray)

    def drag(self, x, y, mods):
        self.pos = (x, y)
        self.spray(False)

    def release(self, x, y, button, mods):
        self.stop()

    def cancel(self):
        self.stop()

    def stop(self):
        if self.timer:
            GLib.source_remove(self.timer)
            self.timer = None

    def spray(self, from_timer=True):
        size = AIRBRUSH_SIZES[self.state.airbrush_size]
        r = size / 2
        count = {9: 5, 16: 9, 24: 14}[size]
        pts = []
        for _ in range(count):
            while True:
                dx = random.uniform(-r, r)
                dy = random.uniform(-r, r)
                if dx * dx + dy * dy <= r * r:
                    break
            pts.append((int(self.pos[0] + dx), int(self.pos[1] + dy)))
        self.stamp(pts, ("square", 1))
        return True


class FillTool(Tool):
    """Flood fill with tolerance; solid colour or a linear/radial gradient
    dragged from the click point (foreground to background colour)."""
    name = "fill"
    cursor = "fill"

    def __init__(self, canvas):
        super().__init__(canvas)
        self.region = None
        self.start = self.end = None

    def is_busy(self):
        return self.region is not None

    def press(self, x, y, button, mods):
        st = self.state
        paint = self.color(button)
        if (st.fill_mode == 0 and st.tolerance == 0 and st.tool_opacity("fill") >= 1 and not is_fun(paint)
                and imageops.get_pixel(self.doc.surface, x, y) == tuple(paint)):
            return
        res = imageops.region_mask(self.doc.surface, x, y, st.tolerance)
        if res is None:
            return
        self.region, self.bbox = res
        self.button = button
        self.start = self.end = (x, y)
        if self.state.fill_mode == 0:
            self.doc.push_undo()
            self.paint(self.doc.surface)
            self.doc.changed()
            self.region = None
        else:
            self.show()

    def drag(self, x, y, mods):
        if self.region is None:
            return
        if mods & SHIFT:
            x, y = constrain_45(self.start[0], self.start[1], x, y)
        self.end = (x, y)
        self.show()

    def release(self, x, y, button, mods):
        if self.region is None:
            return
        self.drag(x, y, mods)
        self.doc.push_undo()
        self.paint(self.doc.surface)
        self.c.set_preview(None)
        self.doc.changed()
        self.region = None

    def cancel(self):
        self.region = None
        self.c.set_preview(None)

    def commit(self):
        self.cancel()

    def show(self):
        prev = imageops.copy_surface(self.doc.surface)
        self.paint(prev)
        self.c.set_preview(prev)

    def source(self):
        a = 1.0  # opacity is applied when painting
        c1, c2 = self.color(self.button), self.other_color(self.button)
        if is_fun(c1) or is_fun(c2):
            # Fun paints bring their own colours: fill the area with them.
            return (c1 if is_fun(c1) else c2).pattern(self.bbox)
        if self.state.fill_mode == 0:
            return cairo.SolidPattern(c1[0] / 255, c1[1] / 255, c1[2] / 255, a)
        x0, y0, x1, y1 = self.bbox
        (sx, sy), (ex, ey) = self.start, self.end
        sx, sy, ex, ey = sx + 0.5, sy + 0.5, ex + 0.5, ey + 0.5
        if self.state.fill_mode == 1:
            if (sx, sy) == (ex, ey):  # a plain click: left to right across the area
                sx, sy, ex, ey = x0, sy, x1 + 1, sy
            pat = cairo.LinearGradient(sx, sy, ex, ey)
        else:
            r = math.hypot(ex - sx, ey - sy)
            if r < 1:  # a plain click: reach the farthest corner of the area
                r = max(math.hypot(cx - sx, cy - sy) for cx in (x0, x1 + 1) for cy in (y0, y1 + 1))
            pat = cairo.RadialGradient(sx, sy, 0, sx, sy, max(1, r))
        pat.add_color_stop_rgba(0, c1[0] / 255, c1[1] / 255, c1[2] / 255, a)
        pat.add_color_stop_rgba(1, c2[0] / 255, c2[1] / 255, c2[2] / 255, a)
        pat.set_extend(cairo.EXTEND_PAD)
        return pat

    def paint(self, surf):
        cr = cairo.Context(surf)
        cr.push_group()
        cr.set_source(self.source())
        cr.mask_surface(self.region, 0, 0)
        cr.pop_group_to_source()
        cr.paint_with_alpha(self.state.tool_opacity("fill"))

    def draw_overlay(self, cr):
        if self.region is None or self.start == self.end:
            return
        z = self.c.zoom
        sx, sy = self.c.to_widget(*self.start)
        ex, ey = self.c.to_widget(*self.end)
        cr.set_line_width(1)
        cr.move_to(sx + z / 2, sy + z / 2)
        cr.line_to(ex + z / 2, ey + z / 2)
        cr.set_source_rgb(1, 1, 1)
        cr.set_dash([3, 3], 0)
        cr.stroke_preserve()
        cr.set_source_rgb(0, 0, 0)
        cr.set_dash([3, 3], 3)
        cr.stroke()


class PickTool(Tool):
    cursor = "pick"

    def pick(self, x, y):
        rgb = imageops.get_pixel(self.doc.surface, x, y)
        if rgb is None:
            return
        if self.button == 1:
            self.state.set_fg(rgb)
        else:
            self.state.set_bg(rgb)

    def press(self, x, y, button, mods):
        self.button = button
        self.pick(x, y)

    def drag(self, x, y, mods):
        self.pick(x, y)

    def release(self, x, y, button, mods):
        self.pick(x, y)
        GLib.idle_add(self.state.set_tool, self.state.prev_tool)


class MagnifierTool(Tool):
    cursor = "magnifier"

    def __init__(self, canvas):
        super().__init__(canvas)
        self.pos = None

    def target_level(self):
        return MAGNIFY_LEVELS[self.state.magnify]

    def view_box(self):
        """Rectangle (image px) that will fill the view after zooming in."""
        level = self.target_level()
        vw, vh = self.c.visible_size()
        w = max(1, int(vw / level))
        h = max(1, int(vh / level))
        x = self.pos[0] - w // 2
        y = self.pos[1] - h // 2
        x = max(0, min(x, self.doc.width - w))
        y = max(0, min(y, self.doc.height - h))
        return x, y, min(w, self.doc.width), min(h, self.doc.height)

    def hover(self, x, y):
        self.pos = (x, y)
        self.c.queue_draw()

    def leave(self):
        self.pos = None
        self.c.queue_draw()

    def press(self, x, y, button, mods):
        if button == 1 and self.c.zoom == 1:
            level = self.target_level()
            if level != 1:
                bx, by, bw, bh = self.view_box()
                self.c.set_zoom(level, (bx, by))
        else:
            self.c.set_zoom(1, (x, y), center=True)
        self.pos = None
        GLib.idle_add(self.state.set_tool, self.state.prev_tool)

    def draw_overlay(self, cr):
        if self.pos is None or self.c.zoom != 1 or self.target_level() == 1:
            return
        x, y, w, h = self.view_box()
        wx, wy = self.c.to_widget(x, y)
        cr.set_source_rgb(0, 0, 0)
        cr.set_line_width(1)
        cr.rectangle(wx + 0.5, wy + 0.5, w - 1, h - 1)
        cr.stroke()


# ---------------------------------------------------------------------------
# Shapes
# ---------------------------------------------------------------------------

class PreviewTool(Tool):
    """Tools that rubber-band a preview before committing to the image.

    The shape is rendered on its own layer and then blended onto the picture
    at the tool's opacity, so outline and fill never double up.
    """

    def use(self, cr, paint):
        """Set a paint as source; fun paints spread across the shape."""
        set_paint(cr, paint, self.paint_bbox())

    def paint_bbox(self):
        pts = self.control_points()
        if not pts:
            return None
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        return (min(xs), min(ys), max(xs), max(ys))

    def control_points(self):
        return []

    def compose(self, target):
        layer = imageops.new_surface(self.doc.width, self.doc.height)
        self.render(self.context(layer))
        mats = self.symmetry_transforms()
        if len(mats) > 1:
            sym = imageops.new_surface(self.doc.width, self.doc.height)
            scr = cairo.Context(sym)
            for m in mats:
                scr.set_matrix(m)
                scr.set_source_surface(layer, 0, 0)
                scr.get_source().set_filter(cairo.FILTER_NEAREST)
                scr.paint()
            layer = sym
        cr = cairo.Context(target)
        cr.set_source_surface(layer, 0, 0)
        cr.paint_with_alpha(self.state.tool_opacity(self.name))

    def show(self):
        prev = imageops.copy_surface(self.doc.surface)
        self.compose(prev)
        self.c.set_preview(prev)

    def finish(self):
        self.doc.push_undo()
        self.compose(self.doc.surface)
        self.c.set_preview(None)
        self.doc.changed()

    def cancel(self):
        self.c.set_preview(None)

    def render(self, cr):
        raise NotImplementedError


class LineTool(PreviewTool):
    name = "line"

    def press(self, x, y, button, mods):
        self.button = button
        self.start = self.end = (x, y)
        self.show()

    def drag(self, x, y, mods):
        if mods & SHIFT:
            x, y = constrain_45(self.start[0], self.start[1], x, y)
        self.end = (x, y)
        self.c.emit_size(abs(x - self.start[0]) + 1, abs(y - self.start[1]) + 1)
        self.show()

    def release(self, x, y, button, mods):
        self.drag(x, y, mods)
        self.finish()
        self.c.emit_size(None)

    def render(self, cr):
        self.use(cr, self.color(self.button))
        stamp_path(cr, bresenham(*self.start, *self.end), disc_offsets(self.state.line_width))

    def control_points(self):
        return [self.start, self.end]


def bezier_points(p0, c1, c2, p3):
    length = (math.dist(p0, c1) + math.dist(c1, c2) + math.dist(c2, p3))
    steps = max(8, int(length))
    pts = []
    for i in range(steps + 1):
        t = i / steps
        u = 1 - t
        x = u ** 3 * p0[0] + 3 * u * u * t * c1[0] + 3 * u * t * t * c2[0] + t ** 3 * p3[0]
        y = u ** 3 * p0[1] + 3 * u * u * t * c1[1] + 3 * u * t * t * c2[1] + t ** 3 * p3[1]
        p = (int(round(x)), int(round(y)))
        if not pts or pts[-1] != p:
            pts.append(p)
    out = []
    for a, b in zip(pts, pts[1:]):
        out.extend(bresenham(*a, *b))
    return out or pts


class CurveTool(PreviewTool):
    name = "curve"

    def __init__(self, canvas):
        super().__init__(canvas)
        self.stage = 0

    def is_busy(self):
        return self.stage != 0

    def press(self, x, y, button, mods):
        if self.stage == 0:
            self.button = button
            self.p0 = self.p3 = self.c1 = self.c2 = (x, y)
            self.stage = 1
        elif self.stage == 2:
            self.c1 = self.c2 = (x, y)
        elif self.stage == 3:
            self.c2 = (x, y)
        self.show()

    def drag(self, x, y, mods):
        if self.stage == 1:
            if mods & SHIFT:
                x, y = constrain_45(self.p0[0], self.p0[1], x, y)
            self.p3 = self.c1 = self.c2 = (x, y)
            self.c1 = self.p0
        elif self.stage == 2:
            self.c1 = self.c2 = (x, y)
        elif self.stage == 3:
            self.c2 = (x, y)
        self.show()

    def release(self, x, y, button, mods):
        self.drag(x, y, mods)
        if self.stage == 1:
            self.c1, self.c2 = self.p0, self.p3
            self.stage = 2
        elif self.stage == 2:
            self.stage = 3
        elif self.stage == 3:
            self.finish()
            self.stage = 0

    def commit(self):
        if self.stage:
            self.finish()
            self.stage = 0

    def cancel(self):
        self.stage = 0
        super().cancel()

    def render(self, cr):
        self.use(cr, self.color(self.button))
        stamp_path(cr, bezier_points(self.p0, self.c1, self.c2, self.p3),
                   disc_offsets(self.state.line_width))

    def control_points(self):
        return [self.p0, self.c1, self.c2, self.p3]


class BoxShapeTool(PreviewTool):
    """Rectangle, ellipse and rounded rectangle."""

    def press(self, x, y, button, mods):
        self.button = button
        self.start = self.end = (x, y)
        self.show()

    def drag(self, x, y, mods):
        if mods & SHIFT:
            x, y = constrain_square(self.start[0], self.start[1], x, y)
        self.end = (x, y)
        self.c.emit_size(abs(x - self.start[0]) + 1, abs(y - self.start[1]) + 1)
        self.show()

    def release(self, x, y, button, mods):
        self.drag(x, y, mods)
        self.finish()
        self.c.emit_size(None)

    def path(self, cr, x, y, w, h):
        raise NotImplementedError

    def control_points(self):
        return [self.start, self.end]

    def render(self, cr):
        x0, x1 = sorted((self.start[0], self.end[0]))
        y0, y1 = sorted((self.start[1], self.end[1]))
        w, h = x1 - x0 + 1, y1 - y0 + 1
        lw = self.state.line_width
        outline = self.color(self.button)
        fill = self.other_color(self.button)
        style = self.state.fill_style
        if style == 2:
            self.path(cr, x0, y0, w, h, 0)
            self.use(cr, outline)
            cr.fill()
            return
        inner_ok = w > 2 * lw and h > 2 * lw
        if style == 1:
            self.path(cr, x0, y0, w, h, 0)
            self.use(cr, outline)
            cr.fill()
            if inner_ok:
                self.path(cr, x0 + lw, y0 + lw, w - 2 * lw, h - 2 * lw, lw)
                self.use(cr, fill)
                cr.fill()
            return
        cr.set_fill_rule(cairo.FILL_RULE_EVEN_ODD)
        self.path(cr, x0, y0, w, h, 0)
        if inner_ok:
            self.path(cr, x0 + lw, y0 + lw, w - 2 * lw, h - 2 * lw, lw)
        self.use(cr, outline)
        cr.fill()


class RectangleTool(BoxShapeTool):
    name = "rectangle"

    def path(self, cr, x, y, w, h, inset):
        cr.rectangle(x, y, w, h)


class EllipseTool(BoxShapeTool):
    name = "ellipse"

    def path(self, cr, x, y, w, h, inset):
        cr.save()
        cr.translate(x + w / 2, y + h / 2)
        cr.scale(w / 2, h / 2)
        cr.new_sub_path()
        cr.arc(0, 0, 1, 0, 2 * math.pi)
        cr.restore()


class RoundedRectTool(BoxShapeTool):
    name = "rounded_rect"

    RADIUS = 8

    def path(self, cr, x, y, w, h, inset):
        r = min(self.RADIUS - inset, w / 2, h / 2)
        if r <= 0:
            cr.rectangle(x, y, w, h)
            return
        cr.new_sub_path()
        cr.arc(x + w - r, y + r, r, -math.pi / 2, 0)
        cr.arc(x + w - r, y + h - r, r, 0, math.pi / 2)
        cr.arc(x + r, y + h - r, r, math.pi / 2, math.pi)
        cr.arc(x + r, y + r, r, math.pi, 1.5 * math.pi)
        cr.close_path()


class PolygonTool(PreviewTool):
    name = "polygon"

    def __init__(self, canvas):
        super().__init__(canvas)
        self.points = []
        self.closed = False

    def is_busy(self):
        return bool(self.points)

    def press(self, x, y, button, mods):
        if not self.points:
            self.button = button
            self.points = [(x, y), (x, y)]
        else:
            self.points.append((x, y))
        self.closed = False
        self.show()

    def drag(self, x, y, mods):
        if not self.points:
            return
        if mods & SHIFT:
            x, y = constrain_45(self.points[-2][0], self.points[-2][1], x, y)
        self.points[-1] = (x, y)
        self.show()

    def release(self, x, y, button, mods):
        if not self.points:
            return
        self.drag(x, y, mods)
        first = self.points[0]
        if len(self.points) > 2 and abs(x - first[0]) <= 2 and abs(y - first[1]) <= 2:
            self.points[-1] = first
            self.close()

    def double_click(self, x, y, button):
        if len(self.points) >= 2:
            self.close()

    def close(self):
        self.closed = True
        self.finish()
        self.points = []

    def commit(self):
        if self.points:
            self.close()

    def cancel(self):
        self.points = []
        super().cancel()

    def render(self, cr):
        pts = self.points
        outline = self.color(self.button)
        fill = self.other_color(self.button)
        style = self.state.fill_style
        if self.closed and style != 0 and len(pts) >= 3:
            cr.move_to(pts[0][0] + 0.5, pts[0][1] + 0.5)
            for p in pts[1:]:
                cr.line_to(p[0] + 0.5, p[1] + 0.5)
            cr.close_path()
            self.use(cr, outline if style == 2 else fill)
            cr.fill()
            if style == 2:
                return
        seq = list(pts)
        if self.closed and seq[-1] != seq[0]:
            seq.append(seq[0])
        line = []
        for a, b in zip(seq, seq[1:]):
            line.extend(bresenham(*a, *b))
        self.use(cr, outline)
        stamp_path(cr, line or seq, disc_offsets(self.state.line_width))

    def control_points(self):
        return self.points


# ---------------------------------------------------------------------------
# Selection tools
# ---------------------------------------------------------------------------

class SelectTool(Tool):
    def __init__(self, canvas):
        super().__init__(canvas)
        self.mode = None
        self.rect = None

    def deactivate(self):
        self.c.commit_selection()

    def commit(self):
        self.c.commit_selection()

    def cancel(self):
        self.mode = None
        self.rect = None
        self.c.queue_draw()

    def hover(self, x, y):
        sel = self.c.selection
        name = self.cursor
        if sel is not None:
            h = self.c.selection_handle_at(*self.c.last_widget_pos)
            if h:
                name = {"n": "ns-resize", "s": "ns-resize", "e": "ew-resize", "w": "ew-resize",
                        "ne": "nesw-resize", "sw": "nesw-resize",
                        "nw": "nwse-resize", "se": "nwse-resize"}[h]
            elif sel.hit(x, y):
                name = "move"
        self.c.set_cursor_name(name)

    def press(self, x, y, button, mods):
        sel = self.c.selection
        if sel is not None:
            h = self.c.selection_handle_at(*self.c.last_widget_pos)
            if h and button == 1:
                self.mode = "resize"
                self.handle = h
                self.c.lift_selection()
                self.orig = (sel.x, sel.y, sel.w, sel.h)
                return
            if sel.hit(x, y):
                if button == 3:
                    self.c.show_context_menu()
                    return
                self.mode = "move"
                self.offset = (x - sel.x, y - sel.y)
                if mods & CTRL:
                    if sel.floating:
                        self.c.stamp_selection()
                    else:
                        self.c.lift_selection(erase=False)
                else:
                    self.c.lift_selection()
                return
            self.c.commit_selection()
        if button == 3:
            return
        self.mode = "new"
        self.start_new(x, y)

    def drag(self, x, y, mods):
        sel = self.c.selection
        if self.mode == "move" and sel is not None:
            sel.x = x - self.offset[0]
            sel.y = y - self.offset[1]
            if mods & SHIFT:
                self.c.stamp_selection()
            self.c.picture_changed()
        elif self.mode == "resize" and sel is not None:
            ox, oy, ow, oh = self.orig
            x0, y0, x1, y1 = ox, oy, ox + ow, oy + oh
            if "w" in self.handle:
                x0 = min(x, x1 - 1)
            if "e" in self.handle:
                x1 = max(x + 1, x0 + 1)
            if "n" in self.handle:
                y0 = min(y, y1 - 1)
            if "s" in self.handle:
                y1 = max(y + 1, y0 + 1)
            sel.x, sel.y, sel.w, sel.h = x0, y0, x1 - x0, y1 - y0
            self.c.emit_size(sel.w, sel.h)
            self.c.picture_changed()
        elif self.mode == "new":
            self.drag_new(x, y)

    def release(self, x, y, button, mods):
        if self.mode == "new":
            self.finish_new(x, y)
        self.c.emit_size(None)
        self.mode = None
        self.c.queue_draw()


class RectSelectTool(SelectTool):
    def start_new(self, x, y):
        self.start = (x, y)
        self.rect = None
        self.drag_new(x, y)

    def drag_new(self, x, y):
        x0, y0 = self.start
        x = max(0, min(x, self.doc.width - 1))
        y = max(0, min(y, self.doc.height - 1))
        x0 = max(0, min(x0, self.doc.width - 1))
        y0 = max(0, min(y0, self.doc.height - 1))
        rx0, rx1 = sorted((x0, x))
        ry0, ry1 = sorted((y0, y))
        self.rect = (rx0, ry0, rx1 - rx0 + 1, ry1 - ry0 + 1)
        self.c.emit_size(self.rect[2], self.rect[3])
        self.c.queue_draw()

    def finish_new(self, x, y):
        r = self.rect
        self.rect = None
        if r and (r[2] > 1 or r[3] > 1):
            self.c.create_selection(*r)

    def draw_overlay(self, cr):
        if self.mode == "new" and self.rect:
            x, y, w, h = self.rect
            wx, wy = self.c.to_widget(x, y)
            z = self.c.zoom
            win98.dotted_rect(cr, int(wx), int(wy), w * z, h * z, (0, 0, 0.5))


class FreeSelectTool(SelectTool):
    def start_new(self, x, y):
        self.points = [(x, y)]

    def drag_new(self, x, y):
        if self.points[-1] != (x, y):
            self.points.append((x, y))
        self.c.queue_draw()

    def finish_new(self, x, y):
        pts = self.points
        self.points = []
        if len(pts) > 2:
            self.c.create_free_selection(pts)

    def draw_overlay(self, cr):
        if self.mode == "new" and getattr(self, "points", None):
            z = self.c.zoom
            cr.set_line_width(1)
            cr.set_source_rgb(0, 0, 0)
            for i, (x, y) in enumerate(self.points):
                wx, wy = self.c.to_widget(x, y)
                fn = cr.move_to if i == 0 else cr.line_to
                fn(wx + z / 2, wy + z / 2)
            cr.stroke()


# ---------------------------------------------------------------------------
# Text
# ---------------------------------------------------------------------------

class TextTool(Tool):
    name = "text"
    cursor = "text"
    has_text_input = True
    MIN_W, MIN_H = 30, 12

    def __init__(self, canvas):
        super().__init__(canvas)
        self.box = None  # [x, y, w, h]
        self.text = ""
        self.dragging = None
        self._surface = None

    def is_busy(self):
        return self.box is not None

    def font_description(self):
        st = self.state
        fd = Pango.FontDescription()
        fd.set_family(st.font_family)
        fd.set_absolute_size(st.font_size * Pango.SCALE * 96 / 72)
        fd.set_weight(Pango.Weight.BOLD if st.font_bold else Pango.Weight.NORMAL)
        fd.set_style(Pango.Style.ITALIC if st.font_italic else Pango.Style.NORMAL)
        return fd

    def make_layout(self, cr):
        layout = PangoCairo.create_layout(cr)
        fo = cairo.FontOptions()
        fo.set_antialias(cairo.ANTIALIAS_NONE)
        fo.set_hint_style(cairo.HINT_STYLE_FULL)
        PangoCairo.context_set_font_options(layout.get_context(), fo)
        layout.set_font_description(self.font_description())
        layout.set_width(max(1, self.box[2]) * Pango.SCALE)
        layout.set_wrap(Pango.WrapMode.WORD_CHAR)
        attrs = Pango.AttrList()
        if self.state.font_underline:
            attrs.insert(Pango.attr_underline_new(Pango.Underline.SINGLE))
        layout.set_attributes(attrs)
        layout.set_text(self.text, -1)
        return layout

    def render_surface(self):
        x, y, w, h = self.box
        surf = imageops.new_surface(w, h)
        cr = cairo.Context(surf)
        if not self.state.transparent:
            set_rgb(cr, self.state.bg)
            cr.paint()
        layout = self.make_layout(cr)
        set_paint(cr, self.state.fg, (0, 0, w - 1, h - 1))
        PangoCairo.show_layout(cr, layout)
        return surf, layout

    def refresh(self):
        if self.box is None:
            return
        surf, layout = self.render_surface()
        _, logical = layout.get_pixel_extents()
        need = logical.height
        if need > self.box[3] and self.box[1] + need <= self.doc.height:
            self.box[3] = need
            surf, layout = self.render_surface()
        self._surface = surf
        self._layout = layout
        self.c.queue_draw()

    def options_changed(self):
        self.refresh()

    def press(self, x, y, button, mods):
        if self.box is not None:
            bx, by, bw, bh = self.box
            if bx <= x < bx + bw and by <= y < by + bh:
                return
            self.commit()
            return
        if button != 1:
            return
        self.dragging = [x, y, x, y]
        self.c.queue_draw()

    def drag(self, x, y, mods):
        if self.dragging:
            self.dragging[2:] = [x, y]
            d = self.dragging
            self.c.emit_size(abs(d[2] - d[0]) + 1, abs(d[3] - d[1]) + 1)
            self.c.queue_draw()

    def release(self, x, y, button, mods):
        if not self.dragging:
            return
        x0, y0, x1, y1 = self.dragging
        self.dragging = None
        self.c.emit_size(None)
        x0, x1 = sorted((x0, x1))
        y0, y1 = sorted((y0, y1))
        x0 = max(0, x0)
        y0 = max(0, y0)
        w = max(self.MIN_W, x1 - x0 + 1)
        h = max(self.MIN_H, y1 - y0 + 1)
        if x0 >= self.doc.width or y0 >= self.doc.height:
            return
        w = min(w, self.doc.width - x0)
        h = min(h, self.doc.height - y0)
        self.box = [x0, y0, w, h]
        self.text = ""
        self.c.text_box_changed()
        self.refresh()
        self.c.grab_focus()

    def commit(self):
        if self.box is None:
            return
        if self.text.strip():
            surf, _ = self.render_surface()
            self.doc.push_undo()
            cr = cairo.Context(self.doc.surface)
            cr.set_source_surface(surf, self.box[0], self.box[1])
            cr.paint_with_alpha(self.state.tool_opacity("text"))
            self.doc.changed()
        self.box = None
        self.text = ""
        self._surface = None
        self.c.text_box_changed()
        self.c.queue_draw()

    def cancel(self):
        self.dragging = None
        self.c.queue_draw()

    def insert(self, s):
        if self.box is None:
            return
        self.text += s
        self.refresh()

    def key_press(self, ev):
        if self.box is None:
            return False
        if ev.keyval == Gdk.KEY_BackSpace:
            self.text = self.text[:-1]
            self.refresh()
            return True
        if ev.keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter):
            self.insert("\n")
            return True
        if ev.keyval == Gdk.KEY_Escape:
            self.commit()
            return True
        return False

    def draw_image_layer(self, cr):
        if self.box is not None and self._surface is not None:
            cr.set_source_surface(self._surface, self.box[0], self.box[1])
            cr.get_source().set_filter(cairo.FILTER_NEAREST)
            cr.paint_with_alpha(self.state.tool_opacity("text"))

    def draw_overlay(self, cr):
        z = self.c.zoom
        if self.dragging:
            x0, y0, x1, y1 = self.dragging
            x0, x1 = sorted((x0, x1))
            y0, y1 = sorted((y0, y1))
            wx, wy = self.c.to_widget(x0, y0)
            win98.dotted_rect(cr, int(wx), int(wy), (x1 - x0 + 1) * z, (y1 - y0 + 1) * z, (0, 0, 0.5))
        if self.box is not None:
            x, y, w, h = self.box
            wx, wy = self.c.to_widget(x, y)
            win98.dotted_rect(cr, int(wx) - 1, int(wy) - 1, w * z + 2, h * z + 2, (0, 0, 0.5))
            if self.c.has_focus() and getattr(self, "_layout", None) is not None:
                idx = len(self.text.encode("utf-8"))
                strong, _ = self._layout.get_cursor_pos(idx)
                cx = x + strong.x / Pango.SCALE
                cy = y + strong.y / Pango.SCALE
                ch = max(1, strong.height / Pango.SCALE)
                wx, wy = self.c.to_widget(min(cx, x + w - 1), cy)
                cr.set_source_rgb(0, 0, 0)
                cr.rectangle(int(wx), int(wy), max(1, z), ch * z)
                cr.fill()


class MagicWandTool(SelectTool):
    """Click to select an area of similar colour (Fill's tolerance).
    Shift+click adds another area; options choose touching or all."""
    name = "magic_wand"
    cursor = "magic_wand"

    def press(self, x, y, button, mods):
        sel = self.c.selection
        if button == 1 and mods & SHIFT and sel is not None and not sel.floating:
            self.mode = None
            self.select_at(x, y, add=True)
            return
        super().press(x, y, button, mods)

    def start_new(self, x, y):
        self.select_at(x, y)

    def select_at(self, x, y, add=False):
        st = self.state
        find = imageops.similar_mask if st.wand_global else imageops.region_mask
        res = find(self.doc.surface, x, y, st.tolerance)
        if res is None:
            return
        mask, bbox = res
        self.c.create_mask_selection(mask, bbox, add=add)
        sel = self.c.selection
        if sel is not None:
            self.c.emit_size(sel.w, sel.h)

    def drag_new(self, x, y):
        pass

    def finish_new(self, x, y):
        pass


class StickerTool(Tool):
    """Stamps the current sticker centred on the pointer; dragging stamps a
    trail. Uses the Size and Opacity sliders and repeats with Symmetry."""
    name = "sticker"
    cursor = "none"

    def __init__(self, canvas):
        super().__init__(canvas)
        self.pos = None
        self.layer = None

    def image(self):
        return stickers.render(self.state.sticker, self.state.sticker_size)

    def press(self, x, y, button, mods):
        if button != 1:
            return
        self.doc.push_undo()
        self.base = self.doc.undo_stack[-1]
        self.layer = imageops.new_surface(self.doc.width, self.doc.height)
        self.last = None
        self.stamp(x, y)

    def drag(self, x, y, mods):
        self.pos = (x, y)
        if self.layer is None:
            return
        spacing = max(4, self.state.sticker_size * 0.8)
        # Fill the path evenly, however fast the pointer moved.
        while math.dist(self.last, (x, y)) >= spacing:
            lx, ly = self.last
            d = math.dist(self.last, (x, y))
            self.stamp(round(lx + (x - lx) * spacing / d), round(ly + (y - ly) * spacing / d))

    def release(self, x, y, button, mods):
        self.layer = None

    def cancel(self):
        self.layer = None

    def stamp(self, x, y):
        img = self.image()
        size = img.get_width()
        lcr = cairo.Context(self.layer)
        lcr.set_source_surface(img, x - size // 2, y - size // 2)
        lcr.paint()
        self.last = (x, y)
        cr = cairo.Context(self.doc.surface)
        cr.set_operator(cairo.OPERATOR_SOURCE)
        cr.set_source_surface(self.base, 0, 0)
        cr.paint()
        cr.set_operator(cairo.OPERATOR_OVER)
        alpha = self.state.tool_opacity("sticker")
        for m in self.symmetry_transforms():
            cr.set_matrix(m)
            cr.set_source_surface(self.layer, 0, 0)
            cr.get_source().set_filter(cairo.FILTER_NEAREST)
            cr.paint_with_alpha(alpha)
        self.doc.changed()

    def hover(self, x, y):
        self.pos = (x, y)
        self.c.queue_draw()

    def leave(self):
        self.pos = None
        self.c.queue_draw()

    def draw_image_layer(self, cr):
        if self.pos is None or self.layer is not None:
            return
        img = self.image()
        size = img.get_width()
        cr.set_source_surface(img, self.pos[0] - size // 2, self.pos[1] - size // 2)
        cr.get_source().set_filter(cairo.FILTER_NEAREST)
        cr.paint_with_alpha(0.6)


TOOL_CLASSES = {
    "free_select": FreeSelectTool,
    "rect_select": RectSelectTool,
    "eraser": EraserTool,
    "fill": FillTool,
    "pick": PickTool,
    "magnifier": MagnifierTool,
    "pencil": PencilTool,
    "brush": BrushTool,
    "airbrush": AirbrushTool,
    "text": TextTool,
    "line": LineTool,
    "curve": CurveTool,
    "rectangle": RectangleTool,
    "polygon": PolygonTool,
    "ellipse": EllipseTool,
    "rounded_rect": RoundedRectTool,
    "magic_wand": MagicWandTool,
    "sticker": StickerTool,
}
