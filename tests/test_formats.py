"""File formats and persistence: palettes, GIF replays, settings files and
crash-recovery copies."""

import json
import os
import random
import struct
import tempfile
import unittest

from . import helpers  # noqa: F401  (isolated home)
from .helpers import BLUE, GREEN, RED, WHITE, filled, paint_rect, pixel

from gi.repository import GdkPixbuf  # noqa: E402

from paint98 import autosave, gif, replay, symmetry  # noqa: E402
from paint98.window import clean_settings, read_pal, write_pal  # noqa: E402


def lzw_decode(data, min_size=8):
    """Independent GIF LZW decoder used to check the encoder."""
    clear, end = 1 << min_size, (1 << min_size) + 1
    size = min_size + 1
    table = [bytes([i]) for i in range(clear)] + [b"", b""]
    out, prev = bytearray(), None
    bitpos, nbits = 0, len(data) * 8
    while bitpos + size <= nbits:
        code = int.from_bytes(data[bitpos // 8:bitpos // 8 + 3].ljust(3, b"\0"), "little") >> (bitpos % 8)
        code &= (1 << size) - 1
        bitpos += size
        if code == clear:
            table = table[:end + 1]
            size, prev = min_size + 1, None
            continue
        if code == end:
            break
        if code < len(table):
            entry = table[code]
            if prev is not None:
                table.append(prev + entry[:1])
        else:  # the KwKwK case
            entry = prev + prev[:1]
            table.append(entry)
        out += entry
        prev = entry
        if len(table) == (1 << size) and size < 12:
            size += 1
    return bytes(out)


def gif_frames(path):
    """Parse a GIF into (screen size, [(x, y, w, h, delay, lzw bytes)])."""
    with open(path, "rb") as f:
        data = f.read()
    assert data[:6] == b"GIF89a", data[:6]
    w, h, flags = struct.unpack_from("<HHB", data, 6)
    i = 13 + (3 * (2 << (flags & 7)) if flags & 0x80 else 0)
    frames, delay = [], None
    while data[i] != 0x3B:
        if data[i] == 0x21:  # extension
            label = data[i + 1]
            i += 2
            if label == 0xF9:
                delay = struct.unpack_from("<H", data, i + 2)[0]
            while data[i]:
                i += data[i] + 1
            i += 1
        elif data[i] == 0x2C:  # image
            x, y, fw, fh, fl = struct.unpack_from("<HHHHB", data, i + 1)
            i += 10
            min_size = data[i]
            i += 1
            lzw = bytearray()
            while data[i]:
                lzw += data[i + 1:i + 1 + data[i]]
                i += data[i] + 1
            i += 1
            frames.append((x, y, fw, fh, delay, lzw_decode(bytes(lzw), min_size)))
        else:
            raise AssertionError("bad block %#x at %d" % (data[i], i))
    return (w, h), frames


class PaletteFileTests(unittest.TestCase):
    def test_round_trip(self):
        colors = [(i, 255 - i, (i * 7) % 256) for i in range(28)]
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "colors.pal")
            write_pal(p, colors)
            self.assertEqual(read_pal(p), colors)

    def test_rejects_other_files(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "bad.pal")
            with open(p, "wb") as f:
                f.write(b"RIFF\0\0\0\0WAVEdata")
            with self.assertRaises(ValueError):
                read_pal(p)
            with open(p, "wb") as f:
                f.write(b"RIFF\0\0\0\0PAL nothing")
            with self.assertRaises(ValueError):
                read_pal(p)
            # Truncated: Get Colors catches struct.error alongside ValueError.
            with open(p, "wb") as f:
                f.write(b"RIFF\0\0\0\0PAL data\0\0")
            with self.assertRaises((ValueError, struct.error)):
                read_pal(p)


class GifTests(unittest.TestCase):
    def test_lzw_round_trip(self):
        rnd = random.Random(1)
        for data in (b"\0", bytes(5000), bytes(range(256)) * 20,
                     bytes(rnd.randrange(4) for _ in range(20000)),
                     bytes(rnd.randrange(256) for _ in range(20000))):
            self.assertEqual(lzw_decode(gif.lzw_encode(data)), data)

    def test_write_gif_frames(self):
        a = filled(12, 8, WHITE)
        b = filled(12, 8, WHITE)
        paint_rect(b, 3, 2, 2, 2, RED)
        c = filled(12, 8, WHITE)
        paint_rect(c, 3, 2, 2, 2, RED)
        paint_rect(c, 10, 6, 1, 1, BLUE)
        steps = []
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "replay.gif")
            gif.write_gif(p, lambda: iter([a, b, c]), 3, delay_cs=5, last_delay_cs=300,
                          progress=steps.append)
            size, frames = gif_frames(p)
            first = GdkPixbuf.Pixbuf.new_from_file(p)
        self.assertEqual(size, (12, 8))
        self.assertEqual(len(frames), 3)
        # Later frames only carry the area that changed.
        self.assertEqual(frames[0][:4], (0, 0, 12, 8))
        self.assertEqual(frames[1][:4], (3, 2, 2, 2))
        self.assertEqual(frames[2][:4], (10, 6, 1, 1))
        self.assertEqual([f[4] for f in frames], [5, 5, 300])
        for x, y, w, h, _, pixels in frames:
            self.assertEqual(len(pixels), w * h)
        self.assertEqual((first.get_width(), first.get_height()), (12, 8))
        self.assertAlmostEqual(steps[-1], 1.0)
        self.assertEqual(steps, sorted(steps))

    def test_palette_reduces_many_colours(self):
        s = filled(64, 64)
        for i in range(64):
            paint_rect(s, i, 0, 1, 64, (i * 4, 255 - i * 4, (i * 37) % 256))
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "many.gif")
            gif.write_gif(p, lambda: iter([s]), 1)
            pb = GdkPixbuf.Pixbuf.new_from_file(p)
        self.assertEqual(pb.get_width(), 64)


