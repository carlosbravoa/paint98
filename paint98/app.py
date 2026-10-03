"""Gtk.Application entry point."""

import os
import sys

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, Gio, GLib, Gtk  # noqa: E402

from . import APP_ID  # noqa: E402

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")


def load_css():
    screen = Gdk.Screen.get_default()
    provider = Gtk.CssProvider()
    provider.load_from_path(os.path.join(DATA_DIR, "win98.css"))
    Gtk.StyleContext.add_provider_for_screen(screen, provider, Gtk.STYLE_PROVIDER_PRIORITY_USER + 1)
    settings = Gtk.Settings.get_default()
    # Classic behaviour: no animations, mnemonics always underlined,
    # clicking the trough pages instead of jumping.
    for prop, value in (("gtk-enable-animations", False),
                        ("gtk-auto-mnemonics", False),
                        ("gtk-primary-button-warps-slider", False),
                        ("gtk-menu-bar-popup-delay", 0)):
        try:
            settings.set_property(prop, value)
        except TypeError:
            pass


class PaintApp(Gtk.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID,
                         flags=Gio.ApplicationFlags.HANDLES_OPEN | Gio.ApplicationFlags.NON_UNIQUE)
        GLib.set_application_name("Paint")

    def do_startup(self):
        Gtk.Application.do_startup(self)
        load_css()

    def new_window(self, path=None):
        from .window import MainWindow
        win = MainWindow(self, path)
        win.show_all()
        win.present()
        return win

    def do_activate(self):
        self.new_window()

    def do_open(self, files, n_files, hint):
        for f in files:
            self.new_window(f.get_path())


def main(argv=None):
    app = PaintApp()
    return app.run(argv if argv is not None else sys.argv)
