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

# The Neon database was connected in Vercel Storage with the custom prefix ``TEMP``
# (``TEMP_DATABASE_URL``...), because unprefixed variables already existed in the project.
# The backend reads only ``DATABASE_URL``, so the prefixed pooled address replaces it here,
# taking precedence over any unprefixed ``DATABASE_URL``. ``DATABASE_ENV_PREFIX`` selects a
# different prefix; an empty value keeps plain ``DATABASE_URL``.
DATABASE_ENV_PREFIX = os.getenv("DATABASE_ENV_PREFIX", "TEMP").strip().rstrip("_")
# Neon sets DATABASE_URL (pooler); older integrations name the same address POSTGRES_URL.
_POOLED_URL_NAMES = ("DATABASE_URL", "POSTGRES_URL")


def _prefixed_database_url(prefix: str) -> tuple[str, str] | None:
    """(variable name, address) of the prefixed pooled database address, if set."""
    if not prefix:
        return None
    for name in _POOLED_URL_NAMES:
        value = os.getenv(f"{prefix}_{name}", "").strip()
        if value:
            return f"{prefix}_{name}", value
    return None


def _describe(url: str) -> str:
    """Host and database name of ``url`` for the logs: never the user or the password."""
    from urllib.parse import parse_qs, urlsplit

    try:
        parts = urlsplit(url)
        if parts.scheme not in ("postgresql", "postgres"):
            # Nothing from the value: without the scheme the password can land in any part.
            return "ZŁY adres: nie zaczyna się od postgresql:// (cudzysłowy, spacja, inna zmienna?)"
        netloc_host = parts.netloc.rpartition("@")[2]  # libpq: host1:port,host2 after the @
        query_hosts = parse_qs(parts.query).get("host", [])
        database = parts.path.lstrip("/")
    except ValueError:
        return "ZŁY adres: nie do odczytania"
    hosts = [h.rsplit(":", 1)[0] if h.count(":") == 1 else h for h in netloc_host.split(",")]
    hosts += [h for value in query_hosts for h in value.split(",")]
    hosts = [h for h in hosts if h] or [""]
    shown = ",".join(hosts) or "-"
    if any(not label for host in hosts for label in host.split(".")):
        return f"host={shown}, baza={database or '-'}; ZŁY host: pusty albo z pustym członem (np. zaczyna się od kropki)"
    return f"host={shown}, baza={database or '-'}"


def _log(message: str) -> None:
    print(f"[vercel] {message}", file=sys.stderr, flush=True)


_found = _prefixed_database_url(DATABASE_ENV_PREFIX)
if _found is not None:
    os.environ["DATABASE_URL"] = _found[1]
    _log(f"DATABASE_URL z {_found[0]} ({_describe(_found[1])})")
elif DATABASE_ENV_PREFIX:
    _log(f"brak {DATABASE_ENV_PREFIX}_DATABASE_URL: zostaje DATABASE_URL")
if os.getenv("DATABASE_URL", "").strip():
    if _found is None:
        _log(f"DATABASE_URL ({_describe(os.environ['DATABASE_URL'])})")
else:
    # Lokalnie adres może jeszcze przyjść z .env (server.py czyta go później); na Vercelu nie.
    _log("brak DATABASE_URL w zmiennych środowiska: na Vercelu backend nie połączy się z bazą")

from server import app  # noqa: E402

__all__ = ["app"]