class ReplayTests(unittest.TestCase):
    def test_thin_keeps_first_and_last(self):
        frames = list(range(1000))
        out = replay.thin(frames, 300)
        self.assertEqual(len(out), 300)
        self.assertEqual((out[0], out[-1]), (0, 999))
        self.assertEqual(out, sorted(out))
        self.assertEqual(replay.thin([1, 2], 300), [1, 2])

    def test_frame_round_trip(self):
        s = filled(5, 3, GREEN)
        paint_rect(s, 4, 2, 1, 1, RED)
        back = replay.Frame(s).surface()
        self.assertEqual(pixel(back, 0, 0), GREEN)
        self.assertEqual(pixel(back, 4, 2), RED)


class SettingsTests(unittest.TestCase):
    def test_garbage_is_dropped(self):
        for junk in (None, [], "x", 3):
            self.assertEqual(clean_settings(junk), {})
        cfg = clean_settings({
            "toolbox": "yes", "colorbox": False, "window_size": [50, 99999],
            "recent": ["/a.png", 5, None], "custom_palette": ["zzzzzz"] * 28,
            "opacity": {"pencil": 50, "brush": "x", "fill": True}, "fill_tolerance": 7,
            "fill_mode": 1.5, "symmetry": "quad", "sizes": [], "unknown": 1,
        })
        self.assertEqual(cfg, {"colorbox": False, "recent": ["/a.png"], "opacity": {"pencil": 50},
                               "fill_tolerance": 7, "symmetry": "quad"})

    def test_good_settings_survive(self):
        good = {"toolbox": True, "window_size": [800, 600], "custom_palette": ["ff0000"] * 28,
                "sticker": {"current": "px:Star"}, "sizes": {"pencil": 2}, "palette_mode": "fun"}
        self.assertEqual(clean_settings(json.loads(json.dumps(good))), good)

    def test_old_tolerance_key_is_ignored(self):
        self.assertNotIn("tolerance", clean_settings({"tolerance": 0}))


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        for sid, _, _ in autosave.find_orphans():
            autosave.discard(sid)

    def write_copy(self, sid, info):
        png, meta, lock = autosave._paths(sid)
        filled(4, 4, RED).write_to_png(png)
        with open(meta, "w") as f:
            json.dump(info, f)
        return png, meta, lock

    def test_orphans_found_newest_first(self):
        self.write_copy("session-old", {"time": 1, "filename": None})
        self.write_copy("session-new", {"time": 2, "filename": "/x.png"})
        found = autosave.find_orphans()
        self.assertEqual([sid for sid, _, _ in found], ["session-new", "session-old"])
        autosave.discard("session-new")
        autosave.discard("session-old")
        self.assertEqual(autosave.find_orphans(), [])

    def test_running_session_is_not_an_orphan(self):
        import fcntl
        _, _, lock = self.write_copy("session-live", {"time": 1})
        with open(lock, "w") as f:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.assertEqual(autosave.find_orphans(), [])
        self.assertEqual(len(autosave.find_orphans()), 1)
        autosave.discard("session-live")

    def test_damaged_copies_are_discarded(self):
        png, meta, _ = self.write_copy("session-bad", {"time": 1})
        with open(meta, "w") as f:
            f.write("{not json")
        self.assertEqual(autosave.find_orphans(), [])
        self.assertFalse(os.path.exists(png))
        _, meta, _ = self.write_copy("session-nopng", {"time": 1})
        os.remove(autosave._paths("session-nopng")[0])
        self.assertEqual(autosave.find_orphans(), [])
        self.assertFalse(os.path.exists(meta))

    def test_recovery_dir_is_isolated(self):
        self.assertTrue(autosave.recovery_dir().startswith(helpers.TEST_HOME))


class SymmetryTests(unittest.TestCase):
    def apply(self, m, x, y):
        return tuple(round(v, 6) for v in m.transform_point(x, y))

    def test_copies_per_mode(self):
        counts = {mode: len(symmetry.transforms(mode, 100, 80)) for mode, _, _ in symmetry.MODES}
        self.assertEqual(counts, {"off": 1, "mirror": 2, "quad": 4, "radial6": 6, "kaleido8": 8})

    def test_first_copy_is_identity_and_all_stay_on_picture(self):
        for mode, _, _ in symmetry.MODES:
            ms = symmetry.transforms(mode, 100, 100)
            self.assertEqual(self.apply(ms[0], 10, 20), (10, 20))
            for m in ms:
                x, y = self.apply(m, 50, 50)  # the centre never moves
                self.assertEqual((x, y), (50, 50), mode)

    def test_mirror_and_quad(self):
        mirror = symmetry.transforms("mirror", 100, 80)
        self.assertEqual(self.apply(mirror[1], 10, 20), (90, 20))
        quad = symmetry.transforms("quad", 100, 80)
        self.assertEqual({self.apply(m, 10, 20) for m in quad}, {(10, 20), (90, 20), (10, 60), (90, 60)})

    def test_kaleidoscope_copies_are_distinct(self):
        ms = symmetry.transforms("kaleido8", 100, 100)
        self.assertEqual(len({self.apply(m, 30, 10) for m in ms}), 8)

    def test_every_mode_has_a_hint(self):
        self.assertEqual(set(symmetry.HINTS), {mode for mode, _, _ in symmetry.MODES})


if __name__ == "__main__":
    unittest.main()
