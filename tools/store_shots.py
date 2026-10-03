#!/usr/bin/env python3
"""Produce the store/README screenshots by drawing with the real tools.

usage: GDK_BACKEND=x11 tools/store_shots.py OUTDIR

Windows are shown briefly on screen and captured; each shot is placed on a
classic teal desktop. Settings and data go to a temporary folder.
"""

import math
import os
import sys
import tempfile

tmp = tempfile.mkdtemp(prefix="paint98-shots-")
os.environ["XDG_CONFIG_HOME"] = os.path.join(tmp, "config")
os.environ["XDG_DATA_HOME"] = os.path.join(tmp, "data")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import gi  # noqa: E402

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, GLib, Gtk  # noqa: E402

import cairo  # noqa: E402

from paint98 import app as appmod  # noqa: E402
from paint98.funpaints import CRAYONS, FUN_PAINTS  # noqa: E402

OUT = sys.argv[1]
os.makedirs(OUT, exist_ok=True)
FUN = {p.name: p for p in FUN_PAINTS}
TEAL = (0, 0.5, 0.5)


def pump(ms=300):
    end = GLib.get_monotonic_time() + ms * 1000
    while GLib.get_monotonic_time() < end:
        while Gtk.events_pending():
            Gtk.main_iteration()


def grab(widget):
    gw = widget.get_window()
    pb = Gdk.pixbuf_get_from_window(gw, 0, 0, gw.get_width(), gw.get_height())
    surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, pb.get_width(), pb.get_height())
    cr = cairo.Context(surf)
    Gdk.cairo_set_source_pixbuf(cr, pb, 0, 0)
    cr.paint()
    return surf


def compose(name, size, parts):
    """parts: list of (surface, x, y) on a teal desktop."""
    w, h = size
    out = cairo.ImageSurface(cairo.FORMAT_RGB24, w, h)
    cr = cairo.Context(out)
    cr.set_source_rgb(*TEAL)
    cr.paint()
    for surf, x, y in parts:
        cr.set_source_rgba(0, 0, 0, 0.35)  # soft drop shadow
        cr.rectangle(x + 8, y + 8, surf.get_width(), surf.get_height())
        cr.fill()
        cr.set_source_surface(surf, x, y)
        cr.paint()
    path = os.path.join(OUT, name)
    out.write_to_png(path)
    print("wrote", path)


def use(win, tool, pts, button=1, mods=0):
    st, c = win.state, win.canvas
    st.set_tool(tool)
    t = c.tool
    t.press(*pts[0], button, mods)
    for p in pts[1:]:
        t.drag(*p, mods)
    t.release(*pts[-1], button, mods)
    win.recorder.capture()  # a frame per step for the Replay shot


def stamp(win, sid, size, at):
    win.state.choose_sticker(sid)
    win.state.set_tool_size("sticker", size)
    use(win, "sticker", [at])


def landscape(win):
    st, doc = win.state, win.doc
    doc.new(780, 470)
    # Sky: linear gradient fill.
    st.set_fg((110, 180, 255))
    st.set_bg((235, 245, 255))
    st.set_option("fill_mode", 1)
    use(win, "fill", [(390, 0), (390, 330)])
    st.set_option("fill_mode", 0)
    # Ground.
    st.set_fg((60, 170, 70))
    st.set_option("fill_style", 2)
    use(win, "rectangle", [(0, 340), (779, 469)])
    # Rainbow arc with the Rainbow paint.
    st.set_fg(FUN["Rainbow"])
    st.choose_brush_preset(0)
    st.set_tool_size("brush", 22)
    arc = [(390 + int(250 * math.cos(math.radians(a))), 345 - int(230 * math.sin(math.radians(a))))
           for a in range(180, -1, -3)]
    use(win, "brush", arc)
    stamp(win, "px:Sun", 110, (690, 80))
    stamp(win, "px:Cloud", 96, (190, 70))
    stamp(win, "px:Cloud", 80, (500, 50))
    stamp(win, "px:House", 150, (250, 300))
    stamp(win, "px:Tree", 150, (570, 290))
    stamp(win, "emoji:🦋", 56, (420, 190))
    stamp(win, "emoji:🐶", 64, (120, 400))
    # A trail of flowers along the bottom.
    win.state.choose_sticker("emoji:🌷")
    win.state.set_tool_size("sticker", 30)
    use(win, "sticker", [(330, 445), (760, 445)])
    # Rainbow text.
    st.set_option("transparent", True)
    st.set_option("font_size", 30)
    st.set_option("font_bold", True)
    st.set_fg(FUN["Sunset"])
    st.set_tool("text")
    t = win.canvas.tool
    t.press(24, 14, 1, 0)
    t.drag(330, 60, 0)
    t.release(330, 60, 1, 0)
    t.insert("Hello, Paint98!")
    t.commit()
    st.set_option("transparent", False)
    st.set_fg((0, 0, 0))
    st.set_bg((255, 255, 255))


