"""Pixel level operations on cairo ARGB32 image surfaces."""

import math
from array import array

import cairo


def rgb_to_pixel(rgb):
    r, g, b = rgb
    return 0xFF000000 | (r << 16) | (g << 8) | b


def pixel_to_rgb(p):
    return ((p >> 16) & 0xFF, (p >> 8) & 0xFF, p & 0xFF)


def new_surface(w, h, fill=None):
    s = cairo.ImageSurface(cairo.FORMAT_ARGB32, max(1, w), max(1, h))
    if fill is not None:
        cr = cairo.Context(s)
        set_rgb(cr, fill)
        cr.paint()
    return s


def copy_surface(src, x=0, y=0, w=None, h=None):
    if w is None:
        w = src.get_width()
    if h is None:
        h = src.get_height()
    s = cairo.ImageSurface(cairo.FORMAT_ARGB32, max(1, w), max(1, h))
    cr = cairo.Context(s)
    cr.set_operator(cairo.OPERATOR_SOURCE)
    cr.set_source_surface(src, -x, -y)
    cr.paint()
    return s


def set_rgb(cr, rgb):
    cr.set_source_rgb(rgb[0] / 255, rgb[1] / 255, rgb[2] / 255)


def _pixels(surf):
    surf.flush()
    return surf.get_data().cast("I"), surf.get_stride() // 4


def get_pixel(surf, x, y):
    if not (0 <= x < surf.get_width() and 0 <= y < surf.get_height()):
        return None
    px, sw = _pixels(surf)
    return pixel_to_rgb(px[y * sw + x])


def flood_fill(surf, x, y, rgb):
    w, h = surf.get_width(), surf.get_height()
    if not (0 <= x < w and 0 <= y < h):
        return False
    px, sw = _pixels(surf)
    target = px[y * sw + x]
    new = rgb_to_pixel(rgb)
    if target == new:
        return False
    stack = [(x, y)]
    while stack:
        x, y = stack.pop()
        row = y * sw
        if px[row + x] != target:
            continue
        lx = x
        while lx > 0 and px[row + lx - 1] == target:
            lx -= 1
        rx = x
        while rx < w - 1 and px[row + rx + 1] == target:
            rx += 1
        px[row + lx:row + rx + 1] = array("I", [new]) * (rx - lx + 1)
        for ny in (y - 1, y + 1):
            if 0 <= ny < h:
                nrow = ny * sw
                inside = False
                for i in range(lx, rx + 1):
                    if px[nrow + i] == target:
                        if not inside:
                            stack.append((i, ny))
                            inside = True
                    else:
                        inside = False
    surf.mark_dirty()
    return True


def replace_color(surf, x0, y0, x1, y1, src_rgb, dst_rgb):
    """Replace src colour by dst colour inside the given (inclusive) box."""
    w, h = surf.get_width(), surf.get_height()
    x0, y0 = max(0, x0), max(0, y0)
    x1, y1 = min(w - 1, x1), min(h - 1, y1)
    if x0 > x1 or y0 > y1:
        return
    px, sw = _pixels(surf)
    src = rgb_to_pixel(src_rgb)
    dst = rgb_to_pixel(dst_rgb)
    for y in range(y0, y1 + 1):
        row = y * sw
        seg = px[row + x0:row + x1 + 1].tolist()
        if src in seg:
            px[row + x0:row + x1 + 1] = array("I", [dst if v == src else v for v in seg])
    surf.mark_dirty()


def key_out(surf, rgb):
    """Return a copy of surf where pixels of colour rgb are transparent."""
    out = copy_surface(surf)
    px, sw = _pixels(out)
    key = rgb_to_pixel(rgb)
    vals = px.tolist()
    if key in vals:
        px[:] = array("I", [0 if v == key else v for v in vals])
        out.mark_dirty()
    return out


def flip(surf, horizontal):
    w, h = surf.get_width(), surf.get_height()
    out = cairo.ImageSurface(cairo.FORMAT_ARGB32, w, h)
    cr = cairo.Context(out)
    if horizontal:
        cr.set_matrix(cairo.Matrix(-1, 0, 0, 1, w, 0))
    else:
        cr.set_matrix(cairo.Matrix(1, 0, 0, -1, 0, h))
    cr.set_source_surface(surf, 0, 0)
    cr.get_source().set_filter(cairo.FILTER_NEAREST)
    cr.set_operator(cairo.OPERATOR_SOURCE)
    cr.paint()
    return out


def rotate(surf, degrees):
    w, h = surf.get_width(), surf.get_height()
    degrees %= 360
    if degrees == 180:
        nw, nh, m = w, h, cairo.Matrix(-1, 0, 0, -1, w, h)
    elif degrees == 90:  # clockwise
        nw, nh, m = h, w, cairo.Matrix(0, 1, -1, 0, h, 0)
    elif degrees == 270:
        nw, nh, m = h, w, cairo.Matrix(0, -1, 1, 0, 0, w)
    else:
        return copy_surface(surf)
    out = cairo.ImageSurface(cairo.FORMAT_ARGB32, nw, nh)
    cr = cairo.Context(out)
    cr.set_matrix(m)
    cr.set_source_surface(surf, 0, 0)
    cr.get_source().set_filter(cairo.FILTER_NEAREST)
    cr.set_operator(cairo.OPERATOR_SOURCE)
    cr.paint()
    return out


