"""Pixel level operations on cairo ARGB32 image surfaces."""

import math
import sys

import cairo


def rgb_to_pixel(rgb):
    r, g, b = rgb
    return 0xFF000000 | (r << 16) | (g << 8) | b


def pixel_to_rgb(p):
    return ((p >> 16) & 0xFF, (p >> 8) & 0xFF, p & 0xFF)


def new_surface(w, h, fill=None):
    check_size(w, h)
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


# Byte offsets of B, G, R, A inside a native-endian ARGB32 pixel.
_B, _G, _R, _A = (0, 1, 2, 3) if sys.byteorder == "little" else (3, 2, 1, 0)
_ONE_TO_FF = bytes([0, 255] + [255] * 254)

# Largest picture Paint98 will create (cairo's hard limit is 32767 a side).
MAX_SIDE = 16000
MAX_PIXELS = 80_000_000


class TooBig(ValueError):
    pass


def check_size(w, h):
    if w > MAX_SIDE or h > MAX_SIDE or w * h > MAX_PIXELS:
        raise TooBig("The picture would be %d x %d pixels, which is too big "
                     "(the limit is %d pixels on a side)." % (w, h, MAX_SIDE))


def _plane_bytes(surf):
    """Pixel bytes without row padding (4 * width * height)."""
    surf.flush()
    w, h, stride = surf.get_width(), surf.get_height(), surf.get_stride()
    raw = bytes(surf.get_data())
    if stride == 4 * w:
        return raw
    return b"".join(raw[y * stride:y * stride + 4 * w] for y in range(h))


def _write_plane_bytes(surf, data):
    w, h, stride = surf.get_width(), surf.get_height(), surf.get_stride()
    buf = surf.get_data()
    if stride == 4 * w:
        buf[:len(data)] = data
    else:
        for y in range(h):
            buf[y * stride:y * stride + 4 * w] = data[y * 4 * w:(y + 1) * 4 * w]
    surf.mark_dirty()


def _pixels(surf):
    surf.flush()
    return surf.get_data().cast("I"), surf.get_stride() // 4


def get_pixel(surf, x, y):
    if not (0 <= x < surf.get_width() and 0 <= y < surf.get_height()):
        return None
    px, sw = _pixels(surf)
    return pixel_to_rgb(px[y * sw + x])


def key_out(surf, rgb):
    """Return a copy of surf where pixels of colour rgb are transparent."""
    out = copy_surface(surf)
    cr = cairo.Context(out)
    cr.set_operator(cairo.OPERATOR_DEST_OUT)
    cr.set_source_rgba(0, 0, 0, 1)
    cr.mask_surface(color_mask(surf, rgb), 0, 0)
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
    check_size(nw, nh)
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


def _shear_offsets(t, n):
    """Whole-pixel shift of each of n rows (or columns) for a shear by t,
    made non-negative, plus how much wider (or taller) that makes the result."""
    offs = [math.floor(t * (i + 0.5)) for i in range(n)]
    lo = min(offs)
    return [o - lo for o in offs], max(offs) - lo


def skew(surf, deg_h, deg_v, bg=None):
    """Skew horizontally, then vertically (like the original program).

    Each row, then each column, moves by a whole number of pixels, so no
    pixel is lost or doubled at any angle. bg=None leaves the new corners
    transparent."""
    w, h = surf.get_width(), surf.get_height()
    dxs, grow_w = _shear_offsets(math.tan(math.radians(deg_h)), h)
    nw = w + grow_w
    dys, grow_h = _shear_offsets(math.tan(math.radians(deg_v)), nw)
    nh = h + grow_h
    check_size(nw, nh)
    rows = new_surface(nw, h)
    cr = cairo.Context(rows)
    for y, dx in enumerate(dxs):
        cr.set_source_surface(surf, dx, 0)
        cr.rectangle(dx, y, w, 1)
        cr.fill()
    out = new_surface(nw, nh, bg)
    cr = cairo.Context(out)
    for x, dy in enumerate(dys):
        cr.set_source_surface(rows, 0, dy)
        cr.rectangle(x, dy, 1, h)
        cr.fill()
    return out


