"""Shared test helpers: a headless main window, simulated mouse input and
pixel checks."""

import sys
import traceback
import types
import unittest
import warnings

from . import TEST_HOME  # noqa: F401  (sets up the isolated home first)

import cairo  # noqa: E402
import gi  # noqa: E402

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, Gtk  # noqa: E402

from paint98 import imageops  # noqa: E402

HAVE_DISPLAY = Gtk.init_check(sys.argv[:1])[0]
needs_display = unittest.skipUnless(HAVE_DISPLAY, "needs a display (try xvfb-run)")

WHITE, BLACK = (255, 255, 255), (0, 0, 0)
RED, GREEN, BLUE = (255, 0, 0), (0, 255, 0), (0, 0, 255)
SHIFT = int(Gdk.ModifierType.SHIFT_MASK)
CTRL = int(Gdk.ModifierType.CONTROL_MASK)

# PyGObject prints exceptions raised in signal handlers and draw callbacks
# instead of propagating them; record them so tests can fail on them.
callback_errors = []
_default_hook = sys.excepthook


def _record(etype, value, tb):
    callback_errors.append("".join(traceback.format_exception(etype, value, tb)))
    _default_hook(etype, value, tb)


sys.excepthook = _record


def pixel(surf, x, y):
    return imageops.get_pixel(surf, x, y)


def surface_bytes(surf):
    surf.flush()
    return bytes(surf.get_data())


def count_color(surf, rgb, box=None):
    """How many pixels in box (x0, y0, x1, y1 exclusive) are exactly rgb."""
    w, h = surf.get_width(), surf.get_height()
    x0, y0, x1, y1 = box or (0, 0, w, h)
    target = imageops.rgb_to_pixel(rgb)
    px, stride = imageops._pixels(surf)
    return sum(1 for y in range(y0, y1) for x in range(x0, x1) if px[y * stride + x] == target)


def filled(w, h, rgb=WHITE):
    return imageops.new_surface(w, h, rgb)


def paint_rect(surf, x, y, w, h, rgb):
    cr = cairo.Context(surf)
    cr.set_source_rgb(*(c / 255 for c in rgb))
    cr.rectangle(x, y, w, h)
    cr.fill()
    surf.flush()


def flush_events():
    with warnings.catch_warnings():
        # gi's main loop hook trips over an asyncio deprecation on Python 3.14.
        warnings.simplefilter("ignore", DeprecationWarning)
        while Gtk.events_pending():
            Gtk.main_iteration_do(False)


_app = None


def application():
    global _app
    if _app is None:
        from paint98 import app as appmod
        appmod.load_css()
        _app = appmod.PaintApp()
        _app.register(None)
    return _app


class WindowTestCase(unittest.TestCase):
    """A fresh main window per test, kept off-screen, with helpers that send
    mouse events through the canvas's real event handlers."""

    W, H = 120, 90

    def setUp(self):
        if not HAVE_DISPLAY:
            self.skipTest("needs a display (try xvfb-run)")
        from paint98.window import MainWindow
        del callback_errors[:]
        self.win = MainWindow(application())
        self.offscreen = Gtk.OffscreenWindow()
        self.offscreen.get_style_context().add_class("paint98")
        frame = self.win.frame
        self.win.remove(frame)
        self.offscreen.add(frame)
        self.offscreen.set_size_request(700, 560)
        self.offscreen.show_all()
        self.canvas, self.state, self.doc = self.win.canvas, self.win.state, self.win.doc
        self.doc.new(self.W, self.H)
        flush_events()

    def tearDown(self):
        win = getattr(self, "win", None)
        if win is None:
            return
        self.canvas.discard_pending()
        self.doc.modified = False
        self.offscreen.destroy()
        win.destroy()
        flush_events()
        errors, callback_errors[:] = list(callback_errors), []
        if errors:
            self.fail("exceptions in GTK callbacks:\n" + "\n".join(errors))

    # -- input --------------------------------------------------------------
    def _event(self, x, y, button=1, mods=0, kind=Gdk.EventType.BUTTON_PRESS):
        z = self.canvas.zoom
        wx, wy = self.canvas.to_widget(x, y)
        return types.SimpleNamespace(x=wx + z / 2, y=wy + z / 2, button=button, state=mods, type=kind)

    def press(self, x, y, button=1, mods=0):
        self.canvas.on_press(self.canvas, self._event(x, y, button, mods))

    def double_click(self, x, y, button=1):
        self.canvas.on_press(self.canvas, self._event(x, y, button, 0, Gdk.EventType._2BUTTON_PRESS))

    def move(self, x, y, mods=0):
        self.canvas.on_motion(self.canvas, self._event(x, y, 0, mods, Gdk.EventType.MOTION_NOTIFY))

    def release(self, x, y, button=1, mods=0):
        self.canvas.on_release(self.canvas, self._event(x, y, button, mods, Gdk.EventType.BUTTON_RELEASE))

    def drag(self, points, button=1, mods=0):
        """Press at the first point, move through the rest, release at the last."""
        self.press(*points[0], button=button, mods=mods)
        for p in points[1:]:
            self.move(*p, mods=mods)
        self.release(*points[-1], button=button, mods=mods)

    def click(self, x, y, button=1, mods=0):
        self.drag([(x, y)], button, mods)

    def use(self, tool, **options):
        self.state.set_tool(tool)
        for name, value in options.items():
            setattr(self.state, name, value)
        return self.canvas.tool

    # -- output -------------------------------------------------------------
    def px(self, x, y):
        return pixel(self.doc.surface, x, y)

    def snapshot(self):
        return surface_bytes(self.doc.surface)

    def render(self, widget=None):
        """Draw a widget (default: the whole window) into an image surface,
        running every draw handler."""
        widget = widget or self.win.frame
        flush_events()
        self.offscreen.check_resize()  # lay out after zoom or size changes
        a = widget.get_allocation()
        surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, max(1, a.width), max(1, a.height))
        widget.draw(cairo.Context(surf))
        return surf

    def assertUndoRestores(self, before):
        """Undo puts the picture back exactly; redo brings the change back."""
        after = self.snapshot()
        self.assertNotEqual(before, after, "the action changed nothing")
        self.win.canvas_undo()
        self.assertEqual(before, self.snapshot(), "undo did not restore the picture")
        self.win.canvas_redo()
        self.assertEqual(after, self.snapshot(), "redo did not bring the change back")
