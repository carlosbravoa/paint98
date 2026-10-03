"""Sticker library: classic pixel art, emoji and the user's own stickers.

A sticker is identified by a string id:
  "px:<name>"    built-in pixel art (stickerart.CLASSIC)
  "emoji:<chr>"  a colour emoji from the emoji font
  "user:<file>"  a PNG in the user's sticker folder
"""

import os
import time

import cairo
import gi

gi.require_version("Pango", "1.0")
gi.require_version("PangoCairo", "1.0")
from gi.repository import GLib, Pango, PangoCairo  # noqa: E402

from . import imageops, pixmaps  # noqa: E402
from .stickerart import CLASSIC, EXTRA  # noqa: E402

EMOJI_FONT = "Noto Color Emoji"
DEFAULT = "px:Star"

EMOJI = [
    ("Faces", "😀 😃 😄 😁 😆 😂 🤣 😊 😇 🙂 😉 😍 🥰 😘 😋 😛 😜 🤪 😎 🤩 🥳 😏 😮 😲 "
              "😴 🤔 🤗 🤭 😢 😭 😡 🤯 😱 🥶 🤠 🤡 👻 💀 👽 🤖 🎃 😺 😸 😻 🙈 🙉 🙊"),
    ("Animals", "🐶 🐱 🐭 🐹 🐰 🦊 🐻 🐼 🐨 🐯 🦁 🐮 🐷 🐸 🐵 🐔 🐧 🐦 🐤 🦆 🦉 🦄 🐝 🐛 "
                "🦋 🐌 🐞 🐢 🐍 🦖 🦕 🐙 🦑 🦀 🐠 🐟 🐬 🐳 🦈 🐊 🐘 🦒 🦓 🐪 🐎 🐑 🐿 🦔"),
    ("Food", "🍎 🍐 🍊 🍋 🍌 🍉 🍇 🍓 🍒 🍑 🍍 🥝 🥥 🥑 🥕 🌽 🥦 🍄 🥨 🧀 🍞 🥞 🍳 🍔 "
             "🍟 🍕 🌭 🌮 🍿 🍩 🍪 🎂 🍰 🧁 🍫 🍬 🍭 🍦 🍨 🥛 🧃"),
    ("Nature", "🌞 🌝 🌛 ⭐ 🌟 ✨ ⚡ 🔥 🌈 ☁ ⛅ 🌧 ❄ ☃ ⛄ 💧 🌊 🌸 🌺 🌻 🌹 🌷 🌼 🌱 "
               "🌲 🌳 🌴 🌵 🍀 🍁 🍂 🌍 🪐 🌙"),
    ("Things", "🎈 🎉 🎁 🎀 🧸 🪁 ⚽ 🏀 🏈 ⚾ 🎾 🏐 🎱 🛹 🎨 🖍 ✏ 📚 🎸 🎹 🥁 🎺 🎻 🎤 "
               "🎧 🎮 🧩 🎲 🪀 👑 💎 🔮 🪄 🧲 🔔 💡 📷 ⏰ ☂ 🎩 👓 🧦 👟"),
    ("Travel", "🚗 🚕 🚙 🚌 🚓 🚑 🚒 🚜 🏎 🚲 🛴 🚂 🚀 🛸 ✈ 🚁 ⛵ 🚤 🛳 🚢 🏠 🏡 🏰 🏯 "
               "🎡 🎢 🎠 ⛺ 🗽 🌋 🏝 🗺"),
    ("Symbols", "❤ 🧡 💛 💚 💙 💜 🖤 🤍 💖 💗 💕 💯 ✅ ❌ ❓ ❗ ➕ ➖ ⭕ 🔴 🟠 🟡 🟢 🔵 "
                "🟣 ⬛ ⬜ 🔶 🔷 ♻ ☮ ☯ ♈ 🎵 🎶 💤 💬 💭 🆒 🆗"),
]

_PALETTE = dict(pixmaps.PALETTE)
_PALETTE.update(EXTRA)
_CLASSIC = dict(CLASSIC)
_cache = {}


def user_dir():
    base = os.environ.get("SNAP_USER_COMMON") or os.path.join(GLib.get_user_data_dir(), "paint98")
    path = os.path.join(base, "stickers")
    os.makedirs(path, exist_ok=True)
    return path


def categories():
    """[(title, [ids])] in Sticker Book order."""
    cats = [("Classic", ["px:" + name for name, _ in CLASSIC])]
    if emoji_available():
        for title, chars in EMOJI:
            cats.append((title, ["emoji:" + c for c in chars.split()]))
    cats.append(("My Stickers", user_stickers()))
    return cats


