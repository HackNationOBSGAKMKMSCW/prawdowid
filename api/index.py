"""Vercel Function: the whole FastAPI backend (``backend/server.py``) under ``/api/*``.

``vercel.json`` rewrites every ``/api/...`` request here; the app still sees the original
path (``/api/check``, ``/api/admin/...``), so its routes need no changes.

Vercel functions have a read-only filesystem except ``/tmp``, and the timeout is set by
``maxDuration`` in ``vercel.json``. The defaults below adapt the backend to that; any of
them can be overridden with a project environment variable in Vercel.
"""

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
for part in ("analysis/src", "analysis", "backend"):
    path = str(ROOT / part)
    if path not in sys.path:
        sys.path.insert(0, path)

SCRATCH = Path(os.getenv("PRAWDOWID_TMP_DIR", "/tmp/prawdowid"))
_DEFAULTS = {
    # Writable locations (each instance has its own /tmp; nothing here survives the instance).
    "LOG_FILE": str(SCRATCH / "logs" / "app.jsonl"),
    "RUNTIME_CONFIG_FILE": str(SCRATCH / "runtime_config.json"),
    "ADMIN_DB_PATH": str(SCRATCH / "admin.db"),
    # Logs also go to stderr, so they show up in the Vercel dashboard.
    "LOG_CONSOLE": "true",
    # Below maxDuration (300 s in vercel.json), so the API answers 504 analysis_timeout
    # instead of Vercel cutting the function off without a response.
    "CHECK_TIMEOUT_SECONDS": "280",
}
for name, value in _DEFAULTS.items():
    os.environ.setdefault(name, value)

from server import app  # noqa: E402

__all__ = ["app"]