def mandala(win):
    st, doc = win.state, win.doc
    doc.new(560, 560)
    st.set_option("symmetry", "kaleido8")
    st.choose_brush_preset(0)
    st.set_fg(FUN["Rainbow"])
    st.set_tool_size("brush", 10)
    use(win, "brush", [(280 + int(r * math.cos(r / 18)), 280 - int(r * 0.55) + int(18 * math.sin(r / 9)))
                       for r in range(20, 250, 3)])
    st.set_fg(FUN["Neon"])
    st.set_tool_size("brush", 6)
    use(win, "brush", [(280 + r, 280 - int(60 * math.sin(r / 25))) for r in range(30, 260, 4)])
    st.set_fg(FUN["Stars"])
    st.set_option("fill_style", 2)
    use(win, "ellipse", [(330, 200), (380, 250)])
    stamp(win, "emoji:🌟", 40, (280, 120))
    stamp(win, "emoji:💜", 34, (360, 330))
    st.set_fg(FUN["Fire"])
    st.set_tool_size("pencil", 3)
    use(win, "pencil", [(280, 280), (420, 140)])
    st.set_tool("brush")


def run(app):
    win = app.get_windows()[0]
    win.resize(1000, 700)
    win.move(40, 40)
    pump(600)

    # 1. Landscape with the Fun Colors palette on.
    landscape(win)
    win.state.set_palette_mode("fun")
    win.state.set_tool("brush")
    pump(500)
    main1 = grab(win)
    compose("01-landscape.png", (1120, 820), [(main1, 60, 50)])

    # 2. Sticker Book over the picture.
    win.state.set_palette_mode("original")
    win.show_sticker_book()
    book = win.sticker_book
    book.list.select_row(book.list.get_row_at_index(2))  # Animals
    pump(600)
    main2 = grab(win)
    book_img = grab(book)
    book.hide()
    compose("02-sticker-book.png", (1120, 820), [(main2, 40, 30), (book_img, 560, 380)])

    # 3. Kaleidoscope mandala with symmetry.
    mandala(win)
    win.state.set_palette_mode("fun")
    pump(500)
    main3 = grab(win)
    compose("03-kaleidoscope.png", (1120, 820), [(main3, 60, 50)])
    win.state.set_option("symmetry", "off")

    # 4. Classic menus and the Edit Colors dialog.
    landscape(win)
    win.state.set_palette_mode("original")
    win.state.set_tool("rect_select")
    pump(300)
    items = win.menubar.get_children()
    image_item = items[3]
    sub = image_item.get_submenu()
    win.update_menu_state()
    win.menubar.select_item(image_item)
    sub.popup_at_widget(image_item, Gdk.Gravity.SOUTH_WEST, Gdk.Gravity.NORTH_WEST, None)
    pump(600)
    main4 = grab(win)
    menu_img = grab(sub.get_toplevel())
    menu_pos = image_item.translate_coordinates(win, 0, 0)
    sub.popdown()
    from paint98 import dialogs
    dlg = dialogs.EditColorsDialog(win, (255, 128, 64), custom=list(CRAYONS) + [(255, 255, 255)] * 14)
    dlg.on_define()
    dlg.show_all()
    pump(600)
    dlg_img = grab(dlg)
    dlg.destroy()
    mx, my = menu_pos[0] + 4, menu_pos[1] + image_item.get_allocated_height()
    compose("04-classic.png", (1120, 820), [(main4, 40, 30), (menu_img, 40 + mx, 30 + my),
                                            (dlg_img, 1120 - dlg_img.get_width() - 40, 820 - dlg_img.get_height() - 30)])

    # 5. Replay window.
    frames = win.recorder.snapshot()
    from paint98.replay import ReplayWindow
    player = ReplayWindow(win, frames, lambda w: None)
    player.show_all()
    pump(300)
    player.stop()
    player.show_frame(int(len(frames) * 0.6))
    pump(600)
    rep = grab(player)
    player.destroy()
    compose("05-replay.png", (1120, 820), [(main1, 30, 20), (rep, 1120 - rep.get_width() - 40, 820 - rep.get_height() - 40)])

    win.doc.modified = False
    app.quit()


application = appmod.PaintApp()
application.connect("activate", lambda a: GLib.timeout_add(800, lambda: run(a) and False))
application.run([])
