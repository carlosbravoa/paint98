"""The main Paint98 window: menus, tool box, colour box, canvas and status bar."""

import json
import os
import struct
import time

import cairo
import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, GdkPixbuf, Gio, GLib, GObject, Gtk, Pango  # noqa: E402

from . import __version__, dialogs, imageops, pixmaps, win98  # noqa: E402
from .canvas import Canvas  # noqa: E402
from .colorbox import ColorBox  # noqa: E402
from .funpaints import set_paint, solid  # noqa: E402
from .document import Document, pixbuf_to_surface, surface_to_pixbuf  # noqa: E402
from .state import DEFAULT_HELP, DEFAULT_PALETTE, TOOL_NAMES, PaintState  # noqa: E402
from .autosave import AutoSaver  # noqa: E402
from .history import HistoryWindow  # noqa: E402
from .settingsbar import SymmetryBar, ToolSettingsPanel  # noqa: E402
from .replay import Recorder, ReplayWindow, export_gif  # noqa: E402
from .stickerbook import StickerBook  # noqa: E402
from . import stickers  # noqa: E402
from . import symmetry  # noqa: E402
from .textbar import TextToolbar  # noqa: E402
from .toolbox import ToolBox  # noqa: E402
from .win98 import Win98Window, message_box  # noqa: E402

MAX_RECENT = 4

IMAGE_FILTERS = [
    ("PNG (*.png)", ["*.png"], ".png"),
    ("24-bit Bitmap (*.bmp)", ["*.bmp"], ".bmp"),
    ("JPEG (*.jpg;*.jpeg)", ["*.jpg", "*.jpeg"], ".jpg"),
    ("TIFF (*.tif;*.tiff)", ["*.tif", "*.tiff"], ".tif"),
]


def display_path(path):
    """A file name made safe to show (names need not be valid UTF-8)."""
    return os.fsencode(path).decode("utf-8", "replace")


def in_document_portal(path):
    """True for files handed to the (confined) app by the file chooser
    portal: only that exact file may be written."""
    runtime = os.environ.get("XDG_RUNTIME_DIR", "")
    return bool(runtime) and path.startswith(os.path.join(runtime, "doc") + os.sep)


BOOL_KEYS = ("toolbox", "colorbox", "statusbar", "settingsbar", "textbar")
STR_KEYS = ("palette_mode", "last_plain", "symmetry", "eraser_shape")


def clean_settings(cfg):
    """Keep only well-formed settings so a damaged file can't break start-up."""
    if not isinstance(cfg, dict):
        return {}
    out = {}

    def is_int(v):
        return isinstance(v, int) and not isinstance(v, bool)

    for k in BOOL_KEYS:
        if isinstance(cfg.get(k), bool):
            out[k] = cfg[k]
    for k in STR_KEYS:
        if isinstance(cfg.get(k), str):
            out[k] = cfg[k]
    ws = cfg.get("window_size")
    if isinstance(ws, (list, tuple)) and len(ws) == 2 and all(is_int(v) and 100 <= v <= 20000 for v in ws):
        out["window_size"] = list(ws)
    if isinstance(cfg.get("recent"), list):
        out["recent"] = [p for p in cfg["recent"] if isinstance(p, str)][:MAX_RECENT]
    pal = cfg.get("custom_palette")
    if isinstance(pal, list) and len(pal) == 28 and all(isinstance(h, str) and len(h) == 6 for h in pal):
        try:
            [int(h, 16) for h in pal]
            out["custom_palette"] = pal
        except ValueError:
            pass
    if isinstance(cfg.get("opacity"), dict):
        out["opacity"] = {k: v for k, v in cfg["opacity"].items() if isinstance(k, str) and is_int(v)}
    for k in ("tolerance", "fill_mode"):
        if is_int(cfg.get(k)):
            out[k] = cfg[k]
    for k in ("sizes", "sticker"):
        if isinstance(cfg.get(k), dict):
            out[k] = cfg[k]
    return out


def config_path():
    return os.path.join(GLib.get_user_config_dir(), "paint98", "settings.json")


def wallpaper_dir():
    base = os.environ.get("SNAP_USER_COMMON") or os.path.join(GLib.get_user_data_dir(), "paint98")
    path = os.path.join(base, "wallpaper")
    os.makedirs(path, exist_ok=True)
    return path


# ---------------------------------------------------------------------------
# Palette files (RIFF "PAL ")
# ---------------------------------------------------------------------------

def read_pal(path):
    with open(path, "rb") as f:
        data = f.read()
    if data[:4] != b"RIFF" or data[8:12] != b"PAL ":
        raise ValueError("Not a palette file")
    i = data.find(b"data", 12)
    if i < 0:
        raise ValueError("Palette file has no colors")
    count = struct.unpack_from("<H", data, i + 10)[0]
    colors = []
    for n in range(count):
        r, g, b, _ = struct.unpack_from("<BBBB", data, i + 12 + n * 4)
        colors.append((r, g, b))
    return colors


def write_pal(path, colors):
    body = struct.pack("<HH", 0x300, len(colors)) + b"".join(struct.pack("<BBBB", r, g, b, 0) for r, g, b in colors)
    chunk = b"data" + struct.pack("<I", len(body)) + body
    data = b"PAL " + chunk
    with open(path, "wb") as f:
        f.write(b"RIFF" + struct.pack("<I", len(data)) + data)


# ---------------------------------------------------------------------------
# Menu check items
# ---------------------------------------------------------------------------

class CheckItem(Gtk.MenuItem):
    """A menu item with a check mark drawn by the stylesheet.

    Gtk.CheckMenuItem makes GTK reserve indicator space per menu, which
    shifts the text of whole menus; the classic look keeps one fixed gutter.
    """

    __gsignals__ = {
        "toggled": (GObject.SignalFlags.RUN_FIRST, None, ()),
    }

    def __init__(self, label):
        super().__init__(label=label, use_underline=True)
        self.get_style_context().add_class("check-item")
        self._active = False

    def get_active(self):
        return self._active

    def set_active(self, value):
        value = bool(value)
        if value == self._active:
            return
        self._active = value
        ctx = self.get_style_context()
        if value:
            ctx.add_class("checked")
        else:
            ctx.remove_class("checked")
        self.emit("toggled")

    def do_activate(self):
        self.set_active(not self._active)


# ---------------------------------------------------------------------------
# Auxiliary windows
# ---------------------------------------------------------------------------

class ThumbnailWindow(Win98Window):
    def __init__(self, parent, canvas):
        super().__init__("Thumbnail", buttons=("close",), icon=False)
        self.set_transient_for(parent)
        self.set_type_hint(Gdk.WindowTypeHint.UTILITY)
        self.set_default_size(180, 140)
        self.set_skip_taskbar_hint(True)
        self.canvas = canvas
        self.area = Gtk.DrawingArea()
        self.area.connect("draw", self.on_draw)
        self.body.pack_start(self.area, True, True, 0)
        canvas.doc.connect("changed", lambda *a: self.area.queue_draw())
        for adj in (canvas.hadj, canvas.vadj):
            adj.connect("value-changed", lambda *a: self.area.queue_draw())
        self.set_destroy_with_parent(True)
        self.connect("delete-event", lambda *a: self.request_close() or True)

    def request_close(self):
        self.hide()
        self.on_closed()

    def on_closed(self):
        pass

    def on_draw(self, w, cr):
        c = self.canvas
        cr.set_source_rgb(*win98.SHADOW)
        cr.paint()
        x, y = c.visible_origin()
        cr.set_source_surface(c.preview or c.doc.surface, -x, -y)
        cr.get_source().set_filter(cairo.FILTER_NEAREST)
        cr.rectangle(0, 0, c.doc.width - x, c.doc.height - y)
        cr.fill()
        return True


