#!/usr/bin/env python3
"""Generate the small PNG assets referenced by paint98/data/win98.css.

Run from the repository root:  python3 tools/gen_assets.py
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from paint98.pixmaps import make_surface  # noqa: E402

OUT = os.path.join(os.path.dirname(__file__), "..", "paint98", "data")

CHECK = [
    "......k",
    ".....kk",
    "k...kkk",
    "kk.kkk.",
    "kkkkk..",
    ".kkk...",
    "..k....",
]
BULLET = [
    ".kkkk.",
    "kkkkkk",
    "kkkkkk",
    "kkkkkk",
    "kkkkkk",
    ".kkkk.",
]
ARROW_RIGHT = [
    "k...",
    "kk..",
    "kkk.",
    "kkkk",
    "kkk.",
    "kk..",
    "k...",
]
ARROW_UP = [
    "...k...",
    "..kkk..",
    ".kkkkk.",
    "kkkkkkk",
]

CIRCLE = [
    "....XXXX....",
    "..XXXXXXXX..",
    ".XXXXXXXXXX.",
    ".XXXXXXXXXX.",
    "XXXXXXXXXXXX",
    "XXXXXXXXXXXX",
    "XXXXXXXXXXXX",
    "XXXXXXXXXXXX",
    ".XXXXXXXXXX.",
    ".XXXXXXXXXX.",
    "..XXXXXXXX..",
    "....XXXX....",
]
DOT = [".kk.", "kkkk", "kkkk", ".kk."]


def recolor(rows, ch):
    return ["".join(ch if c != "." else "." for c in r) for r in rows]


def rotate_cw(rows):
    h, w = len(rows), len(rows[0])
    return ["".join(rows[h - 1 - y][x] for y in range(h)) for x in range(w)]


def flip_v(rows):
    return list(reversed(rows))


def flip_h(rows):
    return [r[::-1] for r in rows]


def embossed(rows):
    """Disabled look: gray glyph over a white copy shifted by one pixel."""
    h, w = len(rows), len(rows[0])
    out = [["."] * (w + 1) for _ in range(h + 1)]
    for y, r in enumerate(rows):
        for x, c in enumerate(r):
            if c != ".":
                out[y + 1][x + 1] = "w"
    for y, r in enumerate(rows):
        for x, c in enumerate(r):
            if c != ".":
                out[y][x] = "g"
    return ["".join(r) for r in out]


def radio(checked, disabled):
    inside = lambda x, y: 0 <= y < 12 and 0 <= x < 12 and CIRCLE[y][x] == "X"  # noqa: E731
    grid = [["."] * 12 for _ in range(12)]
    ring1 = set()
    for y in range(12):
        for x in range(12):
            if inside(x, y) and any(not inside(x + dx, y + dy) for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))):
                ring1.add((x, y))
    ring2 = set()
    for y in range(12):
        for x in range(12):
            if inside(x, y) and (x, y) not in ring1 and any(
                    (x + dx, y + dy) in ring1 for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))):
                ring2.add((x, y))
    for y in range(12):
        for x in range(12):
            if not inside(x, y):
                continue
            tl = x + y < 11
            if (x, y) in ring1:
                grid[y][x] = "g" if tl else "w"
            elif (x, y) in ring2:
                grid[y][x] = "k" if tl else "d"
            else:
                grid[y][x] = "s" if disabled else "w"
    if checked:
        for y, r in enumerate(DOT):
            for x, c in enumerate(r):
                if c != ".":
                    grid[4 + y][4 + x] = "g" if disabled else "k"
    return ["".join(r) for r in grid]


def checkbox(checked, disabled):
    n = 13
    grid = [["s" if disabled else "w"] * n for _ in range(n)]
    for i in range(n):
        grid[0][i] = "g"
        grid[i][0] = "g"
        grid[n - 1][i] = "w"
        grid[i][n - 1] = "w"
    for i in range(1, n - 1):
        grid[1][i] = "k"
        grid[i][1] = "k"
        grid[n - 2][i] = "d"
        grid[i][n - 2] = "d"
    grid[1][n - 2] = "d"
    grid[n - 2][1] = "d"
    if checked:
        for y, r in enumerate(CHECK):
            for x, c in enumerate(r):
                if c != ".":
                    grid[3 + y][3 + x] = "g" if disabled else "k"
    return ["".join(r) for r in grid]


def save(name, rows):
    make_surface(rows).write_to_png(os.path.join(OUT, name))


def main():
    os.makedirs(OUT, exist_ok=True)
    save("dither.png", ["ws", "sw"])
    save("menu-check.png", CHECK)
    save("menu-check-white.png", recolor(CHECK, "w"))
    save("menu-bullet.png", BULLET)
    save("menu-bullet-white.png", recolor(BULLET, "w"))
    save("menu-arrow.png", ARROW_RIGHT)
    save("menu-arrow-white.png", recolor(ARROW_RIGHT, "w"))
    arrows = {
        "up": ARROW_UP,
        "down": flip_v(ARROW_UP),
        "left": flip_h(ARROW_RIGHT),
        "right": ARROW_RIGHT,
    }
    for name, rows in arrows.items():
        save("arrow-%s.png" % name, rows)
        save("arrow-%s-disabled.png" % name, embossed(rows))
    for checked in (False, True):
        for disabled in (False, True):
            suffix = ("-checked" if checked else "") + ("-disabled" if disabled else "")
            save("radio%s.png" % suffix, radio(checked, disabled))
            save("check%s.png" % suffix, checkbox(checked, disabled))
    # Application icon: the 16x16 pixel art blown up without smoothing.
    from paint98.pixmaps import APP_ICON
    root = os.path.join(os.path.dirname(__file__), "..")
    icon = make_surface(APP_ICON, scale=16)
    icon.write_to_png(os.path.join(root, "snap", "gui", "paint98.png"))
    os.makedirs(os.path.join(root, "data", "icons"), exist_ok=True)
    icon.write_to_png(os.path.join(root, "data", "icons", "com.cbravo.paint98.png"))


if __name__ == "__main__":
    main()
