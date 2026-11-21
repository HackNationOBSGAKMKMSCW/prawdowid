"""Logging setup: JSON Lines file (+ stderr), secret masking, idempotent ``init()``."""

from __future__ import annotations

import contextlib
import json
import logging
import os
import re
import sys
from datetime import UTC, datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

from .context import current_request_id, stage_stack

DEFAULT_LOG_FILE = Path(__file__).resolve().parents[1] / "logs" / "app.jsonl"
MAX_STRING = 2000
NOISY_LOGGERS = ("httpx", "httpx2", "httpcore", "httpcore2", "openai", "urllib3", "asyncio")

_SECRET_KEY = re.compile(r"(api[_-]?key|secret|password|passwd|token|authorization|cookie)", re.I)
_SECRET_TEXT = (
    (
        re.compile(r"(?i)\b(api[_-]?key|key|token|access_token|password|secret)=([^&\s\"']+)"),
        r"\1=***",
    ),
    (re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._\-]+"), "Bearer ***"),
    (re.compile(r"\bsk-[A-Za-z0-9_\-]{10,}"), "sk-***"),
    (re.compile(r"\bAIza[0-9A-Za-z_\-]{20,}"), "AIza***"),
)
_RESERVED = ("ts", "level", "logger", "event", "message", "request_id", "stage", "exc")


def mask_text(text: str) -> str:
    for pattern, replacement in _SECRET_TEXT:
        text = pattern.sub(replacement, text)
    return text if len(text) <= MAX_STRING else text[:MAX_STRING] + "…"


def mask(value: Any, key: str | None = None) -> Any:
    """Recursively mask secrets (by key name and by value shape) and truncate long strings."""
    if (
        key is not None
        and _SECRET_KEY.search(key)
        and value not in (None, "")
        and not isinstance(value, int | float | bool)
    ):
        return "***"
    if isinstance(value, str):
        return mask_text(value)
    if isinstance(value, dict):
        return {str(k): mask(v, str(k)) for k, v in value.items()}
    if isinstance(value, list | tuple | set):
        return [mask(v) for v in value]
    return value


def _event_fields(record: logging.LogRecord) -> dict[str, Any]:
    fields = getattr(record, "obs_fields", None)
    return mask(fields) if isinstance(fields, dict) else {}


class JsonFormatter(logging.Formatter):
    """One JSON object per line; domain-event fields are flattened to top level."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname.lower(),
            "logger": record.name,
        }
        event = getattr(record, "obs_event", None)
        if event:
            payload["event"] = event
        else:
            payload["event"] = "log"
            payload["message"] = mask_text(record.getMessage())
        request_id = current_request_id()
        if request_id:
            payload["request_id"] = request_id
        stack = stage_stack()
        if stack:
            payload["stage"] = stack[-1]
        for key, value in _event_fields(record).items():
            payload[f"field_{key}" if key in _RESERVED else key] = value
        if record.exc_info:
            payload["exc"] = mask_text(self.formatException(record.exc_info))
        return json.dumps(payload, ensure_ascii=False, default=str)


class ConsoleFormatter(logging.Formatter):
    """Compact single-line form for stderr: ``WARNING prompt_injection kind=... pattern=...``."""

    def format(self, record: logging.LogRecord) -> str:
        event = getattr(record, "obs_event", None)
        head = f"[obs] {record.levelname} {event or record.name}"
        if event:
            pairs = " ".join(
                f"{k}={v}" for k, v in _event_fields(record).items() if v not in (None, "", [], {})
            )
            text = f"{head} {pairs}".strip()
        else:
            text = f"{head}: {mask_text(record.getMessage())}"
        request_id = current_request_id()
        if request_id:
            text += f" rid={request_id}"
        return text[:600]


def _env_flag(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


class _State:
    initialized = False
    handlers: list[logging.Handler] = []
    previous_root_level: int | None = None


def is_initialized() -> bool:
    return _State.initialized


def init(
    *,
    log_file: str | Path | None = None,
    level: str | None = None,
    console: bool | None = None,
    instrument: bool = True,
) -> bool:
    """Configure logging and apply auto-instrumentation. Safe to call many times.

    Env: LOG_ENABLED (default true), LOG_LEVEL (INFO), LOG_FILE (backend/logs/app.jsonl),
    LOG_CONSOLE (false: only WARNING+ to stderr; true: everything to stderr).
    Returns False when disabled.
    """
    if _State.initialized:
        return True
    if not _env_flag("LOG_ENABLED", True):
        return False

    level_name = (level or os.getenv("LOG_LEVEL") or "INFO").upper()
    numeric_level = logging.getLevelName(level_name)
    if not isinstance(numeric_level, int):
        numeric_level = logging.INFO

    path = Path(log_file or os.getenv("LOG_FILE") or DEFAULT_LOG_FILE)
    path.parent.mkdir(parents=True, exist_ok=True)
    ignore_file = path.parent / ".gitignore"  # keep logs out of git without editing shared files
    if not ignore_file.exists():
        with contextlib.suppress(OSError):
            ignore_file.write_text("*\n", encoding="utf-8")
    file_handler = RotatingFileHandler(
        path, maxBytes=5 * 1024 * 1024, backupCount=5, encoding="utf-8", delay=True
    )
    file_handler.setLevel(numeric_level)
    file_handler.setFormatter(JsonFormatter())

    verbose_console = console if console is not None else _env_flag("LOG_CONSOLE", False)
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setLevel(numeric_level if verbose_console else logging.WARNING)
    console_handler.setFormatter(ConsoleFormatter())

    root = logging.getLogger()
    _State.previous_root_level = root.level
    if root.level == logging.NOTSET or root.level > numeric_level:
        root.setLevel(numeric_level)
    for handler in (file_handler, console_handler):
        root.addHandler(handler)
    _State.handlers = [file_handler, console_handler]
    logging.getLogger("observability").setLevel(numeric_level)
    for name in NOISY_LOGGERS:  # httpx INFO lines contain full URLs (API keys in query)
        logging.getLogger(name).setLevel(max(logging.WARNING, numeric_level))

    _State.initialized = True
    if instrument:
        from .instrument import apply_all

        apply_all()
    return True


def shutdown() -> None:
    """Remove handlers and patches (used by tests and hot reload)."""
    from .instrument import revert_all

    revert_all()
    root = logging.getLogger()
    for handler in _State.handlers:
        root.removeHandler(handler)
        handler.close()
    if _State.previous_root_level is not None:
        root.setLevel(_State.previous_root_level)
    _State.handlers = []
    _State.previous_root_level = None
    _State.initialized = False