def invert(surf):
    """Invert colours in place, keeping alpha.

    With premultiplied alpha the inverse of a channel c is (alpha - c); doing
    that subtraction on whole channel planes as big integers never borrows
    (c <= alpha), so it runs at C speed even on huge pictures."""
    data = bytearray(_plane_bytes(surf))
    n = len(data) // 4
    alpha = int.from_bytes(data[_A::4], "little")
    for off in (_B, _G, _R):
        chan = int.from_bytes(data[off::4], "little")
        data[off::4] = (alpha - chan).to_bytes(n, "little")
    _write_plane_bytes(surf, data)


def to_black_and_white(surf):
    """Threshold every pixel to black or white by brightness (keeps alpha)."""
    w, h = surf.get_width(), surf.get_height()
    orig = _plane_bytes(surf)
    # Let cairo compute the luminosity (desaturate), then threshold it.
    gray = copy_surface(surf)
    cr = cairo.Context(gray)
    cr.set_operator(cairo.OPERATOR_HSL_SATURATION)
    cr.set_source_rgb(0.5, 0.5, 0.5)
    cr.paint()
    lum = _plane_bytes(gray)[_G::4]
    alpha = orig[_A::4]
    thr = bytes(255 if i >= 128 else 0 for i in range(256))
    opaque_mask = alpha.translate(bytes([0] + [255] * 255))
    value = (int.from_bytes(lum.translate(thr), "little")
             & int.from_bytes(opaque_mask, "little")).to_bytes(w * h, "little")
    out = bytearray(orig)
    for off in (_B, _G, _R):
        out[off::4] = value
    # Semi-transparent pixels: decide on the un-premultiplied colour.
    partial = alpha.translate(bytes([0] + [1] * 254 + [0]))
    i = partial.find(1)
    while i != -1:
        a = alpha[i]
        r, g, b = (orig[4 * i + o] * 255 // a for o in (_R, _G, _B))
        v = a if (r * 299 + g * 587 + b * 114) // 1000 >= 128 else 0
        for off in (_B, _G, _R):
            out[4 * i + off] = v
        i = partial.find(1, i + 1)
    _write_plane_bytes(surf, out)


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


def _match_bytes(surf, target, tolerance):
    """bytes with 1 where a pixel is within tolerance (0..100%) of the
    target ARGB value on every channel, else 0. Works on whole channel
    planes with bytes.translate and big-integer AND (C speed)."""
    t = round(tolerance * 255 / 100)
    data = _plane_bytes(surf)
    n = len(data) // 4
    if t >= 255:
        return bytearray(b"\x01") * n
    want = {_A: (target >> 24) & 255, _R: (target >> 16) & 255,
            _G: (target >> 8) & 255, _B: target & 255}
    acc = None
    for off, v in want.items():
        table = bytes(1 if abs(i - v) <= t else 0 for i in range(256))
        plane = int.from_bytes(data[off::4].translate(table), "little")
        acc = plane if acc is None else acc & plane
    return bytearray(acc.to_bytes(n, "little"))


def region_mask(surf, x, y, tolerance=0):
    """Contiguous area around (x, y) whose colour is within tolerance of the
    clicked pixel. Returns (A8 mask, (x0, y0, x1, y1)) or None."""
    w, h = surf.get_width(), surf.get_height()
    if not (0 <= x < w and 0 <= y < h):
        return None
    px, sw = _pixels(surf)
    m = _match_bytes(surf, px[y * sw + x], tolerance)
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
    m = _match_bytes(surf, rgb_to_pixel(rgb), 0)
    return bytes_to_mask(bytes(m).translate(_ONE_TO_FF), surf.get_width(), surf.get_height())


def similar_mask(surf, x, y, tolerance=0):
    """Every pixel in the picture within tolerance of the colour at (x, y),
    touching or not. Returns (A8 mask, (x0, y0, x1, y1)) or None."""
    w, h = surf.get_width(), surf.get_height()
    if not (0 <= x < w and 0 <= y < h):
        return None
    px, sw = _pixels(surf)
    data = bytes(_match_bytes(surf, px[y * sw + x], tolerance)).translate(_ONE_TO_FF)
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