class PrintPreviewWindow(Win98Window):
    """Print Preview drawn by Paint98 itself (the system previewer is not
    available to a confined snap): the page with the picture as it will be
    printed, plus Print and Close buttons."""

    def __init__(self, main):
        super().__init__("%s - Print Preview" % display_path(main.doc.display_name),
                         buttons=("close",), icon=True)
        self.main = main
        self.set_transient_for(main)
        self.set_destroy_with_parent(True)
        self.set_modal(True)
        self.set_default_size(560, 640)
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        row.set_border_width(6)
        row.pack_start(win98.make_button("_Print...", self.on_print, default=True), False, False, 0)
        row.pack_start(win98.make_button("Page Set_up...", self.on_setup), False, False, 0)
        row.pack_end(win98.make_button("_Close", self.close), False, False, 0)
        self.body.pack_start(row, False, False, 0)
        self.area = Gtk.DrawingArea()
        self.area.set_size_request(380, 480)
        self.area.connect("draw", self.on_draw)
        self.body.pack_start(self.area, True, True, 0)

    def on_print(self):
        self.close()
        self.main.on_print()

    def on_setup(self):
        self.main.on_page_setup()
        self.area.queue_draw()

    def on_draw(self, w, cr):
        width, height = w.get_allocated_width(), w.get_allocated_height()
        cr.set_source_rgb(*win98.SHADOW)
        cr.paint()
        setup = self.main.page_setup or Gtk.PageSetup()
        pt = Gtk.Unit.POINTS
        paper_w, paper_h = setup.get_paper_width(pt), setup.get_paper_height(pt)
        left, top = setup.get_left_margin(pt), setup.get_top_margin(pt)
        area_w, area_h = setup.get_page_width(pt), setup.get_page_height(pt)
        scale = min((width - 40) / paper_w, (height - 40) / paper_h)
        ox = (width - paper_w * scale) / 2
        oy = (height - paper_h * scale) / 2
        cr.set_source_rgb(0, 0, 0)
        cr.rectangle(int(ox) + 3, int(oy) + 3, int(paper_w * scale), int(paper_h * scale))
        cr.fill()
        cr.set_source_rgb(1, 1, 1)
        cr.rectangle(int(ox), int(oy), int(paper_w * scale), int(paper_h * scale))
        cr.fill()
        pic = self.main.picture_rect_on_page(area_w, area_h)
        cr.translate(ox + left * scale, oy + top * scale)
        cr.scale(scale * pic, scale * pic)
        cr.set_source_surface(self.main.doc.surface, 0, 0)
        cr.get_source().set_filter(cairo.FILTER_GOOD)
        cr.paint()
        return True


