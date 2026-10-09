"""The main window: menus, tool box, colour box, dialogs, files and settings.

Modal dialogs are replaced with stand-ins that answer straight away, so the
real menu handlers run end to end."""

import json
import os
import tempfile
import types
import unittest
from unittest import mock

from .helpers import (BLACK, BLUE, GREEN, RED, WHITE, WindowTestCase, application, count_color,
                      flush_events, paint_rect)

from gi.repository import Gdk  # noqa: E402

from paint98 import dialogs, imageops, toolbox, window  # noqa: E402
from paint98.colorbox import ColorBox  # noqa: E402
from paint98.state import TOOLS  # noqa: E402


def answer(cls, result=None, ok=True, **attrs):
    """Patch a dialog class so run() returns at once (OK by default) and
    result() returns the given value."""
    def run(self):
        for k, v in attrs.items():
            setattr(self, k, v)
        return dialogs.OK if ok else dialogs.CANCEL
    patches = [mock.patch.object(cls, "run", run)]
    if result is not None:
        patches.append(mock.patch.object(cls, "result", lambda self: result))
    return patches


class Patched:
    def __init__(self, patches):
        self.patches = patches

    def __enter__(self):
        for p in self.patches:
            p.start()

    def __exit__(self, *exc):
        for p in self.patches:
            p.stop()


def widget_event(x, y, button=1, kind=Gdk.EventType.BUTTON_PRESS):
    return types.SimpleNamespace(x=x, y=y, button=button, type=kind, state=0)


