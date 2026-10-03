#!/usr/bin/env python3
"""Render the main window off-screen to a PNG (development aid).

usage: tools/shot.py OUT.png [script.py]

The optional script is exec()'d with `win`, `canvas`, `state`, `doc` in scope
before the snapshot is taken, so it can drive tools programmatically.
"""

import os
os.environ.setdefault("XDG_CONFIG_HOME", os.path.join(os.environ.get("TMPDIR", "/tmp"), "paint98-shot-config"))
os.environ.setdefault("XDG_DATA_HOME", os.path.join(os.environ.get("TMPDIR", "/tmp"), "paint98-shot-data"))
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import gi  # noqa: E402

gi.require_version("Gtk", "3.0")
from gi.repository import GLib, Gtk  # noqa: E402

import cairo  # noqa: E402

from paint98 import app as appmod  # noqa: E402


def main():
    out = sys.argv[1]
    script = sys.argv[2] if len(sys.argv) > 2 else None
    w, h = int(os.environ.get("SHOT_W", 520)), int(os.environ.get("SHOT_H", 500))
    Gtk.init([])
    appmod.load_css()
    application = appmod.PaintApp()
    application.register(None)
    from paint98.window import MainWindow
    win = MainWindow(application)
    off = Gtk.OffscreenWindow()
    off.get_style_context().add_class("paint98")
    frame = win.frame
    win.remove(frame)
    off.add(frame)
    off.set_size_request(w, h)
    off.show_all()
    win.textbar.hide()

    target = {"frame": frame}

    def snap():
        if script:
            ns = dict(win=win, canvas=win.canvas, state=win.state, doc=win.doc, Gtk=Gtk)
            try:
                exec(open(script).read(), ns)
            except Exception:
                import traceback
                traceback.print_exc()
            dlg = ns.get("dialog")
            if dlg is not None:
                # Render a dialog instead of the main window.
                f = dlg.frame
                dlg.remove(f)
                off2 = Gtk.OffscreenWindow()
                off2.get_style_context().add_class("paint98")
                off2.add(f)
                off2.show_all()
                target["frame"] = f
        GLib.timeout_add(300, save)
        return False

    def save():
        frame = target["frame"]
        a = frame.get_allocation()
        surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, a.width, a.height)
        cr = cairo.Context(surf)
        frame.draw(cr)
        surf.write_to_png(out)
        Gtk.main_quit()
        return False

    GLib.timeout_add(500, snap)
    Gtk.main()


main()