def user_stickers():
    try:
        files = sorted(f for f in os.listdir(user_dir()) if f.lower().endswith(".png"))
    except OSError:
        files = []
    return ["user:" + f for f in files]


_emoji_ok = None


def emoji_available():
    global _emoji_ok
    if _emoji_ok is None:
        fm = PangoCairo.FontMap.get_default()
        _emoji_ok = any(f.get_name() == EMOJI_FONT for f in fm.list_families())
    return _emoji_ok


def exists(sid):
    kind, _, key = sid.partition(":")
    if kind == "px":
        return key in _CLASSIC
    if kind == "emoji":
        return emoji_available()
    if kind == "user":
        return os.path.exists(os.path.join(user_dir(), key))
    return False


def name(sid):
    kind, _, key = sid.partition(":")
    if kind == "user":
        return "My sticker"
    return key


def _render_emoji(ch, size):
    surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, size, size)
    cr = cairo.Context(surf)
    layout = PangoCairo.create_layout(cr)
    fd = Pango.FontDescription(EMOJI_FONT)
    fd.set_absolute_size(size * 0.8 * Pango.SCALE)
    layout.set_font_description(fd)
    layout.set_text(ch, -1)
    ink, _ = layout.get_pixel_extents()
    if ink.width <= 0 or ink.height <= 0:
        return surf
    scale = min(size / ink.width, size / ink.height)
    cr.translate(size / 2, size / 2)
    cr.scale(scale, scale)
    cr.translate(-(ink.x + ink.width / 2), -(ink.y + ink.height / 2))
    PangoCairo.show_layout(cr, layout)
    return surf


def _fit(src, size, nearest):
    """Scale a surface into a size x size square, keeping its proportions."""
    w, h = src.get_width(), src.get_height()
    scale = size / max(w, h)
    out = cairo.ImageSurface(cairo.FORMAT_ARGB32, size, size)
    cr = cairo.Context(out)
    cr.translate((size - w * scale) / 2, (size - h * scale) / 2)
    cr.scale(scale, scale)
    cr.set_source_surface(src, 0, 0)
    cr.get_source().set_filter(cairo.FILTER_NEAREST if nearest else cairo.FILTER_GOOD)
    cr.paint()
    return out


def render(sid, size):
    """The sticker as a size x size ARGB surface (cached)."""
    size = max(4, int(size))
    key = (sid, size)
    if key in _cache:
        return _cache[key]
    kind, _, k = sid.partition(":")
    if kind == "px" and k in _CLASSIC:
        surf = _fit(pixmaps.make_surface(_CLASSIC[k], _PALETTE), size, nearest=True)
    elif kind == "emoji":
        surf = _render_emoji(k, size)
    elif kind == "user":
        try:
            src = cairo.ImageSurface.create_from_png(os.path.join(user_dir(), k))
            surf = _fit(src, size, nearest=max(src.get_width(), src.get_height()) <= size)
        except (cairo.Error, OSError):
            surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, size, size)
    else:
        surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, size, size)
    if len(_cache) > 400:
        _cache.clear()
    _cache[key] = surf
    return surf


def crop_to_content(surf):
    """Trim fully transparent borders (row scans run on alpha bytes)."""
    w, h = surf.get_width(), surf.get_height()
    alpha = imageops.alpha_mask(surf)
    alpha.flush()
    data, stride = bytes(alpha.get_data()), alpha.get_stride()
    x0, x1, rows = w, -1, []
    for y in range(h):
        row = data[y * stride:y * stride + w]
        core = row.strip(b"\x00")
        if core:
            rows.append(y)
            x0 = min(x0, len(row) - len(row.lstrip(b"\x00")))
            x1 = max(x1, len(row.rstrip(b"\x00")) - 1)
    if not rows:
        return None
    y0, y1 = rows[0], rows[-1]
    out = cairo.ImageSurface(cairo.FORMAT_ARGB32, x1 - x0 + 1, y1 - y0 + 1)
    cr = cairo.Context(out)
    cr.set_source_surface(surf, -x0, -y0)
    cr.paint()
    return out


def save_user_sticker(surf):
    """Store a surface as a new user sticker; returns its id or None."""
    surf = crop_to_content(surf)
    if surf is None:
        return None
    fname = "sticker-%d.png" % int(time.time() * 1000)
    surf.write_to_png(os.path.join(user_dir(), fname))
    return "user:" + fname


def delete_user_sticker(sid):
    kind, _, k = sid.partition(":")
    if kind != "user":
        return
    try:
        os.remove(os.path.join(user_dir(), k))
    except OSError:
        pass
    for key in [key for key in _cache if key[0] == sid]:
        del _cache[key]
