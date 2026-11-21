"""Domain events: one JSON line per event, never raising into application code."""

from __future__ import annotations

import contextlib
import hashlib
import logging
from typing import Any

from .context import current

EVENTS_LOGGER = "observability.events"
_logger = logging.getLogger(EVENTS_LOGGER)

_LEVELS = {
    "debug": logging.DEBUG,
    "info": logging.INFO,
    "warning": logging.WARNING,
    "error": logging.ERROR,
}


def log_event(event: str, level: str = "info", **fields: Any) -> None:
    """Emit a structured event. Fields become top-level keys in the JSON line."""
    with contextlib.suppress(Exception):
        _logger.log(
            _LEVELS.get(level, logging.INFO),
            event,
            extra={"obs_event": event, "obs_fields": fields},
        )


def text_fingerprint(text: str) -> dict[str, Any]:
    """Privacy-safe description of a text: hash + length, never the content."""
    return {
        "text_sha256": hashlib.sha256(text.encode("utf-8", "replace")).hexdigest()[:16],
        "text_length": len(text),
    }


def log_abstain(reason: str, **fields: Any) -> None:
    """Record that the system withheld a verdict (call from the place that decides it)."""
    metrics = current()
    if metrics is not None:
        metrics.abstain(reason)
    log_event("abstain", level="warning", reason=reason, **fields)


def log_prompt_injection(
    *,
    text: str,
    pattern: str,
    source: str,
    kind: str = "input_pattern",
    snippet: str | None = None,
    **fields: Any,
) -> None:
    """Record a prompt-injection attempt once per (request, text, kind)."""
    fingerprint = text_fingerprint(text)
    metrics = current()
    if metrics is not None:
        if not metrics.mark_reported(f"{kind}:{fingerprint['text_sha256']}"):
            return
        metrics.add(injection_attempts=1)
    log_event(
        "prompt_injection",
        level="warning",
        kind=kind,
        pattern=pattern,
        source=source,
        snippet=(snippet or "")[:80] or None,
        **fingerprint,
        **fields,
    )