class MenuTests(WindowTestCase):
    def test_window_renders(self):
        surf = self.render()
        self.assertGreater(surf.get_width(), 400)
        for widget in (self.win.toolbox, self.win.colorbox, self.canvas):
            self.render(widget)

    def test_menu_items_and_accelerators(self):
        items = self.win.items
        for name in ("new", "open", "save", "save_as", "undo", "redo", "cut", "copy", "paste",
                     "select_all", "flip", "stretch", "invert", "attributes", "clear_image",
                     "edit_colors", "get_colors", "save_colors", "zoom_normal", "zoom_large"):
            self.assertIn(name, items)

    def test_sensitivity_follows_the_selection(self):
        self.win.refresh_sensitivity()
        self.assertFalse(self.win.items["copy"].get_sensitive())
        self.win.items["select_all"].activate()
        self.win.refresh_sensitivity()
        self.assertTrue(self.win.items["copy"].get_sensitive())
        self.assertTrue(self.win.items["cut"].get_sensitive())

    def test_select_all_and_clear_selection(self):
        paint_rect(self.doc.surface, 0, 0, self.W, self.H, RED)
        self.state.set_bg(GREEN)
        self.win.items["select_all"].activate()
        sel = self.canvas.selection
        self.assertEqual((sel.x, sel.y, sel.w, sel.h), (0, 0, self.W, self.H))
        self.win.items["clear_sel"].activate()
        self.assertIsNone(self.canvas.selection)
        self.assertEqual(count_color(self.doc.surface, GREEN), self.W * self.H)
        self.win.canvas_undo()
        self.assertEqual(count_color(self.doc.surface, RED), self.W * self.H)

    def test_invert(self):
        paint_rect(self.doc.surface, 0, 0, 10, 10, RED)
        before = self.snapshot()
        self.win.items["invert"].activate()
        self.assertEqual(self.px(0, 0), (0, 255, 255))
        self.assertEqual(self.px(50, 50), BLACK)
        self.assertEqual(self.doc.history()[0][-1], "Invert Colors")
        self.assertUndoRestores(before)

    def test_invert_selection_only(self):
        self.use("rect_select")
        self.drag([(0, 0), (9, 9)])
        self.win.items["invert"].activate()
        self.canvas.commit_selection()
        self.assertEqual(count_color(self.doc.surface, BLACK), 100)

    def test_clear_image(self):
        paint_rect(self.doc.surface, 0, 0, 10, 10, RED)
        self.state.set_bg(BLUE)
        self.win.items["clear_image"].activate()
        self.assertEqual(count_color(self.doc.surface, BLUE), self.W * self.H)

    def test_flip_and_rotate(self):
        paint_rect(self.doc.surface, 0, 0, 1, 1, RED)
        with Patched(answer(dialogs.FlipRotateDialog, ("flip", True))):
            self.win.items["flip"].activate()
        self.assertEqual(self.px(self.W - 1, 0), RED)
        with Patched(answer(dialogs.FlipRotateDialog, ("rotate", 90))):
            self.win.items["flip"].activate()
        self.assertEqual((self.doc.width, self.doc.height), (self.H, self.W))
        self.assertEqual(self.px(self.H - 1, self.W - 1), RED)
        self.win.canvas_undo()
        self.assertEqual((self.doc.width, self.doc.height), (self.W, self.H))

    def test_cancelled_dialog_changes_nothing(self):
        with Patched(answer(dialogs.FlipRotateDialog, ("flip", True), ok=False)):
            self.win.items["flip"].activate()
        self.assertFalse(self.doc.can_undo())

    def test_stretch_and_skew(self):
        with Patched(answer(dialogs.StretchSkewDialog, (200, 50, 0, 0))):
            self.win.items["stretch"].activate()
        self.assertEqual((self.doc.width, self.doc.height), (self.W * 2, self.H // 2))
        with Patched(answer(dialogs.StretchSkewDialog, (100, 100, 45, 0))):
            self.win.items["stretch"].activate()
        self.assertEqual(self.doc.width, self.W * 2 + self.H // 2 - 1)
        self.assertEqual(count_color(self.doc.surface, WHITE), self.doc.width * self.doc.height)

    def test_too_big_is_reported_not_raised(self):
        errors = []
        with Patched(answer(dialogs.StretchSkewDialog, (500, 500, 89, 0))), \
                mock.patch.object(self.win, "error", errors.append):
            self.win.items["stretch"].activate()
        self.assertEqual(len(errors), 1)
        self.assertIn("too big", errors[0])
        self.assertEqual((self.doc.width, self.doc.height), (self.W, self.H))

    def test_attributes_resize_and_black_and_white(self):
        paint_rect(self.doc.surface, 0, 0, 10, 10, (200, 30, 30))
        with Patched(answer(dialogs.AttributesDialog, (50, 40, False))), \
                mock.patch.object(window, "message_box", lambda *a, **k: 0):
            self.win.items["attributes"].activate()
        self.assertEqual((self.doc.width, self.doc.height), (50, 40))
        self.assertTrue(self.doc.monochrome)
        self.assertEqual(count_color(self.doc.surface, BLACK) + count_color(self.doc.surface, WHITE), 2000)

    def test_edit_colors_sets_foreground_and_palette(self):
        with Patched(answer(dialogs.EditColorsDialog, color=(10, 20, 30))):
            self.win.on_edit_colors(3)
        self.assertEqual(self.state.fg, (10, 20, 30))
        self.assertEqual(self.state.palette[3], (10, 20, 30))

    def test_zoom_items(self):
        self.win.items["zoom_large"].activate()
        self.assertEqual(self.canvas.zoom, 4)
        self.win.refresh_sensitivity()
        self.assertTrue(self.win.items["grid"].get_sensitive())
        self.render()
        self.win.items["zoom_normal"].activate()
        self.assertEqual(self.canvas.zoom, 1)

    def test_palette_modes(self):
        for name, mode in (("pal_fun", "fun"), ("pal_custom", "custom"), ("pal_original", "original")):
            self.win.items[name].set_active(True)
            self.assertEqual(self.state.palette_mode, mode)
            self.render(self.win.colorbox)

    def test_symmetry_items(self):
        self.win.items["sym_quad"].set_active(True)
        self.assertEqual(self.state.symmetry, "quad")
        self.render(self.canvas)
        self.win.items["sym_off"].set_active(True)
        self.assertEqual(self.state.symmetry, "off")

    def test_view_toggles(self):
        self.win.items["v_toolbox"].set_active(False)
        self.assertFalse(self.win.toolbox.get_visible())
        self.win.items["v_toolbox"].set_active(True)
        self.assertTrue(self.win.toolbox.get_visible())

    def test_side_windows_open(self):
        self.use("pencil")
        self.drag([(10, 10), (50, 50)])
        self.win.items["v_history"].set_active(True)
        flush_events()
        self.win.items["v_history"].set_active(False)
        self.win.show_sticker_book()
        flush_events()
        self.win.sticker_book.destroy()
        self.win.on_replay()
        flush_events()

    def test_text_tool_shows_the_text_toolbar(self):
        self.use("text")
        self.drag([(10, 10), (100, 60)])
        flush_events()
        self.assertTrue(self.win.textbar.get_visible())
        self.render()
        self.canvas.commit_all()
        flush_events()
        self.assertFalse(self.win.textbar.get_visible())


class PasteTests(WindowTestCase):
    def test_pasted_picture_floats(self):
        surf = imageops.new_surface(10, 10, RED)
        pb = window.surface_to_pixbuf(surf)
        self.win.float_pixbuf(pb)
        sel = self.canvas.selection
        self.assertTrue(sel.floating)
        self.assertEqual(self.state.tool, "rect_select")
        self.canvas.commit_selection()
        self.assertEqual(count_color(self.doc.surface, RED), 100)
        self.win.canvas_undo()
        self.assertEqual(count_color(self.doc.surface, RED), 0)

    def test_bigger_paste_can_enlarge_the_picture(self):
        pb = window.surface_to_pixbuf(imageops.new_surface(200, 30, RED))
        with mock.patch.object(window, "message_box", lambda *a, **k: 0):
            self.win.float_pixbuf(pb)
        self.assertEqual((self.doc.width, self.doc.height), (200, self.H))


class FileTests(WindowTestCase):
    def setUp(self):
        super().setUp()
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)

    def path(self, name):
        return os.path.join(self.dir.name, name)

    def test_save_as_then_save(self):
        paint_rect(self.doc.surface, 0, 0, 10, 10, RED)
        self.doc.set_modified(True)
        p = self.path("pic.png")
        with mock.patch.object(self.win, "file_dialog", lambda *a, **k: p):
            self.win.items["save_as"].activate()
        self.assertTrue(os.path.exists(p))
        self.assertFalse(self.doc.modified)
        self.assertEqual(self.win.get_title(), "pic.png - Paint98")
        self.assertEqual(self.win.settings["recent"][0], p)
        # Save writes to the same file without asking.
        paint_rect(self.doc.surface, 0, 0, 10, 10, BLUE)
        self.doc.set_modified(True)
        with mock.patch.object(self.win, "file_dialog", side_effect=AssertionError("asked")):
            self.win.items["save"].activate()
        self.assertFalse(self.doc.modified)

    def test_save_commits_text_being_typed(self):
        self.use("text")
        self.drag([(10, 10), (100, 60)])
        self.canvas.on_im_commit(self.canvas.im, "Hi")
        p = self.path("text.png")
        with mock.patch.object(self.win, "file_dialog", lambda *a, **k: p):
            self.win.items["save"].activate()
        self.assertGreater(count_color(self.doc.surface, BLACK), 5)

    def test_refuses_unwritable_formats(self):
        errors = []
        with mock.patch.object(self.win, "file_dialog", lambda *a, **k: self.path("x.gif")), \
                mock.patch.object(self.win, "error", errors.append):
            self.win.items["save_as"].activate()
        self.assertEqual(len(errors), 1)
        self.assertFalse(os.path.exists(self.path("x.gif")))

    def test_open(self):
        p = self.path("in.bmp")
        other = window.Document(30, 20)
        paint_rect(other.surface, 0, 0, 30, 20, GREEN)
        other.save(p)
        with mock.patch.object(self.win, "file_dialog", lambda *a, **k: p):
            self.win.items["open"].activate()
        self.assertEqual((self.doc.width, self.doc.height), (30, 20))
        self.assertEqual(self.px(5, 5), GREEN)
        self.assertEqual(self.win.get_title(), "in.bmp - Paint98")

    def test_open_bad_file_reports_and_keeps_picture(self):
        p = self.path("bad.png")
        with open(p, "w") as f:
            f.write("nope")
        errors = []
        with mock.patch.object(self.win, "file_dialog", lambda *a, **k: p), \
                mock.patch.object(self.win, "error", errors.append):
            self.win.items["open"].activate()
        self.assertEqual(len(errors), 1)
        self.assertEqual((self.doc.width, self.doc.height), (self.W, self.H))

    def test_unsaved_changes_are_asked_about(self):
        self.use("pencil")
        self.click(5, 5)
        answers = []

        def box(*a, **k):
            answers.append(a[2])
            return 2  # Cancel
        with mock.patch.object(window, "message_box", box):
            self.win.items["new"].activate()
        self.assertEqual(len(answers), 1)
        self.assertEqual(self.px(5, 5), BLACK)  # Cancel keeps the picture
        with mock.patch.object(window, "message_box", lambda *a, **k: 1):  # No: discard
            self.win.items["new"].activate()
        self.assertEqual(self.px(5, 5), WHITE)
        self.assertFalse(self.doc.can_undo())

    def test_palette_files(self):
        p = self.path("colors.pal")
        self.state.set_palette([RED] * 28)
        with mock.patch.object(self.win, "file_dialog", lambda *a, **k: p):
            self.win.items["save_colors"].activate()
        self.state.set_palette([WHITE] * 28)
        with mock.patch.object(self.win, "file_dialog", lambda *a, **k: p):
            self.win.items["get_colors"].activate()
        self.assertEqual(self.state.custom_palette, [RED] * 28)
        self.assertEqual(self.state.palette_mode, "custom")


class SettingsTests(WindowTestCase):
    def test_settings_survive_a_restart(self):
        self.state.set_opacity("brush", 40)
        self.state.tolerance = 12
        self.state.fill_mode = 2
        self.state.set_palette([BLUE] * 28)
        self.win.items["sym_mirror"].set_active(True)
        self.win.items["v_statusbar"].set_active(False)
        self.win.save_settings()
        with open(window.config_path()) as f:
            saved = json.load(f)
        self.assertEqual(saved["fill_tolerance"], 12)
        again = window.MainWindow(application())
        try:
            st = again.state
            self.assertEqual(st.opacity["brush"], 40)
            self.assertEqual(st.tolerance, 12)
            self.assertEqual(st.fill_mode, 2)
            self.assertEqual(st.custom_palette, [BLUE] * 28)
            self.assertEqual(st.symmetry, "mirror")
            self.assertFalse(again.settings["statusbar"])
        finally:
            again.destroy()
            os.remove(window.config_path())

    def test_damaged_settings_file_is_ignored(self):
        os.makedirs(os.path.dirname(window.config_path()), exist_ok=True)
        with open(window.config_path(), "w") as f:
            f.write("{broken")
        again = window.MainWindow(application())
        try:
            self.assertEqual(again.state.tolerance, 2)
        finally:
            again.destroy()
            os.remove(window.config_path())


class ToolBoxTests(WindowTestCase):
    def button_centre(self, item):
        i = toolbox.ITEMS.index(item)
        return (toolbox.X0 + (i % 2) * toolbox.BTN + toolbox.BTN // 2,
                toolbox.Y0 + (i // 2) * toolbox.BTN + toolbox.BTN // 2)

    def click_box(self, item):
        tb = self.win.toolbox
        x, y = self.button_centre(item)
        tb.on_press(tb, widget_event(x, y))
        tb.on_release(tb, widget_event(x, y, kind=Gdk.EventType.BUTTON_RELEASE))

    def test_every_tool_button(self):
        for tool in TOOLS:
            self.assertEqual(self.win.toolbox.tool_at(*self.button_centre(tool)), tool)
            self.click_box(tool)
            self.assertEqual(self.state.tool, tool)
            self.render(self.win.toolbox)

    def test_undo_redo_buttons(self):
        self.use("pencil")
        self.click(5, 5)
        self.click_box("undo")
        self.assertEqual(self.px(5, 5), WHITE)
        self.click_box("redo")
        self.assertEqual(self.px(5, 5), BLACK)

    def test_disabled_buttons_do_nothing(self):
        self.assertFalse(self.win.toolbox.action_enabled("undo"))
        self.click_box("undo")
        self.click_box("redo")
        self.assertFalse(self.doc.can_undo() or self.doc.can_redo())

    def test_release_elsewhere_cancels_the_button(self):
        self.use("pencil")
        self.click(5, 5)
        tb = self.win.toolbox
        x, y = self.button_centre("undo")
        tb.on_press(tb, widget_event(x, y))
        tb.on_release(tb, widget_event(x, y + 200, kind=Gdk.EventType.BUTTON_RELEASE))
        self.assertEqual(self.px(5, 5), BLACK)

    def test_buttons_follow_undo_state(self):
        tb = self.win.toolbox
        self.assertEqual(tb.shown_enabled, (False, False))
        self.use("pencil")
        self.click(5, 5)
        self.assertEqual(tb.shown_enabled, (True, False))
        self.win.canvas_undo()
        self.assertEqual(tb.shown_enabled, (False, True))

    def test_every_tool_option_box(self):
        tb = self.win.toolbox
        for tool in TOOLS:
            self.use(tool)
            for (x, y, w, h), name, value in tb.option_items():
                if name == "sticker_book":
                    continue
                with self.subTest(tool=tool, option=name, value=value):
                    tb.on_press(tb, widget_event(x + w // 2, y + h // 2))
                    if name == ("eraser_shape", "eraser_size"):
                        self.assertEqual((self.state.eraser_shape, self.state.eraser_size), value)
                    else:
                        self.assertEqual(getattr(self.state, name), value)
            self.render(tb)

    def test_sticker_book_button(self):
        opened = []
        self.win.toolbox.connect("open-sticker-book", lambda *a: opened.append(True))
        self.use("sticker")
        tb = self.win.toolbox
        (x, y, w, h), _, _ = [i for i in tb.option_items() if i[1] == "sticker_book"][0]
        tb.on_press(tb, widget_event(x + w // 2, y + h // 2))
        flush_events()
        self.assertEqual(opened, [True])
        self.assertIsNotNone(self.win.sticker_book)
        self.win.sticker_book.destroy()


class ColorBoxTests(WindowTestCase):
    def find(self, box, test):
        for y in range(0, 60):
            for x in range(0, 300):
                if test(x, y):
                    return x, y
        self.fail("spot not found")

    def test_palette_clicks_set_colours(self):
        box = self.win.colorbox
        x, y = self.find(box, lambda x, y: box.index_at(x, y) == 2)
        box.on_press(box, widget_event(x, y))
        self.assertEqual(self.state.fg, self.state.palette[2])
        box.on_press(box, widget_event(x, y, button=3))
        self.assertEqual(self.state.bg, self.state.palette[2])

    def test_single_click_on_a_swatch_asks_to_edit(self):
        box = ColorBox(self.state)
        asked = []
        box.connect("edit-indicator", lambda b, which: asked.append(which))
        fx, fy = self.find(box, lambda x, y: box.indicator_at(x, y) == "fg")
        box.on_press(box, widget_event(fx, fy))
        bx, by = self.find(box, lambda x, y: box.indicator_at(x, y) == "bg")
        box.on_press(box, widget_event(bx, by))
        box.on_press(box, widget_event(bx, by, button=3))
        self.assertEqual(asked, ["fg", "bg"])
        box.destroy()


class DialogTests(WindowTestCase):
    """Every dialog builds, draws and reports a result."""

    def show(self, dlg):
        dlg.show_all()
        flush_events()
        self.render(dlg.frame)

    def test_dialogs_build(self):
        cases = [
            (dialogs.AttributesDialog(self.win, 640, 480, ("01/01/2026 10:00", "1,234 bytes")), (640, 480, True)),
            (dialogs.FlipRotateDialog(self.win), ("flip", True)),
            (dialogs.StretchSkewDialog(self.win), (100, 100, 0, 0)),
        ]
        for dlg, default in cases:
            with self.subTest(type(dlg).__name__):
                self.show(dlg)
                self.assertEqual(dlg.result(), default)
                dlg.destroy()
        zoom = dialogs.CustomZoomDialog(self.win, 1)
        self.show(zoom)
        self.assertIn(zoom.result(), dialogs.CustomZoomDialog.LEVELS)
        zoom.destroy()

    def test_edit_colors_dialog(self):
        dlg = dialogs.EditColorsDialog(self.win, (255, 128, 64), custom=[WHITE] * 16)
        self.show(dlg)
        self.assertTrue(dlg.right.get_visible())  # spectrum always shown
        self.assertEqual(dlg.color, (255, 128, 64))
        dlg.hex_entry.set_text("#00ff00")
        dlg.hex_entry.activate()
        flush_events()
        self.assertEqual(dlg.color, GREEN)
        dlg.on_add()
        self.assertEqual(dlg.custom[0], GREEN)
        self.assertTrue(dlg.custom_changed)
        dlg.destroy()

    def test_hex_and_hsl_helpers(self):
        self.assertEqual(dialogs.parse_hex("#FF8000"), (255, 128, 0))
        self.assertEqual(dialogs.parse_hex("f80"), (255, 136, 0))
        self.assertIsNone(dialogs.parse_hex("zzz"))
        for rgb in (RED, GREEN, BLUE, WHITE, BLACK, (128, 64, 32)):
            back = dialogs.hsl240_to_rgb(*dialogs.rgb_to_hsl240(rgb))
            self.assertTrue(all(abs(a - b) <= 3 for a, b in zip(back, rgb)), (rgb, back))

    def test_help_topics(self):
        from gi.repository import Gtk
        before = set(Gtk.Window.list_toplevels())
        dialogs.help_topics(self.win)
        flush_events()
        opened = [w for w in Gtk.Window.list_toplevels() if w not in before and w.get_visible()]
        self.assertEqual(len(opened), 1)
        self.render(opened[0].frame)
        opened[0].destroy()


if __name__ == "__main__":
    unittest.main()