def scale(surf, nw, nh):
    nw, nh = max(1, int(nw)), max(1, int(nh))
    w, h = surf.get_width(), surf.get_height()
    out = cairo.ImageSurface(cairo.FORMAT_ARGB32, nw, nh)
    cr = cairo.Context(out)
    cr.scale(nw / w, nh / h)
    cr.set_source_surface(surf, 0, 0)
    pat = cr.get_source()
    pat.set_filter(cairo.FILTER_NEAREST)
    pat.set_extend(cairo.EXTEND_PAD)
    cr.set_operator(cairo.OPERATOR_SOURCE)
    cr.paint()
    return out


def skew(surf, deg_h, deg_v, bg=None):
    """Skew by the given angles (degrees). bg=None leaves new area transparent."""
    w, h = surf.get_width(), surf.get_height()
    th = math.tan(math.radians(deg_h))
    tv = math.tan(math.radians(deg_v))
    # Map corners to find the bounding box.
    xs, ys = [], []
    for (x, y) in ((0, 0), (w, 0), (0, h), (w, h)):
        xs.append(x + th * y)
        ys.append(y + tv * x)
    minx, miny = min(xs), min(ys)
    nw = int(math.ceil(max(xs) - minx))
    nh = int(math.ceil(max(ys) - miny))
    out = new_surface(nw, nh, bg)
    cr = cairo.Context(out)
    cr.set_antialias(cairo.ANTIALIAS_NONE)
    cr.set_matrix(cairo.Matrix(1, tv, th, 1, -minx, -miny))
    cr.set_source_surface(surf, 0, 0)
    cr.get_source().set_filter(cairo.FILTER_NEAREST)
    cr.rectangle(0, 0, w, h)
    cr.fill()
    return out


def invert(surf):
    """Invert colours in place (keeps alpha)."""
    px, sw = _pixels(surf)
    vals = px.tolist()
    px[:] = array("I", [(v ^ 0x00FFFFFF) if (v >> 24) == 0xFF else (0 if v == 0 else v) for v in vals])
    surf.mark_dirty()


def to_black_and_white(surf):
    px, sw = _pixels(surf)
    out = []
    for v in px.tolist():
        if (v >> 24) == 0:
            out.append(v)
            continue
        r, g, b = pixel_to_rgb(v)
        lum = (r * 299 + g * 587 + b * 114) // 1000
        out.append(0xFFFFFFFF if lum >= 128 else 0xFF000000)
    px[:] = array("I", out)
    surf.mark_dirty()


def bresenham(x0, y0, x1, y1):
    pts = []
    dx = abs(x1 - x0)
    dy = -abs(y1 - y0)
    sx = 1 if x0 < x1 else -1
    sy = 1 if y0 < y1 else -1
    err = dx + dy
    while True:
        pts.append((x0, y0))
        if x0 == x1 and y0 == y1:
            break
        e2 = 2 * err
        if e2 >= dy:
            err += dy
            x0 += sx
        if e2 <= dx:
            err += dx
            y0 += sy
    return pts


