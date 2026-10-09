"""Paint98 test suite (stdlib unittest).

Run from the project root:  python3 -m unittest -v
Window tests need a display; without one they are skipped. On a headless
machine run them under Xvfb:  xvfb-run -a python3 -m unittest -v

Importing this package points the user config and data directories at a
throw-away folder before GLib reads them, so tests never touch your real
settings, recovery copies or stickers.
"""

import atexit
import os
import shutil
import tempfile

_HOME = tempfile.mkdtemp(prefix="paint98-tests-")
atexit.register(shutil.rmtree, _HOME, ignore_errors=True)
for _var, _sub in (("XDG_CONFIG_HOME", "config"), ("XDG_DATA_HOME", "data"),
                   ("XDG_CACHE_HOME", "cache"), ("XDG_STATE_HOME", "state")):
    os.environ[_var] = os.path.join(_HOME, _sub)
    os.makedirs(os.environ[_var], exist_ok=True)
os.environ.pop("SNAP_USER_COMMON", None)
os.environ["GSETTINGS_BACKEND"] = "memory"
os.environ.setdefault("NO_AT_BRIDGE", "1")

TEST_HOME = _HOME
