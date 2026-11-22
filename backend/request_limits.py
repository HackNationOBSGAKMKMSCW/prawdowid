"""Limits of the public API: request size, checks per client (rate) and parallel checks."""

from __future__ import annotations

import asyncio
import json
import os
import re
import threading
import time
from collections import deque
from collections.abc import Callable, Sequence
from typing import Any

_BODY_LIMIT_RESPONSE = json.dumps(
    {
        "error": {
            "code": "request_too_large",
            "message": "The request input exceeds the allowed size.",
        }
    },
    separators=(",", ":"),
).encode("utf-8")


class RequestSizeLimitMiddleware:
    def __init__(self, app: Any, *, max_body_bytes: int = 96 * 1024):
        if max_body_bytes < 1:
            raise ValueError("max_body_bytes must be positive")
        self.app = app
        self.max_body_bytes = max_body_bytes

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if (
            scope.get("type") == "http"
            and scope.get("method") == "GET"
            and scope.get("path") == "/api/check"
        ):
            if len(scope.get("query_string", b"")) > self.max_body_bytes:
                await self._reject(send)
                return
            await self.app(scope, receive, send)
            return

        if not self._is_limited_request(scope):
            await self.app(scope, receive, send)
            return

        content_length = self._content_length(scope)
        if content_length is not None and content_length > self.max_body_bytes:
            await self._reject(send)
            return

        messages: list[dict[str, Any]] = []
        body_size = 0
        while True:
            message = await receive()
            messages.append(message)
            if message.get("type") == "http.disconnect":
                break
            if message.get("type") == "http.request":
                body_size += len(message.get("body", b""))
                if body_size > self.max_body_bytes:
                    await self._reject(send)
                    return
                if not message.get("more_body", False):
                    break

        async def replay_receive() -> dict[str, Any]:
            if messages:
                return messages.pop(0)
            return await receive()

        await self.app(scope, replay_receive, send)

    @staticmethod
    def _is_limited_request(scope: dict[str, Any]) -> bool:
        if scope.get("type") != "http" or scope.get("method") != "POST":
            return False
        path = scope.get("path", "")
        return path == "/api/check" or (
            path.startswith("/api/check/") and path.endswith("/report")
        )

    @staticmethod
    def _content_length(scope: dict[str, Any]) -> int | None:
        for name, value in scope.get("headers", []):
            if name.lower() == b"content-length":
                try:
                    return int(value)
                except ValueError:
                    return None
        return None

    @staticmethod
    async def _reject(send: Any) -> None:
        await send(
            {
                "type": "http.response.start",
                "status": 413,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(_BODY_LIMIT_RESPONSE)).encode("ascii")),
                    (b"cache-control", b"no-store"),
                    (b"referrer-policy", b"no-referrer"),
                ],
            }
        )
        await send({"type": "http.response.body", "body": _BODY_LIMIT_RESPONSE})


# --------------------------------------------------------------------------- check limits

RATE_LIMIT_ENV = "CHECK_RATE_LIMIT"
DEFAULT_RATE_LIMIT = "6/minute,60/hour"
_UNITS = {"second": 1.0, "minute": 60.0, "hour": 3600.0, "day": 86400.0}
_LIMIT = re.compile(r"^\s*(\d+)\s*/\s*(second|minute|hour|day)s?\s*$")


def parse_rate_limits(spec: str | None) -> list[tuple[int, float]]:
    """``"6/minute,60/hour"`` -> ``[(6, 60.0), (60, 3600.0)]``; ``""``/``off`` -> no limit."""
    spec = (spec or "").strip().lower()
    if spec in {"", "0", "off", "none", "false"}:
        return []
    limits = []
    for part in spec.split(","):
        match = _LIMIT.match(part)
        if not match or int(match.group(1)) < 1:
            raise ValueError(f"{RATE_LIMIT_ENV}: invalid limit {part!r} (e.g. 6/minute,60/hour)")
        limits.append((int(match.group(1)), _UNITS[match.group(2)]))
    return limits


class RateLimiter:
    """Sliding-window limits per key (e.g. client IP), kept in memory of one process.

    ``hit(key)`` records a request and returns ``None``, or returns the number of seconds
    to wait without recording it. With several server processes every process counts on
    its own, so the effective limit is the configured one times the number of processes.
    """

    def __init__(
        self,
        limits: Sequence[tuple[int, float]],
        *,
        clock: Callable[[], float] = time.monotonic,
        max_keys: int = 50_000,
    ) -> None:
        if not limits:
            raise ValueError("at least one limit is required")
        self.limits = sorted(limits, key=lambda limit: limit[1])
        self._longest = self.limits[-1][1]
        self._clock = clock
        self._max_keys = max_keys
        self._hits: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    @classmethod
    def from_environment(cls) -> RateLimiter | None:
        limits = parse_rate_limits(os.getenv(RATE_LIMIT_ENV, DEFAULT_RATE_LIMIT))
        return cls(limits) if limits else None

    def hit(self, key: str) -> float | None:
        now = self._clock()
        with self._lock:
            hits = self._hits.get(key)
            if hits is None:
                if len(self._hits) >= self._max_keys:
                    self._prune(now)
                hits = self._hits[key] = deque()
            while hits and now - hits[0] >= self._longest:
                hits.popleft()
            wait = 0.0
            for count, window in self.limits:
                if len(hits) >= count and now - hits[-count] < window:
                    wait = max(wait, window - (now - hits[-count]))
            if wait > 0:
                return wait
            hits.append(now)
            return None

    def _prune(self, now: float) -> None:
        for key in [k for k, hits in self._hits.items() if not hits or now - hits[-1] >= self._longest]:
            del self._hits[key]
        while len(self._hits) >= self._max_keys:  # still full: drop the oldest keys
            del self._hits[next(iter(self._hits))]


class CheckGate:
    """Admission of one check: rate limit per client and the shared concurrency limit.

    The website (``GET /api/check``) and WhatsApp (``/api/whatsapp/webhook``) use the same
    gate, so one client cannot bypass the limits by switching channels.
    """

    def __init__(self, semaphore: asyncio.Semaphore, limiter: RateLimiter | None = None) -> None:
        self.semaphore = semaphore
        self.limiter = limiter

    def retry_after(self, key: str) -> int | None:
        """Seconds to wait when ``key`` is over its limit (the request is not counted)."""
        if self.limiter is None:
            return None
        wait = self.limiter.hit(key)
        return None if wait is None else max(1, int(wait + 0.999))

    def busy(self) -> bool:
        return self.semaphore.locked()

    async def try_acquire(self) -> bool:
        """Take a check slot without waiting; ``False`` when all slots are in use.

        ``acquire`` of a free semaphore returns at once, so nothing can take the slot
        between the check and the acquisition.
        """
        if self.semaphore.locked():
            return False
        await self.semaphore.acquire()
        return True

    def release(self) -> None:
        self.semaphore.release()


def client_ip(request: object) -> str:
    """Client address as uvicorn sees it (behind a proxy: run with ``--proxy-headers``)."""
    client = getattr(request, "client", None)
    return getattr(client, "host", None) or "unknown"
