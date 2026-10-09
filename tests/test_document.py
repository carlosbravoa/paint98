"""Document: undo/redo history, resizing and loading/saving files."""

import os
import tempfile
import unittest

from . import helpers  # noqa: F401  (isolated home)
from .helpers import BLUE, RED, WHITE, count_color, paint_rect, pixel, surface_bytes

from gi.repository import GLib  # noqa: E402

from paint98 import document, imageops  # noqa: E402
from paint98.document import Document  # noqa: E402


class SignalLog:
    def __init__(self, doc):
        self.events = []
        for name in ("changed", "size-changed", "state-changed", "reset"):
            doc.connect(name, lambda d, n=name: self.events.append(n))

    def count(self, name):
        return self.events.count(name)


def scribble(doc, rgb, label=None):
    """One undoable step: paint a pixel row in a colour."""
    doc.push_undo(label)
    paint_rect(doc.surface, 0, 0, doc.width, 1, rgb)
    doc.changed()


class HistoryTests(unittest.TestCase):
    def setUp(self):
        self.doc = Document(8, 4)

    def test_new_document(self):
        d = self.doc
        self.assertEqual((d.width, d.height), (8, 4))
        self.assertEqual(count_color(d.surface, WHITE), 32)
        self.assertFalse(d.modified)
        self.assertFalse(d.can_undo() or d.can_redo())
        self.assertEqual(d.display_name, "untitled")

    def test_undo_redo_round_trip(self):
        d = self.doc
        blank = surface_bytes(d.surface)
        scribble(d, RED, "Pencil")
        red = surface_bytes(d.surface)
        scribble(d, BLUE, "Brush")
        self.assertTrue(d.modified)
        self.assertTrue(d.undo())
        self.assertEqual(surface_bytes(d.surface), red)
        self.assertTrue(d.undo())
        self.assertEqual(surface_bytes(d.surface), blank)
        self.assertFalse(d.undo())
        self.assertTrue(d.redo())
        self.assertTrue(d.redo())
        self.assertEqual(pixel(d.surface, 0, 0), BLUE)
        self.assertFalse(d.redo())

    def test_new_step_clears_redo(self):
        d = self.doc
        scribble(d, RED)
        d.undo()
        self.assertTrue(d.can_redo())
        scribble(d, BLUE)
        self.assertFalse(d.can_redo())

    def test_history_names(self):
        d = self.doc
        scribble(d, RED, "Pencil")
        scribble(d, BLUE, "Fill With Color")
        d.undo()
        names, current = d.history()
        self.assertEqual(names, ["New Picture", "Pencil", "Fill With Color"])
        self.assertEqual(current, 1)

    def test_default_label(self):
        scribble(self.doc, RED)
        self.assertEqual(self.doc.history()[0][-1], "Change")

    def test_undo_levels_are_capped(self):
        d = self.doc
        for i in range(document.UNDO_LEVELS + 5):
            scribble(d, (i, 0, 0))
        self.assertEqual(len(d.undo_stack), document.UNDO_LEVELS)
        self.assertEqual(d.history()[0][0], "Earlier steps")
        while d.undo():
            pass
        # The oldest snapshot kept is the picture before step 5 (painted by step 4).
        self.assertEqual(pixel(d.surface, 0, 0), (4, 0, 0))

    def test_discard_last_change_is_not_redoable(self):
        d = self.doc
        blank = surface_bytes(d.surface)
        scribble(d, RED)
        d.discard_last_change()
        self.assertEqual(surface_bytes(d.surface), blank)
        self.assertFalse(d.can_redo())
        d.discard_last_change()  # nothing left: no error

    def test_undo_restores_size(self):
        d = self.doc
        log = SignalLog(d)
        d.resize(20, 10, RED)
        self.assertEqual((d.width, d.height), (20, 10))
        self.assertEqual(pixel(d.surface, 0, 0), WHITE)  # old picture kept
        self.assertEqual(pixel(d.surface, 19, 9), RED)   # new area in bg colour
        d.undo()
        self.assertEqual((d.width, d.height), (8, 4))
        self.assertEqual(log.count("size-changed"), 2)
        self.assertEqual(d.history()[0][-1], "Resize Picture")

    def test_resize_to_same_size_is_no_step(self):
        self.doc.resize(8, 4, RED)
        self.assertFalse(self.doc.can_undo())
        self.doc.resize(0, -3, RED)  # clamps to 1 x 1
        self.assertEqual((self.doc.width, self.doc.height), (1, 1))

    def test_new_resets_everything(self):
        d = self.doc
        scribble(d, RED)
        log = SignalLog(d)
        d.new(30, 20)
        self.assertEqual((d.width, d.height), (30, 20))
        self.assertFalse(d.modified or d.can_undo())
        self.assertIsNone(d.filename)
        self.assertEqual(log.count("reset"), 1)

    def test_state_changed_on_modified(self):
        log = SignalLog(self.doc)
        self.doc.set_modified(True)
        self.doc.set_modified(True)
        self.assertEqual(log.count("state-changed"), 1)


class FileTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.doc = Document(16, 8)
        paint_rect(self.doc.surface, 0, 0, 8, 8, RED)
        paint_rect(self.doc.surface, 8, 0, 8, 8, BLUE)

    def tearDown(self):
        self.dir.cleanup()

    def path(self, name):
        return os.path.join(self.dir.name, name)

    def test_format_for(self):
        self.assertEqual(Document.format_for("a.PNG"), "png")
        self.assertEqual(Document.format_for("a.jpeg"), "jpeg")
        self.assertEqual(Document.format_for("a.tif"), "tiff")
        self.assertIsNone(Document.format_for("a.xyz"))
        self.assertIsNone(Document.format_for("noext"))

    def test_lossless_round_trips(self):
        for name in ("a.png", "a.bmp", "a.tiff", "a.ico"):
            with self.subTest(name):
                p = self.path(name)
                self.doc.save(p)
                self.assertEqual(self.doc.filename, p)
                self.assertFalse(self.doc.modified)
                other = Document()
                other.load(p)
                self.assertEqual((other.width, other.height), (16, 8))
                self.assertEqual(pixel(other.surface, 0, 0), RED)
                self.assertEqual(pixel(other.surface, 15, 7), BLUE)
                self.assertEqual(other.display_name, name)
                self.assertFalse(other.can_undo())

    def test_jpeg_is_close(self):
        p = self.path("a.jpg")
        self.doc.save(p)
        other = Document()
        other.load(p)
        r, g, b = pixel(other.surface, 2, 2)
        self.assertGreater(r, 200)
        self.assertLess(max(g, b), 60)

    def test_unknown_extension_saves_png(self):
        p = self.path("picture.xyz")
        self.doc.save(p)
        with open(p, "rb") as f:
            self.assertEqual(f.read(8), b"\x89PNG\r\n\x1a\n")

    def test_saving_a_copy_keeps_the_filename(self):
        self.doc.set_modified(True)
        self.doc.save(self.path("copy.png"), surface=imageops.copy_surface(self.doc.surface))
        self.assertIsNone(self.doc.filename)
        self.assertTrue(self.doc.modified)

    def test_transparency_flattened_for_bmp_and_jpeg(self):
        clear = imageops.new_surface(4, 4)  # fully transparent
        for name in ("t.bmp", "t.jpg"):
            p = self.path(name)
            self.doc.save(p, surface=clear)
            other = Document()
            other.load(p)
            self.assertGreater(min(pixel(other.surface, 1, 1)), 240, name)

    def test_loading_a_bad_file_keeps_the_picture(self):
        p = self.path("broken.png")
        with open(p, "wb") as f:
            f.write(b"not a picture")
        before = surface_bytes(self.doc.surface)
        with self.assertRaises(GLib.Error):
            self.doc.load(p)
        self.assertEqual(surface_bytes(self.doc.surface), before)
        with self.assertRaises(GLib.Error):
            self.doc.load(self.path("missing.png"))

    def test_recover_marks_unsaved(self):
        p = self.path("rec.png")
        self.doc.surface.write_to_png(p)
        other = Document()
        other.recover(p, "/somewhere/pic.png")
        self.assertTrue(other.modified)
        self.assertEqual(other.display_name, "pic.png")
        self.assertEqual(pixel(other.surface, 15, 0), BLUE)
        self.assertEqual(other.history()[0], ["Recovered"])

    def test_pixbuf_round_trip(self):
        pb = document.surface_to_pixbuf(self.doc.surface)
        back = document.pixbuf_to_surface(pb)
        self.assertEqual(pixel(back, 0, 0), RED)
        self.assertEqual(pixel(back, 15, 7), BLUE)


if __name__ == "__main__":
    unittest.main()
