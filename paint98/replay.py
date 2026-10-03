"""Replay: record the picture while it is drawn, play it back, save a GIF."""

import threading
import zlib

import cairo
import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gdk, GLib, Gtk  # noqa: E402

from . import gif, win98  # noqa: E402
from .settingsbar import Trackbar  # noqa: E402
from .win98 import Win98Dialog, Win98Window, make_button  # noqa: E402

MAX_SIDE = 640        # frames are stored (and exported) at most this big
INTERVAL_MS = 120     # at most one frame this often while drawing
MAX_FRAMES = 3000     # older frames are thinned out beyond this
GIF_MAX_FRAMES = 300  # exported GIFs are thinned to about this many frames


class Frame:
    __slots__ = ("w", "h", "stride", "data")

    def __init__(self, surf):
        surf.flush()
        self.w, self.h, self.stride = surf.get_width(), surf.get_height(), surf.get_stride()
        self.data = zlib.compress(bytes(surf.get_data()), 1)

    def surface(self):
        buf = bytearray(zlib.decompress(self.data))
        return cairo.ImageSurface.create_for_data(buf, cairo.FORMAT_ARGB32, self.w, self.h, self.stride)


def _fit(surf, max_side=MAX_SIDE):
    w, h = surf.get_width(), surf.get_height()
    scale = min(1.0, max_side / max(w, h))
    if scale >= 1:
        return surf
    nw, nh = max(1, round(w * scale)), max(1, round(h * scale))
    out = cairo.ImageSurface(cairo.FORMAT_ARGB32, nw, nh)
    cr = cairo.Context(out)
    cr.scale(nw / w, nh / h)
    cr.set_source_surface(surf, 0, 0)
    cr.get_source().set_filter(cairo.FILTER_NEAREST)
    cr.paint()
    return out


class Recorder:
    """Takes a snapshot of the visible picture shortly after it changes."""

    def __init__(self, canvas, doc):
        self.canvas = canvas
        self.doc = doc
        self.frames = []
        self._last = None
        self._timer = None
        doc.connect("changed", self.note)
        doc.connect("reset", lambda *a: self.reset())
        canvas.connect("picture-changed", self.note)
        self.reset()

    def reset(self):
        self.frames = []
        self._last = None
        self.capture()

    def note(self, *args):
        if self._timer is None:
            self._timer = GLib.timeout_add(INTERVAL_MS, self._tick)

    def _tick(self):
        self._timer = None
        self.capture()
        return False

    def capture(self):
        frame = Frame(_fit(self.canvas.composite_picture()))
        key = (frame.w, frame.h, frame.data)
        if key == self._last:
            return
        self._last = key
        self.frames.append(frame)
        if len(self.frames) > MAX_FRAMES:
            # Keep the first and last frames, drop every other one in between.
            self.frames = [self.frames[0]] + self.frames[1:-1:2] + [self.frames[-1]]

    def snapshot(self):
        """Frames including the current state (flushes a pending capture)."""
        if self._timer is not None:
            GLib.source_remove(self._timer)
            self._timer = None
        self.capture()
        return list(self.frames)


def thin(frames, limit):
    if len(frames) <= limit:
        return frames
    step = len(frames) / (limit - 1)
    picked = [frames[min(len(frames) - 1, round(i * step))] for i in range(limit - 1)]
    return picked + [frames[-1]]


def export_gif(parent, frames, path, on_done=None):
    """Write frames to path in a background thread with a progress dialog."""
    frames = thin(frames, GIF_MAX_FRAMES)
    width = max(f.w for f in frames)
    height = max(f.h for f in frames)

    def surfaces():
        for f in frames:
            s = f.surface()
            if (f.w, f.h) == (width, height):
                yield s
                continue
            # The picture changed size: place it on a white page.
            page = cairo.ImageSurface(cairo.FORMAT_ARGB32, width, height)
            cr = cairo.Context(page)
            cr.set_source_rgb(1, 1, 1)
            cr.paint()
            cr.set_source_surface(s, 0, 0)
            cr.paint()
            yield page

    dlg = ProgressDialog(parent, "Saving Replay", "Saving %s..." % GLib.path_get_basename(path))
    state = {"error": None}

    def progress(fraction):
        GLib.idle_add(dlg.set_fraction, fraction)

    def work():
        try:
            gif.write_gif(path, surfaces, len(frames), progress=progress)
        except Exception as e:  # report any failure in the UI thread
            state["error"] = e
        GLib.idle_add(finish)

    def finish():
        dlg.destroy()
        if on_done:
            on_done(state["error"])
        return False

    dlg.show_all()
    threading.Thread(target=work, daemon=True).start()


