#!/usr/bin/env python3
"""Run the real window under X11 and capture it (plus an open menu) to PNGs.

usage: GDK_BACKEND=x11 tools/live_shot.py OUTDIR [menu-index]
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import gi  # noqa: E402

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, GLib, Gtk  # noqa: E402

from paint98 import app as appmod  # noqa: E402

out = sys.argv[1]
menu_index = int(sys.argv[2]) if len(sys.argv) > 2 else None


def grab(widget, name):
    gw = widget.get_window()
    pb = Gdk.pixbuf_get_from_window(gw, 0, 0, gw.get_width(), gw.get_height())
    pb.savev(os.path.join(out, name), "png", [], [])


def activate(app):
    win = None

    def open_menu():
        nonlocal win
        win = app.get_windows()[0]
        if menu_index is not None:
            item = win.menubar.get_children()[menu_index]
            win.menubar.select_item(item)
            sub = item.get_submenu()
            sub.popup_at_widget(item, Gdk.Gravity.SOUTH_WEST, Gdk.Gravity.NORTH_WEST, None)
            GLib.timeout_add(500, capture, sub)
        else:
            GLib.timeout_add(100, capture, None)
        return False

    def capture(sub):
        grab(win, "live-window.png")
        if sub is not None:
            grab(sub.get_toplevel(), "live-menu.png")
        app.quit()
        return False

    GLib.timeout_add(800, open_menu)


application = appmod.PaintApp()
application.connect("activate", activate)
application.run([])