def disc_offsets(d):
    """Pixel offsets of a filled disc with diameter d centred on (0,0)."""
    if d <= 1:
        return [(0, 0)]
    r = d / 2
    c = (d - 1) / 2
    off = []
    for y in range(d):
        for x in range(d):
            if (x - c) ** 2 + (y - c) ** 2 <= r * r - 0.25 * (d > 2):
                off.append((x - d // 2, y - d // 2))
    return off


def square_offsets(d):
    return [(x - d // 2, y - d // 2) for y in range(d) for x in range(d)]


def stamp_path(cr, points, offsets):
    """Fill offsets around every point; points are pixel coordinates."""
    seen = set()
    for (px, py) in points:
        for (ox, oy) in offsets:
            p = (px + ox, py + oy)
            if p not in seen:
                seen.add(p)
                cr.rectangle(p[0], p[1], 1, 1)
    cr.fill()


# ---------------------------------------------------------------------------
# Masks: regions with tolerance, colour matches
# ---------------------------------------------------------------------------

def new_mask(w, h):
    return cairo.ImageSurface(cairo.FORMAT_A8, max(1, w), max(1, h))


def bytes_to_mask(data, w, h):
    """Turn w*h bytes (0 or 255) into an A8 surface."""
    mask = new_mask(w, h)
    stride = mask.get_stride()
    buf = mask.get_data()
    if stride == w:
        buf[:w * h] = data
    else:
        for y in range(h):
            buf[y * stride:y * stride + w] = data[y * w:(y + 1) * w]
    mask.mark_dirty()
    return mask


def _matcher(target, tolerance):
    """Bytes(1/0) flags of which pixel values are within tolerance (0..100%)."""
    t = round(tolerance * 255 / 100)
    if t <= 0:
        return lambda vals: bytearray(map(target.__eq__, vals))
    if t >= 255:
        return lambda vals: bytearray(b"\x01") * len(vals)
    tr, tg, tb = pixel_to_rgb(target)
    okr = [abs(i - tr) <= t for i in range(256)]
    okg = [abs(i - tg) <= t for i in range(256)]
    okb = [abs(i - tb) <= t for i in range(256)]
    return lambda vals: bytearray([okr[(v >> 16) & 255] and okg[(v >> 8) & 255] and okb[v & 255]
                                   for v in vals])


def region_mask(surf, x, y, tolerance=0):
    """Contiguous area around (x, y) whose colour is within tolerance of the
    clicked pixel. Returns (A8 mask, (x0, y0, x1, y1)) or None."""
    w, h = surf.get_width(), surf.get_height()
    if not (0 <= x < w and 0 <= y < h):
        return None
    px, sw = _pixels(surf)
    vals = px.tolist()
    if sw != w:  # never for ARGB32, but keep the rows tight anyway
        vals = [v for r in range(h) for v in vals[r * sw:r * sw + w]]
    m = _matcher(vals[y * w + x], tolerance)(vals)
    out = bytearray(w * h)
    x0, y0, x1, y1 = x, y, x, y
    stack = [(x, y)]
    while stack:
        sx, sy = stack.pop()
        row = sy * w
        if not m[row + sx]:
            continue
        lx = m.rfind(0, row, row + sx)
        lx = row if lx < 0 else lx + 1
        rx = m.find(0, row + sx, row + w)
        rx = row + w if rx < 0 else rx
        n = rx - lx
        m[lx:rx] = bytes(n)
        out[lx:rx] = b"\xff" * n
        x0 = min(x0, lx - row)
        x1 = max(x1, rx - row - 1)
        y0 = min(y0, sy)
        y1 = max(y1, sy)
        for ny in (sy - 1, sy + 1):
            if 0 <= ny < h:
                nrow = ny * w
                s, e = lx - row + nrow, rx - row + nrow
                i = m.find(1, s, e)
                while i != -1:
                    stack.append((i - nrow, ny))
                    j = m.find(0, i, e)
                    if j == -1:
                        break
                    i = m.find(1, j, e)
    return bytes_to_mask(bytes(out), w, h), (x0, y0, x1, y1)


def color_mask(surf, rgb):
    """A8 mask of every pixel exactly equal to rgb."""
    w, h = surf.get_width(), surf.get_height()
    px, sw = _pixels(surf)
    key = rgb_to_pixel(rgb)
    data = bytes(255 if v == key else 0 for v in px.tolist())
    return bytes_to_mask(data, w, h)


def similar_mask(surf, x, y, tolerance=0):
    """Every pixel in the picture within tolerance of the colour at (x, y),
    touching or not. Returns (A8 mask, (x0, y0, x1, y1)) or None."""
    w, h = surf.get_width(), surf.get_height()
    if not (0 <= x < w and 0 <= y < h):
        return None
    px, sw = _pixels(surf)
    vals = px.tolist()
    if sw != w:
        vals = [v for r in range(h) for v in vals[r * sw:r * sw + w]]
    m = _matcher(vals[y * w + x], tolerance)(vals)
    data = bytes(m).replace(b"\x01", b"\xff")
    rows = [r for r in range(h) if data.find(b"\xff", r * w, (r + 1) * w) != -1]
    if not rows:
        return None
    x0 = min(data.find(b"\xff", r * w, (r + 1) * w) - r * w for r in rows)
    x1 = max(data.rfind(b"\xff", r * w, (r + 1) * w) - r * w for r in rows)
    return bytes_to_mask(data, w, h), (x0, rows[0], x1, rows[-1])


def alpha_mask(surf):
    """A8 copy of a surface's alpha channel."""
    a = new_mask(surf.get_width(), surf.get_height())
    cr = cairo.Context(a)
    cr.set_operator(cairo.OPERATOR_SOURCE)
    cr.set_source_surface(surf, 0, 0)
    cr.paint()
    return a


def alpha_edges(surf):
    """A8 mask of the outline pixels of a surface's opaque area."""
    a = alpha_mask(surf)
    eroded = alpha_mask(surf)
    cr = cairo.Context(eroded)
    cr.set_operator(cairo.OPERATOR_IN)
    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        cr.set_source_surface(a, dx, dy)
        cr.paint()
    cr = cairo.Context(a)
    cr.set_operator(cairo.OPERATOR_DEST_OUT)
    cr.set_source_surface(eroded, 0, 0)
    cr.paint()
    return a