class BitmapViewer(Gtk.Window):
    """View Bitmap: the whole picture on an otherwise empty screen."""

    def __init__(self, parent, surface):
        super().__init__()
        self.surface = surface
        self.set_transient_for(parent)
        self.set_decorated(False)
        self.add_events(Gdk.EventMask.BUTTON_PRESS_MASK | Gdk.EventMask.KEY_PRESS_MASK)
        self.connect("draw", self.on_draw)
        self.connect("button-press-event", lambda *a: self.destroy())
        self.connect("key-press-event", lambda *a: self.destroy())
        self.set_app_paintable(True)
        self.fullscreen()

    def on_draw(self, w, cr):
        a = self.get_allocation()
        cr.set_source_rgb(0, 0x80 / 255, 0x80 / 255)
        cr.paint()
        sw, sh = self.surface.get_width(), self.surface.get_height()
        cr.set_source_surface(self.surface, max(0, (a.width - sw) // 2), max(0, (a.height - sh) // 2))
        cr.paint()
        return True


# ---------------------------------------------------------------------------
# Main window
# ---------------------------------------------------------------------------

class MainWindow(Win98Window):
    def __init__(self, app, path=None):
        super().__init__("untitled - Paint98", application=app)
        self.app = app
        self.state = PaintState()
        self.doc = Document(640, 480)
        self.settings = self.load_settings()
        self.restore_tool_settings()
        self.palette_index = 0
        self.thumbnail = None
        self.sticker_book = None
        self.page_setup = None
        self.print_settings = None
        self.items = {}
        self.set_icon(self.app_icon_pixbuf())

        self.accel = Gtk.AccelGroup()
        self.add_accel_group(self.accel)

        self.menubar = self.build_menubar()
        self.body.pack_start(self.menubar, False, False, 0)
        sep = Gtk.Box()
        sep.get_style_context().add_class("win98-separator")
        self.body.pack_start(sep, False, False, 0)

        self.textbar = TextToolbar(self.state)
        self.textbar.refocus = lambda: self.canvas.grab_focus()
        self.textbar.set_no_show_all(True)
        self.body.pack_start(self.textbar, False, False, 0)

        middle = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        self.toolbox = ToolBox(self.state)
        middle.pack_start(self.toolbox, False, False, 0)

        self.canvas = Canvas(self.state, self.doc)
        self.scroller = Gtk.ScrolledWindow()
        self.scroller.set_overlay_scrolling(False)
        self.scroller.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        self.scroller.get_style_context().add_class("workspace")
        viewport = Gtk.Viewport()
        viewport.add(self.canvas)
        self.scroller.add(viewport)
        self.canvas.hadj = self.scroller.get_hadjustment()
        self.canvas.vadj = self.scroller.get_vadjustment()
        field = Gtk.Box()
        field.get_style_context().add_class("win98-field")
        field.pack_start(self.scroller, True, True, 0)
        middle.pack_start(field, True, True, 0)
        self.body.pack_start(middle, True, True, 0)

        bottom = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        self.colorbox = ColorBox(self.state)
        bottom.pack_start(self.colorbox, False, False, 0)
        self.settingsbar = ToolSettingsPanel(self.state)
        bottom.pack_end(self.settingsbar, False, False, 6)
        self.symmetrybar = SymmetryBar(self.state)
        bottom.pack_end(self.symmetrybar, False, False, 6)
        self.body.pack_start(bottom, False, False, 0)

        self.statusbar = self.build_statusbar()
        self.body.pack_start(self.statusbar, False, False, 0)

        self.recorder = Recorder(self.canvas, self.doc)
        # Name undo steps after the tool that made them (History window).
        self.doc.default_label = lambda: TOOL_NAMES.get(self.state.tool, "Change")
        self.history_window = None
        self.autosaver = AutoSaver(self.canvas, self.doc)
        self.connect("destroy", lambda *a: self.autosaver.close())
        self.connect_signals()
        self.apply_view_settings()
        self.set_default_size(*self.settings.get("window_size", (780, 640)))
        self.update_title()
        if path:
            GLib.idle_add(self.open_path, path)

    @staticmethod
    def app_icon_pixbuf():
        surf = pixmaps.get("APP_ICON", 3)
        return Gdk.pixbuf_get_from_surface(surf, 0, 0, surf.get_width(), surf.get_height())

    # -- settings ---------------------------------------------------------------
    def load_settings(self):
        try:
            with open(config_path()) as f:
                return clean_settings(json.load(f))
        except (OSError, ValueError):
            return {}

    def restore_tool_settings(self):
        st, cfg = self.state, self.settings

        def rgb_list(hexes):
            try:
                return [tuple(int(h[i:i + 2], 16) for i in (0, 2, 4)) for h in hexes][:28]
            except (TypeError, ValueError):
                return None

        pal = rgb_list(cfg.get("custom_palette") or [])
        # Older versions saved an untouched copy of the original colours as
        # the custom palette; treat that as "not customised yet" (blank).
        if pal and len(pal) == 28 and pal != DEFAULT_PALETTE:
            st.custom_palette = pal
        stk = cfg.get("sticker") or {}
        try:
            if isinstance(stk.get("current"), str) and stickers.exists(stk["current"]):
                st.sticker = stk["current"]
            st.sticker_size = max(8, min(256, int(stk.get("size", st.sticker_size))))
            recent = stk.get("recent", [])
            recent = [s for s in recent if isinstance(s, str) and stickers.exists(s)] \
                if isinstance(recent, list) else []
            if recent:
                st.sticker_recent = recent[:6]
        except (TypeError, ValueError, AttributeError):
            pass
        if cfg.get("symmetry") in [m for m, _, _ in symmetry.MODES]:
            st.symmetry = cfg["symmetry"]
        mode = cfg.get("palette_mode") or ("custom" if cfg.get("use_custom") else "original")
        if mode in ("original", "custom", "fun"):
            st.palette_mode = mode
        last = cfg.get("last_plain", "custom" if mode == "custom" else "original")
        st.last_plain = last if last in ("original", "custom") else "original"
        for tool, value in (cfg.get("opacity") or {}).items():
            if tool in st.opacity and isinstance(value, int):
                st.opacity[tool] = max(1, min(100, value))
        st.tolerance = max(0, min(100, int(cfg.get("tolerance", 0))))
        st.fill_mode = int(cfg.get("fill_mode", 0)) % 3
        st.eraser_shape = "circle" if cfg.get("eraser_shape") == "circle" else "square"
        sizes = cfg.get("sizes") or {}
        try:
            st.brush = max(0, min(11, int(sizes.get("brush_preset", st.brush))))
            st.eraser_size = max(0, min(3, int(sizes.get("eraser_preset", st.eraser_size))))
            for tool in ("pencil", "brush", "eraser"):
                if tool in sizes:
                    lo, hi = st.SIZE_LIMITS[tool]
                    setattr(st, st.SIZE_ATTRS[tool], max(lo, min(hi, int(sizes[tool]))))
        except (TypeError, ValueError, AttributeError):
            pass

    def store_tool_settings(self):
        st = self.state
        self.settings["custom_palette"] = ["%02x%02x%02x" % c for c in st.custom_palette]
        self.settings["symmetry"] = st.symmetry
        self.settings["sticker"] = {"current": st.sticker, "size": st.sticker_size,
                                    "recent": st.sticker_recent}
        self.settings["palette_mode"] = st.palette_mode
        self.settings["last_plain"] = st.last_plain
        self.settings.pop("use_custom", None)
        self.settings["opacity"] = dict(st.opacity)
        self.settings["tolerance"] = st.tolerance
        self.settings["fill_mode"] = st.fill_mode
        self.settings["eraser_shape"] = st.eraser_shape
        self.settings["sizes"] = {"pencil": st.pencil_size, "brush": st.brush_size,
                                  "brush_preset": st.brush, "eraser": st.eraser_px,
                                  "eraser_preset": st.eraser_size}

    def sync_symmetry_checks(self):
        for mode, _, _ in symmetry.MODES:
            self.set_check("sym_" + mode, self.state.symmetry == mode)

    def on_symmetry_item(self, name, active):
        self.state.set_option("symmetry", name[4:])
        self.sync_symmetry_checks()

    def sync_palette_checks(self):
        for mode in ("original", "custom", "fun"):
            self.set_check("pal_" + mode, self.state.palette_mode == mode)

    def on_palette_changed(self, state):
        self.sync_palette_checks()
        self.save_settings()

    def on_palette_item(self, name, active):
        # The three items behave like radio items.
        self.state.set_palette_mode(name[4:])
        self.sync_palette_checks()

    def save_settings(self):
        self.store_tool_settings()
        self.settings["window_size"] = list(self.get_size())
        try:
            os.makedirs(os.path.dirname(config_path()), exist_ok=True)
            with open(config_path(), "w") as f:
                json.dump(self.settings, f, indent=1)
        except OSError:
            pass

    # -- menus ------------------------------------------------------------------
    def build_menubar(self):
        mb = Gtk.MenuBar()
        self.recent_items = []
        self.file_menu = self.add_menu(mb, "_File", [
            ("new", "_New", self.on_new, "<Control>n", "Creates a new document."),
            ("open", "_Open...", self.on_open, "<Control>o", "Opens an existing document."),
            ("save", "_Save", self.on_save, "<Control>s", "Saves the active document."),
            ("save_as", "Save _As...", self.on_save_as, None, "Saves the active document with a new name."),
            None,
            ("print_preview", "Print Pre_view", self.on_print_preview, None, "Displays full pages."),
            ("page_setup", "Page Se_tup...", self.on_page_setup, None, "Changes the page layout."),
            ("print", "_Print...", self.on_print, "<Control>p",
             "Prints the active document and sets printing options."),
            None,
            ("send", "S_end...", None, None, "Sends a picture by using electronic mail."),
            None,
            ("save_replay", "Save Rep_lay As...", self.on_save_replay, None,
             "Saves an animated GIF that shows how the picture was drawn."),
            None,
            ("wall_tiled", "Set As _Wallpaper (Tiled)", lambda: self.on_wallpaper("wallpaper"), None,
             "Tiles this bitmap as the desktop wallpaper."),
            ("wall_center", "Set As Wa_llpaper (Centered)", lambda: self.on_wallpaper("centered"), None,
             "Centers this bitmap as the desktop wallpaper."),
            ("recent_sep", None),
            ("exit", "E_xit", self.close, "<Alt>F4", "Quits Paint98."),
        ])
        self.add_menu(mb, "_Edit", [
            ("undo", "_Undo", self.canvas_undo, "<Control>z", "Undoes the last action."),
            ("redo", "_Repeat", self.canvas_redo, "F4", "Redoes the previously undone action."),
            None,
            ("cut", "Cu_t", self.on_cut, "<Control>x", "Cuts the selection and puts it on the Clipboard."),
            ("copy", "_Copy", self.on_copy, "<Control>c", "Copies the selection and puts it on the Clipboard."),
            ("paste", "_Paste", self.on_paste, "<Control>v", "Inserts the contents of the Clipboard."),
            ("clear_sel", "C_lear Selection", self.on_clear_selection, "Delete", "Deletes the selection."),
            ("select_all", "Select _All", self.on_select_all, "<Control>l", "Selects everything."),
            None,
            ("copy_to", "C_opy To...", self.on_copy_to, None, "Copies the selection to a file."),
            ("paste_from", "Paste _From...", self.on_paste_from, None, "Pastes a file into the selection."),
            ("save_sticker", "Save Selection as _Sticker", self.on_save_sticker, None,
             "Adds the selection to My Stickers in the Sticker Book."),
        ])
        self.add_menu(mb, "_View", [
            ("v_toolbox", "_Tool Box", self.on_toggle_view, "<Control>t", "Shows or hides the tool box.", "check"),
            ("v_colorbox", "_Color Box", self.on_toggle_view, "<Control>a", "Shows or hides the color box.",
             "check"),
            ("v_statusbar", "_Status Bar", self.on_toggle_view, None, "Shows or hides the status bar.", "check"),
            ("v_textbar", "T_ext Toolbar", self.on_toggle_view, None, "Shows or hides the text toolbar.",
             "check"),
            ("v_settingsbar", "Tool Setti_ngs", self.on_toggle_view, None,
             "Shows or hides the tool settings (opacity, size and tolerance).", "check"),
            None,
            ("zoom", "_Zoom", [
                ("zoom_normal", "_Normal Size", lambda: self.canvas.set_zoom(1), "<Control>Page_Up",
                 "Zooms the picture to 100%."),
                ("zoom_large", "_Large Size", lambda: self.canvas.set_zoom(4), "<Control>Page_Down",
                 "Zooms the picture to 400%."),
                ("zoom_custom", "C_ustom...", self.on_custom_zoom, None, "Zooms the picture."),
                None,
                ("grid", "Show _Grid", self.on_toggle_grid, "<Control>g", "Shows or hides the grid.", "check"),
                ("thumb", "Show T_humbnail", self.on_toggle_thumbnail, None,
                 "Shows or hides the thumbnail view of the picture.", "check"),
            ], None, "Zooms the picture."),
            ("view_bitmap", "_View Bitmap", self.on_view_bitmap, "<Control>f", "Displays the entire picture."),
            ("replay", "_Replay...", self.on_replay, "<Control><Shift>r",
             "Plays back how the picture was drawn."),
            ("v_history", "_History", self.on_toggle_view, "<Control>h",
             "Shows every step of the picture; click one to go back to it.", "check"),
            ("sticker_book", "Stic_ker Book...", self.show_sticker_book, "<Control>b",
             "Opens the Sticker Book to pick a sticker."),
        ])
        self.add_menu(mb, "_Image", [
            ("flip", "_Flip/Rotate...", self.on_flip_rotate, "<Control>r",
             "Flips or rotates the picture or a selection."),
            ("stretch", "_Stretch/Skew...", self.on_stretch_skew, "<Control>w",
             "Stretches or skews the picture or a selection."),
            ("recolor", "_Recolor Selection", self.on_recolor_selection, "<Control><Shift>f",
             "Paints the selection with the foreground color (Fun Colors too)."),
            ("invert", "_Invert Colors", self.on_invert, "<Control>i",
             "Inverts the colors of the picture or a selection."),
            ("attributes", "_Attributes...", self.on_attributes, "<Control>e",
             "Changes the attributes of the picture."),
            ("clear_image", "_Clear Image", self.on_clear_image, "<Control><Shift>n",
             "Clears the picture or selection."),
            ("opaque", "_Draw Opaque", self.on_toggle_opaque, None,
             "Makes the current selection either opaque or transparent.", "check"),
        ])
        self.add_menu(mb, "_Options", [
            ("edit_colors", "_Edit Colors...", self.on_edit_colors, None, "Creates a new color."),
            ("get_colors", "_Get Colors...", self.on_get_colors, None,
             "Uses a previously saved palette of colors."),
            ("save_colors", "_Save Colors...", self.on_save_colors, None,
             "Saves the current palette of colors to a file."),
            None,
            ("symmetry", "S_ymmetry", [
                ("sym_" + mode, label, self.on_symmetry_item, None, symmetry.HINTS[mode], "check")
                for mode, label, _ in symmetry.MODES
            ], None, "Repeats what you draw around the centre of the picture."),
            None,
            ("pal_original", "O_riginal Colors", self.on_palette_item, None,
             "Shows the original 28 colors.", "check"),
            ("pal_custom", "C_ustom Colors", self.on_palette_item, None,
             "Shows your own palette (edit it with Edit Colors).", "check"),
            ("pal_fun", "_Fun Colors", self.on_palette_item, None,
             "Shows magic paints: rainbows, fire, stars, hearts and more.", "check"),
        ])
        self.add_menu(mb, "_Help", [
            ("help_topics", "_Help Topics", lambda: dialogs.help_topics(self), None,
             "Displays Help for the current task or command."),
            None,
            ("about", "_About Paint98", lambda: dialogs.about(self, __version__), None,
             "Displays program information, version number, and copyright."),
        ])
        self.items["send"].set_sensitive(False)
        return mb

    def add_menu(self, parent_shell, title, entries):
        top = Gtk.MenuItem.new_with_mnemonic(title)
        win98.always_underline(top.get_child())
        menu = self.build_menu(entries)
        top.set_submenu(menu)
        top.connect("activate", lambda *a: self.update_menu_state())
        menu.connect("deactivate", self.refresh_sensitivity)
        parent_shell.append(top)
        return menu

    def build_menu(self, entries):
        menu = Gtk.Menu()
        menu.set_accel_group(self.accel)
        menu.connect("realize", self._style_popup)
        for entry in entries:
            if entry is None:
                menu.append(Gtk.SeparatorMenuItem())
                continue
            if entry[1] is None:  # named separator
                sep = Gtk.SeparatorMenuItem()
                self.items[entry[0]] = sep
                menu.append(sep)
                continue
            name, label, action, accel, hint = entry[:5]
            kind = entry[5] if len(entry) > 5 else None
            if kind == "check":
                item = CheckItem(label)
                item.connect("toggled", self._on_check, name, action)
            else:
                item = Gtk.MenuItem.new_with_mnemonic(label)
                if isinstance(action, list):
                    item.set_submenu(self.build_menu(action))
                elif action is not None:
                    item.connect("activate", lambda w, a=action: a())
            if accel:
                key, mods = Gtk.accelerator_parse(accel)
                item.add_accelerator("activate", self.accel, key, mods, Gtk.AccelFlags.VISIBLE)
            item.connect("select", lambda w, h=hint: self.set_hint(h))
            item.connect("deselect", lambda w: self.set_hint(""))
            self.items[name] = item
            menu.append(item)
        return menu

    def _style_popup(self, menu):
        top = menu.get_toplevel()
        if top is not None:
            top.get_style_context().add_class("paint98-popup")
            win98.keep_mnemonics_visible(top)

    _updating = False

    def _on_check(self, item, name, action):
        if self._updating:
            return
        action(name, item.get_active())

    def set_check(self, name, value):
        self._updating = True
        self.items[name].set_active(value)
        self._updating = False

    def refresh_sensitivity(self, *args):
        """Keep item sensitivity current so their accelerators work."""
        sel = self.canvas.selection is not None
        # Undo also cancels a curve/polygon/text in progress, which emits no
        # signal, so leave it enabled here and refine it when the menu opens.
        self.items["undo"].set_sensitive(True)
        self.items["redo"].set_sensitive(self.doc.can_redo())
        for n in ("cut", "copy", "clear_sel", "copy_to", "recolor", "save_sticker"):
            self.items[n].set_sensitive(sel)
        self.items["paste"].set_sensitive(True)
        self.items["grid"].set_sensitive(self.canvas.zoom >= 4)
        self.items["thumb"].set_sensitive(self.canvas.zoom > 1)

    def update_menu_state(self):
        """Full update when a menu opens (includes the clipboard check)."""
        self.refresh_sensitivity()
        self.items["undo"].set_sensitive(self.doc.can_undo() or self.canvas.tool.is_busy())
        clip = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
        self.items["paste"].set_sensitive(clip.wait_is_image_available() and not self.canvas.text_active())
        self.items["v_textbar"].set_sensitive(self.state.tool == "text")
        self.set_check("grid", self.state.show_grid)
        self.set_check("opaque", not self.state.transparent)
        self.sync_palette_checks()
        self.sync_symmetry_checks()
        self.set_check("v_textbar", self.settings.get("textbar", True))

    def refresh_recent(self):
        menu = self.file_menu
        for it in self.recent_items:
            menu.remove(it)
        self.recent_items = []
        sep = self.items["recent_sep"]
        pos = menu.get_children().index(sep)
        recent = self.settings.get("recent", [])
        for i, path in enumerate(recent[:MAX_RECENT]):
            label = "_%d %s" % (i + 1, display_path(os.path.basename(path)).replace("_", "__"))
            item = Gtk.MenuItem.new_with_mnemonic(label)
            item.connect("activate", lambda w, p=path: self.open_path(p, confirm=True))
            item.connect("select", lambda w: self.set_hint("Opens this document."))
            item.connect("deselect", lambda w: self.set_hint(""))
            menu.insert(item, pos)
            pos += 1
            item.show()
            self.recent_items.append(item)
        if recent:
            extra = Gtk.SeparatorMenuItem()
            menu.insert(extra, pos)
            extra.show()
            self.recent_items.append(extra)

    def forget_recent(self, path):
        recent = self.settings.get("recent", [])
        if path in recent:
            self.settings["recent"] = [p for p in recent if p != path]
            self.refresh_recent()

    def add_recent(self, path):
        recent = [p for p in self.settings.get("recent", []) if p != path]
        recent.insert(0, path)
        self.settings["recent"] = recent[:MAX_RECENT]
        self.refresh_recent()

    # -- status bar ---------------------------------------------------------------
    def build_statusbar(self):
        bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=2)
        bar.get_style_context().add_class("statusbar")
        self.hint_label = Gtk.Label(label=DEFAULT_HELP, xalign=0)
        self.hint_label.set_ellipsize(Pango.EllipsizeMode.END)
        hint_box = Gtk.Box()
        hint_box.get_style_context().add_class("status-text")
        hint_box.pack_start(self.hint_label, True, True, 0)
        bar.pack_start(hint_box, True, True, 0)

        def panel(icon):
            box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
            box.get_style_context().add_class("status-panel")
            box.set_size_request(118, -1)
            da = Gtk.DrawingArea()
            da.set_size_request(16, 16)
            da.connect("draw", lambda w, cr: pixmaps.paint(cr, icon, 0, 0) or True)
            box.pack_start(da, False, False, 0)
            lbl = Gtk.Label(xalign=0)
            box.pack_start(lbl, True, True, 0)
            bar.pack_start(box, False, False, 0)
            return lbl

        self.pos_label = panel("STATUS_POS")
        self.size_label = panel("STATUS_SIZE")
        grip = Gtk.EventBox()
        grip.set_size_request(14, 14)
        grip.set_valign(Gtk.Align.END)
        da = Gtk.DrawingArea()
        da.connect("draw", self.draw_grip)
        grip.add(da)
        grip.connect("button-press-event", self.on_grip)
        bar.pack_start(grip, False, False, 0)
        return bar

    def draw_grip(self, w, cr):
        a = w.get_allocation()
        for i in range(3):
            off = 4 * i
            for k, col in ((0, win98.WHITE), (1, win98.SHADOW), (2, win98.SHADOW)):
                cr.set_source_rgb(*col)
                d = 11 - off + k
                for t in range(d + 1):
                    x, y = a.width - 1 - t, a.height - 1 - (d - t)
                    if x >= 0 and y >= 0:
                        cr.rectangle(x, y, 1, 1)
                cr.fill()
        return True

    def on_grip(self, w, ev):
        if ev.button == 1:
            self.begin_resize_drag(Gdk.WindowEdge.SOUTH_EAST, ev.button,
                                   int(ev.x_root), int(ev.y_root), ev.time)
        return True

    def set_hint(self, text):
        self.hint_label.set_text(text or DEFAULT_HELP)

    # -- wiring ---------------------------------------------------------------------
    def connect_signals(self):
        self.connect("delete-event", self.on_delete)
        self.connect("key-press-event", self.on_key)
        self.doc.connect("state-changed", lambda *a: self.update_title())
        self.toolbox.connect("hint", lambda w, t: self.set_hint(t))
        self.colorbox.connect("hint", lambda w, t: self.set_hint(t))
        self.colorbox.connect("edit-color", lambda w, i: self.on_edit_colors(i))
        self.colorbox.connect("palette-index", self.on_palette_index)
        self.colorbox.connect("edit-indicator", self.on_edit_indicator)
        self.canvas.connect("pointer-info", self.on_pointer)
        self.canvas.connect("size-info", self.on_size_info)
        self.canvas.connect("text-box-changed", lambda *a: self.update_textbar())
        self.canvas.connect("context-menu", lambda *a: self.show_context_menu())
        self.state.connect("tool-changed", lambda *a: self.update_textbar())
        self.state.connect("options-changed", lambda *a: self.set_check("opaque", not self.state.transparent))
        self.refresh_recent()
        self.canvas.connect("selection-changed", self.refresh_sensitivity)
        self.canvas.connect("zoom-changed", self.refresh_sensitivity)
        self.doc.connect("state-changed", self.refresh_sensitivity)
        self.state.connect("tool-changed", self.refresh_sensitivity)
        self.state.connect("palette-changed", self.on_palette_changed)
        self.state.connect("options-changed", lambda *a: self.sync_symmetry_checks())
        self.symmetrybar.connect("hint", lambda w, t: self.set_hint(t))
        self.toolbox.connect("open-sticker-book", lambda *a: self.show_sticker_book())
        self.canvas.connect("selection-changed", self.on_selection_for_book)
        self.refresh_sensitivity()

    def on_palette_index(self, colorbox, index):
        self.palette_index = index

    def on_edit_indicator(self, colorbox, which):
        """Edit the current foreground/background colour directly."""
        current = self.state.fg if which == "fg" else self.state.bg
        dlg = self.edit_colors_dialog(solid(current))
        if dlg.run() == dialogs.OK:
            if dlg.custom_changed:
                self.state.set_palette(dlg.custom)
            (self.state.set_fg if which == "fg" else self.state.set_bg)(dlg.color)
        dlg.destroy()

    def on_key(self, w, ev):
        if self.canvas.handle_key(ev):
            return True
        focus = self.get_focus()
        if isinstance(focus, Gtk.Editable):
            # A number box has the focus: let it have the key before any
            # menu shortcut (Delete, Ctrl+Z...) acts on the picture.
            if self.propagate_key_event(ev):
                return True
            if ev.keyval in (Gdk.KEY_Tab, Gdk.KEY_ISO_Left_Tab):
                return False
            ctrl_alt = ev.state & (Gdk.ModifierType.CONTROL_MASK | Gdk.ModifierType.MOD1_MASK)
            if not ctrl_alt:
                return True
            if ev.state & Gdk.ModifierType.CONTROL_MASK and Gdk.keyval_to_lower(ev.keyval) in (Gdk.KEY_z, Gdk.KEY_y):
                return True
        return False

    def on_pointer(self, canvas, x, y, inside):
        self.pos_label.set_text("%d,%d" % (x, y) if inside else "")

    def on_size_info(self, canvas, w, h, valid):
        self.size_label.set_text("%dx%d" % (w, h) if valid else "")

    def update_title(self):
        self.set_title("%s - Paint98" % display_path(self.doc.display_name))

    def update_textbar(self):
        show = self.canvas.text_active() and self.settings.get("textbar", True)
        if show:
            self.textbar.set_no_show_all(False)
            self.textbar.show_all()
        else:
            self.textbar.hide()

    def apply_view_settings(self):
        for key, widget, item in (("toolbox", self.toolbox, "v_toolbox"),
                                  ("colorbox", self.colorbox, "v_colorbox"),
                                  ("statusbar", self.statusbar, "v_statusbar"),
                                  ("settingsbar", self.settingsbar, "v_settingsbar")):
            vis = self.settings.get(key, True)
            widget.set_no_show_all(not vis)
            widget.set_visible(vis)
            self.set_check(item, vis)
        self.set_check("v_textbar", self.settings.get("textbar", True))
        self.set_check("grid", self.state.show_grid)
        self.set_check("opaque", not self.state.transparent)
        self.sync_palette_checks()
        self.sync_symmetry_checks()

    def on_toggle_view(self, name, active):
        if name == "v_history":
            if active:
                if self.history_window is None:
                    self.history_window = HistoryWindow(self)
                self.history_window.show_window()
            elif self.history_window is not None:
                self.history_window.hide()
            return
        if name == "v_textbar":
            self.settings["textbar"] = active
            self.update_textbar()
            return
        key = name[2:]
        widget = getattr(self, key)
        self.settings[key] = active
        widget.set_no_show_all(False)
        widget.set_visible(active)

    def show_context_menu(self):
        menu = self.build_menu([
            ("ctx_cut", "Cu_t", self.on_cut, None, "Cuts the selection and puts it on the Clipboard."),
            ("ctx_copy", "_Copy", self.on_copy, None, "Copies the selection and puts it on the Clipboard."),
            ("ctx_paste", "_Paste", self.on_paste, None, "Inserts the contents of the Clipboard."),
            ("ctx_clear", "C_lear Selection", self.on_clear_selection, None, "Deletes the selection."),
            ("ctx_all", "Select _All", self.on_select_all, None, "Selects everything."),
            None,
            ("ctx_copy_to", "C_opy To...", self.on_copy_to, None, "Copies the selection to a file."),
            ("ctx_paste_from", "Paste _From...", self.on_paste_from, None, "Pastes a file into the selection."),
            None,
            ("ctx_flip", "_Flip/Rotate...", self.on_flip_rotate, None, "Flips or rotates the selection."),
            ("ctx_stretch", "_Stretch/Skew...", self.on_stretch_skew, None, "Stretches or skews the selection."),
            ("ctx_invert", "_Invert Colors", self.on_invert, None, "Inverts the colors of the selection."),
            ("ctx_recolor", "_Recolor Selection", self.on_recolor_selection, None,
             "Paints the selection with the foreground color (Fun Colors too)."),
            ("ctx_sticker", "Save as _Sticker", self.on_save_sticker, None,
             "Adds the selection to My Stickers in the Sticker Book."),
        ])
        menu.attach_to_widget(self.canvas, None)
        menu.show_all()
        menu.popup_at_pointer(None)

    # -- closing / confirmation ---------------------------------------------------
    def confirm_discard(self):
        """Ask before throwing work away. Nothing is committed unless the
        user chooses to save; Cancel leaves everything exactly as it was."""
        pending = self.canvas.has_pending_work()
        if not self.doc.modified and not pending:
            return True
        res = message_box(self, "Paint98", "Save changes to %s?" % self.doc.display_name,
                          ("Yes", "No", "Cancel"))
        if res == 0:
            self.canvas.commit_all()
            return self.on_save()
        if res == 1:
            self.canvas.discard_pending()
            return True
        return False

    def jump_to_history(self, index):
        """Undo or redo until the picture is at step `index`."""
        names, current = self.doc.history()
        index = max(0, min(index, len(names) - 1))
        while current != index:
            if current > index:
                self.canvas.undo()
            else:
                self.canvas.redo()
            _, now = self.doc.history()
            if now == current:
                break  # nothing more to undo/redo
            current = now

    def recover(self, png_path, info):
        """Open an autosaved recovery copy as unsaved work."""
        filename = info.get("filename") if isinstance(info.get("filename"), str) else None
        try:
            self.canvas.discard_pending()
            self.doc.recover(png_path, filename)
        except Exception as e:  # a damaged recovery file must not stop start-up
            self.error("Paint98 could not recover the picture.\n\n%s" % e)
            return False
        self.autosaver.save_now()
        return True

    def on_delete(self, *a):
        if not self.confirm_discard():
            return True
        self.save_settings()
        return False

    def error(self, text):
        message_box(self, "Paint98", text, ("OK",))

    # -- file ------------------------------------------------------------------------
    def file_dialog(self, title, action, name=None, filters=IMAGE_FILTERS, all_images=True):
        dlg = Gtk.FileChooserNative.new(title, self, action, None, None)
        dlg.set_modal(True)
        chosen = {}
        if action == Gtk.FileChooserAction.OPEN and all_images:
            f = Gtk.FileFilter()
            f.set_name("All Picture Files")
            f.add_pixbuf_formats()
            dlg.add_filter(f)
        for fname, patterns, ext in filters:
            f = Gtk.FileFilter()
            f.set_name(fname)
            for p in patterns:
                f.add_pattern(p)
                f.add_pattern(p.upper())
            chosen[fname] = ext
            dlg.add_filter(f)
        if action == Gtk.FileChooserAction.OPEN:
            f = Gtk.FileFilter()
            f.set_name("All Files")
            f.add_pattern("*")
            dlg.add_filter(f)
        if action == Gtk.FileChooserAction.SAVE:
            dlg.set_do_overwrite_confirmation(True)
            if name:
                dlg.set_current_name(name)
            if self.doc.filename:
                dlg.set_current_folder(os.path.dirname(self.doc.filename))
        res = dlg.run()
        path = dlg.get_filename() if res == Gtk.ResponseType.ACCEPT else None
        flt = dlg.get_filter()
        dlg.destroy()
        if path and action == Gtk.FileChooserAction.SAVE and not os.path.splitext(path)[1]:
            ext = chosen.get(flt.get_name() if flt else "", filters[0][2])
            # Under the file chooser portal only the exact chosen name may be
            # written, so the file keeps that name (the format still follows
            # the chosen file type). Elsewhere add the extension, asking
            # before replacing a file the chooser didn't check.
            self.save_format_hint = ext
            if not in_document_portal(path):
                candidate = path + ext
                if os.path.exists(candidate):
                    res = message_box(self, title, "%s already exists.\nDo you want to replace it?"
                                      % display_path(os.path.basename(candidate)), ("Yes", "No"),
                                      default=1)
                    if res != 0:
                        return None
                path = candidate
        return path

    def on_new(self):
        if not self.confirm_discard():
            return
        self.canvas.discard_selection()
        self.doc.new(self.doc.width, self.doc.height)
        self.autosaver.clear()

    def on_open(self):
        if not self.confirm_discard():
            return
        path = self.file_dialog("Open", Gtk.FileChooserAction.OPEN)
        if path:
            self.open_path(path)

    def open_path(self, path, confirm=False):
        if confirm and not self.confirm_discard():
            return False
        try:
            self.doc.load(path)
        except imageops.TooBig as e:
            self.error("Paint98 cannot open %s.\n\n%s" % (display_path(path), e))
            return False
        except (GLib.Error, cairo.Error, MemoryError) as e:
            msg = getattr(e, "message", None) or str(e)
            self.error("Paint98 cannot read this file.\n%s\nThis is not a valid bitmap file, or its "
                       "format is not currently supported.\n\n%s" % (display_path(path), msg))
            self.forget_recent(path)
            return False
        self.canvas.discard_selection()
        self.add_recent(path)
        self.autosaver.clear()
        return False

    def on_save(self):
        self.canvas.commit_all()
        if not self.doc.filename or not Document.format_for(self.doc.filename):
            return self.on_save_as()
        return self.save_to(self.doc.filename)

    def check_save_name(self, path):
        """Refuse names whose extension Paint98 can't write (e.g. .gif),
        instead of putting PNG data under that name."""
        ext = os.path.splitext(path)[1]
        if ext and not Document.format_for(path):
            self.error("Paint98 cannot save pictures as %s files.\n\n"
                       "Please choose PNG, BMP, JPEG or TIFF." % display_path(ext))
            return False
        return True

    def save_format(self, path):
        """Format for a path; files without an extension use the type that
        was picked in the file chooser."""
        fmt = Document.format_for(path)
        if fmt is None and not os.path.splitext(path)[1]:
            fmt = Document.format_for("x" + getattr(self, "save_format_hint", ".png"))
        return fmt or "png"

    def on_save_as(self):
        self.canvas.commit_all()
        if self.doc.filename:
            name = display_path(os.path.basename(self.doc.filename))
            if not Document.format_for(name):
                name = os.path.splitext(name)[0] + ".png"
        else:
            name = "untitled.png"
        path = self.file_dialog("Save As", Gtk.FileChooserAction.SAVE, name)
        if not path:
            return False
        return self.save_to(path)

    def save_to(self, path):
        if not self.check_save_name(path):
            return False
        try:
            self.doc.save(path, fmt=self.save_format(path))
        except (GLib.Error, OSError) as e:
            self.error("Paint98 cannot save this file.\n\n%s" % (getattr(e, "message", None) or e))
            return False
        self.add_recent(path)
        if not self.canvas.has_pending_work():
            self.autosaver.clear()
        return True

    # printing
    def _print_op(self):
        op = Gtk.PrintOperation()
        op.set_n_pages(1)
        op.set_job_name(self.doc.display_name)
        if self.print_settings:
            op.set_print_settings(self.print_settings)
        if self.page_setup:
            op.set_default_page_setup(self.page_setup)
        op.connect("draw-page", self._draw_page)
        return op

    def _draw_page(self, op, ctx, page_nr):
        cr = ctx.get_cairo_context()
        surf = self.doc.surface
        w, h = surf.get_width(), surf.get_height()
        pw, ph = ctx.get_width(), ctx.get_height()
        scale = self.picture_rect_on_page(pw, ph, ctx.get_dpi_x())
        cr.scale(scale, scale)
        cr.set_source_surface(surf, 0, 0)
        cr.get_source().set_filter(cairo.FILTER_NEAREST)
        cr.paint()

    def on_print(self):
        self.canvas.commit_all()
        op = self._print_op()
        res = op.run(Gtk.PrintOperationAction.PRINT_DIALOG, self)
        if res == Gtk.PrintOperationResult.APPLY:
            self.print_settings = op.get_print_settings()

    def on_print_preview(self):
        self.canvas.commit_all()
        PrintPreviewWindow(self).show_all()

    def picture_rect_on_page(self, page_w, page_h, dpi=72.0):
        """Where the picture goes on a printable area (same rule as printing):
        96 pixels per inch, shrunk to fit."""
        w, h = self.doc.width, self.doc.height
        scale = min(dpi / 96.0, page_w / w, page_h / h)
        return scale

    def on_page_setup(self):
        if self.print_settings is None:
            self.print_settings = Gtk.PrintSettings()
        self.page_setup = Gtk.print_run_page_setup_dialog(self, self.page_setup, self.print_settings)

    def on_wallpaper(self, mode):
        self.canvas.commit_all()
        source = Gio.SettingsSchemaSource.get_default()
        schema = source.lookup("org.gnome.desktop.background", True) if source else None
        if schema is None:
            self.error("Paint98 cannot set the wallpaper on this desktop.")
            return
        folder = wallpaper_dir()
        for old in os.listdir(folder):
            if old.startswith("wallpaper-"):
                try:
                    os.remove(os.path.join(folder, old))
                except OSError:
                    pass
        path = os.path.join(folder, "wallpaper-%d.png" % int(time.time()))
        try:
            self.doc.save(path, surface=self.doc.surface)
        except GLib.Error as e:
            self.error("Paint98 cannot save the wallpaper.\n\n%s" % e.message)
            return
        uri = GLib.filename_to_uri(path, None)
        settings = Gio.Settings.new("org.gnome.desktop.background")
        settings.set_string("picture-uri", uri)
        if schema.has_key("picture-uri-dark"):
            settings.set_string("picture-uri-dark", uri)
        settings.set_string("picture-options", mode)
        Gio.Settings.sync()

    # -- edit ------------------------------------------------------------------------
    def canvas_undo(self):
        self.canvas.undo()

    def canvas_redo(self):
        self.canvas.redo()

    def selection_surface(self):
        sel = self.canvas.selection
        if sel is None:
            return None
        return sel.baked()

    def on_copy(self):
        surf = self.selection_surface()
        if surf is None:
            return
        clip = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
        clip.set_image(surface_to_pixbuf(surf))
        clip.store()

    def on_cut(self):
        if self.canvas.selection is None:
            return
        self.on_copy()
        self.on_clear_selection()

    def on_clear_selection(self):
        if self.canvas.selection is None:
            return
        self.canvas.lift_selection(label="Clear Selection")
        self.canvas.discard_selection()

    def on_select_all(self):
        self.canvas.commit_all()
        self.state.set_tool("rect_select")
        self.canvas.create_selection(0, 0, self.doc.width, self.doc.height)

    def float_pixbuf(self, pb):
        try:
            imageops.check_size(pb.get_width(), pb.get_height())
        except imageops.TooBig as e:
            self.error("Paint98 cannot paste this picture.\n\n%s" % e)
            return
        surf = pixbuf_to_surface(pb, self.state.bg)
        w, h = surf.get_width(), surf.get_height()
        if w > self.doc.width or h > self.doc.height:
            res = message_box(self, "Paint98",
                              "The image in the clipboard is larger than the bitmap.\n"
                              "Would you like the bitmap enlarged?", ("Yes", "No", "Cancel"))
            if res == 0:
                self.canvas.commit_all()
                if not self.guard(self.doc.resize, max(w, self.doc.width), max(h, self.doc.height),
                                  self.state.bg):
                    return
            elif res != 1:
                return
        x, y = self.canvas.visible_origin()
        self.canvas.float_surface(surf, x, y)

    def on_paste(self):
        clip = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
        if self.canvas.text_active():
            # Typing text: paste text into the text box, like the original.
            text = clip.wait_for_text()
            if text:
                self.canvas.tool.insert(text)
            return
        pb = clip.wait_for_image()
        if pb is not None:
            self.float_pixbuf(pb)

    def on_copy_to(self):
        surf = self.selection_surface()
        if surf is None:
            return
        path = self.file_dialog("Copy To", Gtk.FileChooserAction.SAVE, "untitled.png")
        if path and self.check_save_name(path):
            try:
                self.doc.save(path, surface=surf, fmt=self.save_format(path))
            except (GLib.Error, OSError) as e:
                self.error("Paint98 cannot save this file.\n\n%s" % (getattr(e, "message", None) or e))

    def on_paste_from(self):
        path = self.file_dialog("Paste From", Gtk.FileChooserAction.OPEN)
        if not path:
            return
        try:
            _, w, h = GdkPixbuf.Pixbuf.get_file_info(path)
            imageops.check_size(w, h)
            pb = GdkPixbuf.Pixbuf.new_from_file(path)
        except imageops.TooBig as e:
            self.error("Paint98 cannot paste this picture.\n\n%s" % e)
            return
        except (GLib.Error, TypeError) as e:
            self.error("Paint98 cannot read this file.\n\n%s" % (getattr(e, "message", None) or e))
            return
        self.float_pixbuf(pb)

    # -- view ------------------------------------------------------------------------
    def on_custom_zoom(self):
        dlg = dialogs.CustomZoomDialog(self, self.canvas.zoom)
        if dlg.run() == dialogs.OK:
            self.canvas.set_zoom(dlg.result())
        dlg.destroy()

    def on_toggle_grid(self, name, active):
        self.state.set_option("show_grid", active)

    def on_toggle_thumbnail(self, name, active):
        if self.thumbnail is None:
            self.thumbnail = ThumbnailWindow(self, self.canvas)
            self.thumbnail.on_closed = lambda: self.set_check("thumb", False)
        if active:
            self.thumbnail.show_all()
        else:
            self.thumbnail.hide()

    def on_replay(self):
        self.canvas.commit_all()
        frames = self.recorder.snapshot()
        player = ReplayWindow(self, frames, lambda win: self.save_replay(frames, win))
        player.set_destroy_with_parent(True)
        player.show_all()

    def on_save_replay(self):
        self.canvas.commit_all()
        self.save_replay(self.recorder.snapshot(), self)

    def save_replay(self, frames, parent):
        base = os.path.splitext(self.doc.display_name)[0] or "untitled"
        path = self.file_dialog("Save Replay As", Gtk.FileChooserAction.SAVE, base + "-replay.gif",
                                filters=[("Animated GIF (*.gif)", ["*.gif"], ".gif")])
        if not path:
            return

        def done(error):
            if error is not None:
                message_box(parent, "Paint98", "Paint98 cannot save the replay.\n\n%s" % error, ("OK",))

        export_gif(parent, frames, path, done)

    def on_view_bitmap(self):
        self.canvas.commit_all()
        BitmapViewer(self, imageops.copy_surface(self.doc.surface)).show_all()

    # -- image -----------------------------------------------------------------------
    def guard(self, fn, *args):
        """Run a picture operation; report pictures that would be too big
        instead of crashing. Returns True on success."""
        try:
            fn(*args)
            return True
        except imageops.TooBig as e:
            self.error(str(e))
        except (cairo.Error, MemoryError) as e:
            self.error("Paint98 does not have enough memory for this picture.\n\n%s" % e)
        return False

    def apply_transform(self, fn, label="Change"):
        return self.guard(self._apply_transform, fn, label)

    def _apply_transform(self, fn, label):
        sel = self.canvas.selection
        if sel is not None:
            # Compute first, so a failure leaves the selection untouched.
            sel.bake()
            result = fn(imageops.copy_surface(sel.content))
            self.canvas.lift_selection(label=label)
            sel.set_content(result)
            self.canvas.picture_changed()
        else:
            self.canvas.commit_all()
            self.doc.replace_surface(fn(imageops.copy_surface(self.doc.surface)), label=label)

    def on_flip_rotate(self):
        dlg = dialogs.FlipRotateDialog(self)
        if dlg.run() == dialogs.OK:
            kind, arg = dlg.result()
            if kind == "flip":
                self.apply_transform(lambda s: imageops.flip(s, arg), "Flip")
            else:
                self.apply_transform(lambda s: imageops.rotate(s, arg), "Rotate")
        dlg.destroy()

    def on_stretch_skew(self):
        dlg = dialogs.StretchSkewDialog(self)
        if dlg.run() == dialogs.OK:
            sh, sv, kh, kv = dlg.result()
            bg = None if self.canvas.selection is not None else self.state.bg

            def fn(s):
                if (sh, sv) != (100, 100):
                    s = imageops.scale(s, s.get_width() * sh / 100, s.get_height() * sv / 100)
                if kh or kv:
                    # Selections get transparent corners; the picture gets
                    # the background colour.
                    s = imageops.skew(s, kh, kv, bg)
                return s

            self.apply_transform(fn, "Stretch/Skew")
        dlg.destroy()

    def on_invert(self):
        def fn(s):
            imageops.invert(s)
            return s

        self.apply_transform(fn, "Invert Colors")

    def selection_sticker_surface(self):
        sel = self.canvas.selection
        if sel is None:
            return None
        return sel.render(self.state.transparent, self.state.bg)

    def show_sticker_book(self):
        if self.sticker_book is None:
            self.sticker_book = StickerBook(self, self.state, self.selection_sticker_surface)
        self.sticker_book.sync_buttons()
        self.sticker_book.show_all()
        self.sticker_book.present()

    def on_selection_for_book(self, *a):
        if self.sticker_book is not None and self.sticker_book.get_visible():
            self.sticker_book.sync_buttons()

    def on_save_sticker(self):
        surf = self.selection_sticker_surface()
        if surf is None:
            return
        try:
            sid = stickers.save_user_sticker(surf)
        except (OSError, cairo.Error) as e:
            self.error("Paint98 cannot save the sticker.\n\n%s" % e)
            return
        if sid is None:
            return
        self.state.choose_sticker(sid)
        if self.sticker_book is not None:
            self.sticker_book.reload("My Stickers")
        self.set_hint("Saved to My Stickers. Pick the Sticker tool to stamp it.")

    def on_recolor_selection(self):
        sel = self.canvas.selection
        if sel is None:
            return
        self.canvas.lift_selection(label="Recolor Selection")
        sel.bake()
        src = sel.content
        w, h = src.get_width(), src.get_height()
        out = imageops.copy_surface(src)
        cr = cairo.Context(out)
        cr.push_group()
        set_paint(cr, self.state.fg, (0, 0, w - 1, h - 1))
        cr.mask_surface(src, 0, 0)  # only where something is selected
        cr.pop_group_to_source()
        cr.paint_with_alpha(self.state.tool_opacity("fill"))
        sel.set_content(out)
        self.canvas.picture_changed()

    def on_attributes(self):
        self.canvas.commit_all()
        info = None
        if self.doc.filename and os.path.exists(self.doc.filename):
            st = os.stat(self.doc.filename)
            info = (time.strftime("%d/%m/%Y %H:%M", time.localtime(st.st_mtime)),
                    "{:,} bytes".format(st.st_size))
        dlg = dialogs.AttributesDialog(self, self.doc.width, self.doc.height, info,
                                       colors=not self.doc.monochrome)
        try:
            if dlg.run() != dialogs.OK:
                return
            w, h, colors = dlg.result()
        finally:
            dlg.destroy()
        if not self.guard(self.doc.resize, w, h, self.state.bg):
            return
        if not colors and not self.doc.monochrome:
            res = message_box(self, "Paint98", "Converting to black-and-white will lose color "
                              "information. Do you want to continue?", ("Yes", "No"))
            if res == 0:
                def fn(s):
                    imageops.to_black_and_white(s)
                    return s
                if self.apply_transform(fn, "Black and White"):
                    self.doc.monochrome = True
        elif colors:
            self.doc.monochrome = False

    def on_clear_image(self):
        sel = self.canvas.selection
        if sel is not None:
            self.on_clear_selection()
            return
        self.canvas.commit_all()
        self.doc.push_undo("Clear Image")
        cr = cairo.Context(self.doc.surface)
        imageops.set_rgb(cr, self.state.bg)
        cr.paint()
        self.doc.changed()

    def on_toggle_opaque(self, name, active):
        self.state.set_option("transparent", not active)

    # -- options -----------------------------------------------------------------------
    def on_edit_colors(self, index=None):
        if index is None:
            index = self.palette_index
        st = self.state
        start = index if st.palette_mode == "custom" else 0
        dlg = self.edit_colors_dialog(solid(st.palette[index]), start)
        if dlg.run() == dialogs.OK:
            if dlg.custom_changed:
                # Colours were added to the custom boxes: show them all.
                st.set_palette(dlg.custom)
            elif st.palette_mode != "fun":
                # The fun palette is fixed: just paint with the chosen colour.
                st.set_palette_color(index, dlg.color)
            st.set_fg(dlg.color)
        dlg.destroy()

    def edit_colors_dialog(self, color, start_index=0):
        return dialogs.EditColorsDialog(self, color, custom=self.state.custom_palette,
                                        start_index=start_index)

    def on_get_colors(self):
        path = self.file_dialog("Get Colors", Gtk.FileChooserAction.OPEN,
                                filters=[("Palette (*.pal)", ["*.pal"], ".pal")], all_images=False)
        if not path:
            return
        try:
            self.state.set_palette(read_pal(path))
        except (OSError, ValueError, struct.error):
            self.error("Paint98 cannot read this palette file.")

    def on_save_colors(self):
        path = self.file_dialog("Save Colors", Gtk.FileChooserAction.SAVE, "untitled.pal",
                                filters=[("Palette (*.pal)", ["*.pal"], ".pal")])
        if not path:
            return
        try:
            write_pal(path, [solid(c) for c in self.state.palette])
        except OSError as e:
            self.error("Paint98 cannot save this palette file.\n\n%s" % e)
