"""A small animated GIF writer in pure Python.

Frames are cairo ARGB32 surfaces of the same size. Colours are reduced to a
shared 256-colour palette (exact when the drawing uses few colours, median
cut otherwise), and each frame only stores the rectangle that changed since
the previous one, which keeps drawings-in-progress small and fast to encode.
"""

import struct
from collections import Counter


def _pixels(surf):
    surf.flush()
    w, h = surf.get_width(), surf.get_height()
    px = surf.get_data().cast("I")
    sw = surf.get_stride() // 4
    vals = px.tolist()
    if sw != w:
        vals = [v for r in range(h) for v in vals[r * sw:r * sw + w]]
    # Drop alpha: the picture is opaque.
    return [v & 0xFFFFFF for v in vals]


# ---------------------------------------------------------------------------
# Palette
# ---------------------------------------------------------------------------

def _median_cut(hist, n=256):
    """hist: list of (rgb_int, count). Returns (palette, colour->index).

    Each box's channel spread is computed once, when the box is created, so
    the cost is about n * (number of colours) instead of n^2 * colours."""

    def make_box(items):
        best_rng, best_shift = -1, 0
        for shift in (16, 8, 0):
            vals = [(c >> shift) & 255 for c, _ in items]
            rng = max(vals) - min(vals)
            if rng > best_rng:
                best_rng, best_shift = rng, shift
        return [best_rng if len(items) > 1 else 0, best_shift, items]

    boxes = [make_box(list(hist))]
    while len(boxes) < n:
        i = max(range(len(boxes)), key=lambda k: boxes[k][0])
        score, shift, box = boxes[i]
        if score <= 0:
            break
        boxes.pop(i)
        box.sort(key=lambda e: (e[0] >> shift) & 255)
        total = sum(cnt for _, cnt in box)
        acc, cut = 0, 1
        for j, (_, cnt) in enumerate(box):
            acc += cnt
            if acc >= total / 2:
                cut = max(1, min(len(box) - 1, j + 1))
                break
        boxes += [make_box(box[:cut]), make_box(box[cut:])]
    palette, mapping = [], {}
    for idx, (_, _, box) in enumerate(boxes):
        total = sum(cnt for _, cnt in box) or 1
        r = sum(((c >> 16) & 255) * cnt for c, cnt in box) // total
        g = sum(((c >> 8) & 255) * cnt for c, cnt in box) // total
        b = sum((c & 255) * cnt for c, cnt in box) // total
        palette.append((r << 16) | (g << 8) | b)
        for c, _ in box:
            mapping[c] = idx
    return palette, mapping


# Above this many distinct colours (photos), colours are first grouped into
# 15-bit buckets so building the palette stays fast.
_REDUCE_ABOVE = 4096
_REDUCE_MASK = 0xF8F8F8


def build_palette(counter):
    """Returns (palette, index_of) where index_of maps a colour to an index."""
    if len(counter) <= 256:
        palette = list(counter)
        exact = {c: i for i, c in enumerate(palette)}
        return palette, exact.__getitem__
    if len(counter) > _REDUCE_ABOVE:
        reduced = Counter()
        for c, cnt in counter.items():
            reduced[c & _REDUCE_MASK] += cnt
        palette, mapping = _median_cut(reduced.most_common())
        return palette, lambda c: mapping[c & _REDUCE_MASK]
    palette, mapping = _median_cut(counter.most_common())
    return palette, mapping.__getitem__


def _nearest(palette, c):
    r, g, b = (c >> 16) & 255, (c >> 8) & 255, c & 255
    best, bi = None, 0
    for i, p in enumerate(palette):
        d = (((p >> 16) & 255) - r) ** 2 + (((p >> 8) & 255) - g) ** 2 + ((p & 255) - b) ** 2
        if best is None or d < best:
            best, bi = d, i
    return bi


# ---------------------------------------------------------------------------
# LZW
# ---------------------------------------------------------------------------

