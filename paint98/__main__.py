import sys

from gi.repository import GLib

# Name the program before GTK starts, so the window class is "paint98"
# rather than "__main__.py" (used by docks to match the launcher).
GLib.set_prgname("paint98")

from .app import main  # noqa: E402

sys.exit(main(sys.argv))