class ProgressDialog(Win98Dialog):
    def __init__(self, parent, title, text):
        super().__init__(parent, title, help_button=False)
        self.fraction = 0.0
        self.content.pack_start(Gtk.Label(label=text, xalign=0), False, False, 0)
        self.bar = Gtk.DrawingArea()
        self.bar.set_size_request(260, 20)
        self.bar.connect("draw", self.draw_bar)
        self.content.pack_start(self.bar, False, False, 4)
        self.titlebar.buttons["close"].set_sensitive(False)

    def set_fraction(self, f):
        self.fraction = max(0.0, min(1.0, f))
        self.bar.queue_draw()
        return False

    def request_close(self):
        pass

    def draw_bar(self, w, cr):
        width, height = w.get_allocated_width(), w.get_allocated_height()
        win98.sunken_thin(cr, 0, 0, width, height)
        # Classic progress: separate navy blocks.
        inner = width - 4
        filled = int(inner * self.fraction)
        cr.set_source_rgb(0, 0, 0.5)
        x = 2
        while x + 8 <= 2 + filled:
            cr.rectangle(x, 2, 8, height - 4)
            x += 10
        cr.fill()
        return True


class ReplayWindow(Win98Window):
    """Plays the recorded frames like a little video player."""

    SPEEDS = [1, 2, 4, 8]

    def __init__(self, parent, frames, save_cb):
        super().__init__("Replay - Paint98", buttons=("close",), icon=True)
        self.set_transient_for(parent)
        self.set_type_hint(Gdk.WindowTypeHint.DIALOG)
        self.frames = frames
        self.save_cb = save_cb
        self.index = 0
        self.speed = 1
        self.timer = None
        self._cache = (None, None)

        fw = max(f.w for f in frames)
        fh = max(f.h for f in frames)
        scale = min(1.0, 560 / fw, 420 / fh)
        field = Gtk.Box()
        field.get_style_context().add_class("win98-field")
        self.view = Gtk.DrawingArea()
        self.view.set_size_request(max(240, int(fw * scale)), max(160, int(fh * scale)))
        self.view.connect("draw", self.on_draw)
        field.pack_start(self.view, True, True, 0)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        box.set_border_width(8)
        box.pack_start(field, True, True, 0)

        self.track = Trackbar(0, max(1, len(frames) - 1), 0, width=300)
        self.track.connect("value-changed", self.on_seek)
        box.pack_start(self.track, False, False, 0)

        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self.play_btn = make_button("_Play", self.toggle_play, default=True)
        row.pack_start(self.play_btn, False, False, 0)
        row.pack_start(make_button("_Restart", self.restart), False, False, 0)
        self.speed_btn = make_button("Speed: _1x", self.cycle_speed)
        row.pack_start(self.speed_btn, False, False, 0)
        self.label = Gtk.Label(xalign=0)
        row.pack_start(self.label, True, True, 6)
        row.pack_end(make_button("_Close", self.close), False, False, 0)
        row.pack_end(make_button("_Save as GIF...", lambda: self.save_cb(self)), False, False, 0)
        box.pack_start(row, False, False, 0)
        self.body.pack_start(box, True, True, 0)
        self.connect("destroy", lambda *a: self.stop())
        self.update_label()
        GLib.idle_add(self.play)

    def frame_surface(self, i):
        if self._cache[0] != i:
            self._cache = (i, self.frames[i].surface())
        return self._cache[1]

    def on_draw(self, w, cr):
        width, height = w.get_allocated_width(), w.get_allocated_height()
        cr.set_source_rgb(*win98.SHADOW)
        cr.paint()
        surf = self.frame_surface(self.index)
        sw, sh = surf.get_width(), surf.get_height()
        scale = min(width / sw, height / sh)
        if scale >= 1:
            scale = max(1, int(scale))
        cr.translate((width - sw * scale) // 2, (height - sh * scale) // 2)
        cr.scale(scale, scale)
        cr.set_source_surface(surf, 0, 0)
        cr.get_source().set_filter(cairo.FILTER_NEAREST if scale >= 1 else cairo.FILTER_GOOD)
        cr.paint()
        return True

    def update_label(self):
        self.label.set_text("Frame %d of %d" % (self.index + 1, len(self.frames)))

    def show_frame(self, i):
        self.index = max(0, min(len(self.frames) - 1, i))
        self.track.set_value(self.index, emit=False)
        self.update_label()
        self.view.queue_draw()

    def on_seek(self, track, value):
        self.show_frame(value)

    def play(self):
        if self.index >= len(self.frames) - 1:
            self.index = 0
        self.stop()
        self.timer = GLib.timeout_add(60, self.tick)
        self.play_btn.set_label("_Pause")
        return False

    def stop(self):
        if self.timer:
            GLib.source_remove(self.timer)
            self.timer = None
        if hasattr(self, "play_btn"):
            self.play_btn.set_label("_Play")

    def toggle_play(self):
        if self.timer:
            self.stop()
        else:
            self.play()

    def restart(self):
        self.show_frame(0)
        self.play()

    def cycle_speed(self):
        i = self.SPEEDS.index(self.speed)
        self.speed = self.SPEEDS[(i + 1) % len(self.SPEEDS)]
        self.speed_btn.set_label("Speed: _%dx" % self.speed)

    def tick(self):
        nxt = self.index + self.speed
        if nxt >= len(self.frames) - 1:
            self.show_frame(len(self.frames) - 1)
            self.timer = None
            self.play_btn.set_label("_Play")
            return False
        self.show_frame(nxt)
        return True