def lzw_encode(data, min_size=8):
    clear = 1 << min_size
    eoi = clear + 1
    out = bytearray()
    bitbuf = 0
    bitcount = 0
    code_size = min_size + 1
    next_code = eoi + 1
    table = {}

    def emit(code, size):
        nonlocal bitbuf, bitcount
        bitbuf |= code << bitcount
        bitcount += size
        while bitcount >= 8:
            out.append(bitbuf & 0xFF)
            bitbuf >>= 8
            bitcount -= 8

    emit(clear, code_size)
    if not data:
        emit(eoi, code_size)
        if bitcount:
            out.append(bitbuf & 0xFF)
        return bytes(out)
    prefix = data[0]
    get = table.get
    for b in data[1:] if isinstance(data, list) else memoryview(data)[1:]:
        key = (prefix << 8) | b
        code = get(key)
        if code is not None:
            prefix = code
            continue
        emit(prefix, code_size)
        if next_code < 4096:
            table[key] = next_code
            next_code += 1
            if next_code > (1 << code_size) and code_size < 12:
                code_size += 1
        else:
            emit(clear, code_size)
            table.clear()
            code_size = min_size + 1
            next_code = eoi + 1
        prefix = b
    emit(prefix, code_size)
    emit(eoi, code_size)
    if bitcount:
        out.append(bitbuf & 0xFF)
    return bytes(out)


def _sub_blocks(data):
    out = bytearray()
    for i in range(0, len(data), 255):
        chunk = data[i:i + 255]
        out.append(len(chunk))
        out += chunk
    out.append(0)
    return bytes(out)


# ---------------------------------------------------------------------------
# Frame differences
# ---------------------------------------------------------------------------

def _first_diff(a, b):
    lo, hi = 0, len(a)
    while lo < hi:
        mid = (lo + hi) // 2
        if a[:mid + 1] == b[:mid + 1]:
            lo = mid + 1
        else:
            hi = mid
    return lo


def _changed_box(prev, cur, w, h):
    rows = [y for y in range(h) if prev[y * w:(y + 1) * w] != cur[y * w:(y + 1) * w]]
    if not rows:
        return None
    x0, x1 = w, -1
    for y in rows:
        a, b = prev[y * w:(y + 1) * w], cur[y * w:(y + 1) * w]
        x0 = min(x0, _first_diff(a, b))
        x1 = max(x1, w - 1 - _first_diff(a[::-1], b[::-1]))
    return x0, rows[0], x1, rows[-1]


# ---------------------------------------------------------------------------
# Writer
# ---------------------------------------------------------------------------

def write_gif(path, frames, total, delay_cs=5, last_delay_cs=300, progress=None):
    """frames: callable returning an iterator of equally sized surfaces
    (called twice: once for the palette, once to encode)."""
    counter = Counter()
    count = 0
    for surf in frames():
        counter.update(_pixels(surf))
        count += 1
        if progress:
            progress(0.3 * count / max(1, total))
    palette, index_of = build_palette(counter)
    mapping = {}
    total = count

    with open(path, "wb") as f:
        prev = None
        w = h = 0
        for n, surf in enumerate(frames()):
            vals = _pixels(surf)
            if prev is None:
                w, h = surf.get_width(), surf.get_height()
                f.write(b"GIF89a" + struct.pack("<HHBBB", w, h, 0xF7, 0, 0))
                pal = palette + [0] * (256 - len(palette))
                f.write(b"".join(struct.pack("BBB", (c >> 16) & 255, (c >> 8) & 255, c & 255)
                                 for c in pal))
                # Loop forever.
                f.write(b"\x21\xFF\x0BNETSCAPE2.0\x03\x01\x00\x00\x00")
            for c in set(vals):
                if c not in mapping:
                    try:
                        mapping[c] = index_of(c)
                    except KeyError:
                        mapping[c] = _nearest(palette, c)
            cur = bytes(map(mapping.__getitem__, vals))
            if prev is None:
                box = (0, 0, w - 1, h - 1)
            else:
                box = _changed_box(prev, cur, w, h) or (0, 0, 0, 0)
            x0, y0, x1, y1 = box
            bw, bh = x1 - x0 + 1, y1 - y0 + 1
            rect = b"".join(cur[y * w + x0:y * w + x1 + 1] for y in range(y0, y1 + 1))
            delay = last_delay_cs if n == total - 1 else delay_cs
            # Graphic control: leave the previous frame in place.
            f.write(b"\x21\xF9\x04" + struct.pack("<BHBB", 1 << 2, delay, 0, 0))
            f.write(b"\x2C" + struct.pack("<HHHHB", x0, y0, bw, bh, 0))
            f.write(b"\x08" + _sub_blocks(lzw_encode(rect)))
            prev = cur
            if progress:
                progress(0.3 + 0.7 * (n + 1) / max(1, total))
        f.write(b"\x3B")
