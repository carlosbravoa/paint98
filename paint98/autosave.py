"""Autosave and crash recovery.

Every open window writes a recovery copy of its picture (PNG + a small JSON
file) shortly after unsaved changes, and deletes it once the work is saved
or deliberately discarded. Each window also holds an exclusive lock on its
own lock file while it runs; the operating system releases that lock if the
process dies, so at start-up any recovery copy whose lock can be taken
belongs to a session that ended without cleaning up (a crash).
"""

import fcntl
import itertools
import json
import os
import threading
import time

from gi.repository import GLib

INTERVAL_S = 30
_counter = itertools.count(1)


def recovery_dir():
    base = os.environ.get("SNAP_USER_COMMON") or os.path.join(GLib.get_user_data_dir(), "paint98")
    path = os.path.join(base, "recovery")
    os.makedirs(path, exist_ok=True)
    return path


def _paths(session_id):
    d = recovery_dir()
    return (os.path.join(d, session_id + ".png"), os.path.join(d, session_id + ".json"),
            os.path.join(d, session_id + ".lock"))


def _remove(*paths):
    for p in paths:
        try:
            os.remove(p)
        except OSError:
            pass


class AutoSaver:
    """Keeps a recovery copy of one window's picture."""

    def __init__(self, canvas, doc):
        self.canvas = canvas
        self.doc = doc
        self.id = "session-%d-%d" % (os.getpid(), next(_counter))
        self.png, self.meta, lock = _paths(self.id)
        self.lock = open(lock, "w")
        fcntl.flock(self.lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        self.dirty = False
        self.writing = False
        doc.connect("changed", self._note)
        canvas.connect("picture-changed", self._note)
        self.timer = GLib.timeout_add_seconds(INTERVAL_S, self._tick)

    def _note(self, *a):
        self.dirty = True

    def _tick(self):
        if self.dirty and (self.doc.modified or self.canvas.has_pending_work()):
            self.save_now()
        return True

    def save_now(self):
        """Write the recovery copy in a background thread."""
        if self.writing:
            return
        self.dirty = False
        surf = self.canvas.composite_picture()  # a private copy
        meta = {
            "filename": self.doc.filename,
            "time": time.time(),
            "width": surf.get_width(),
            "height": surf.get_height(),
        }
        self.writing = True

        def work():
            try:
                tmp = self.png + ".tmp"
                surf.write_to_png(tmp)
                os.replace(tmp, self.png)
                tmp = self.meta + ".tmp"
                with open(tmp, "w") as f:
                    json.dump(meta, f)
                os.replace(tmp, self.meta)
            except OSError:
                pass
            finally:
                self.writing = False

        threading.Thread(target=work, daemon=True).start()

    def clear(self):
        """The work is saved or discarded: no recovery copy is needed."""
        self.dirty = False
        _remove(self.meta, self.png)

    def close(self):
        if self.timer:
            GLib.source_remove(self.timer)
            self.timer = None
        self.clear()
        lock_path = self.lock.name
        self.lock.close()
        _remove(lock_path)


def find_orphans():
    """Recovery copies left behind by sessions that are no longer running.
    Returns a list of (session_id, metadata, png_path), newest first."""
    found = []
    d = recovery_dir()
    for name in os.listdir(d):
        if not name.endswith(".json"):
            continue
        sid = name[:-5]
        png, meta, lock = _paths(sid)
        try:
            with open(lock, "a") as f:
                fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
                fcntl.flock(f, fcntl.LOCK_UN)
        except BlockingIOError:
            continue  # that window is still open
        except OSError:
            pass
        try:
            with open(meta) as f:
                info = json.load(f)
            if not isinstance(info, dict) or not os.path.exists(png):
                raise ValueError
        except (OSError, ValueError):
            discard(sid)
            continue
        found.append((sid, info, png))
    found.sort(key=lambda e: e[1].get("time", 0) if isinstance(e[1].get("time"), (int, float)) else 0,
               reverse=True)
    return found


def discard(session_id):
    _remove(*_paths(session_id))
