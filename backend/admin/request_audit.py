"""Middleware ASGI: próby SQL injection w żądaniach trafiają do powiadomień admina.

Na ścieżce żądania middleware tylko buforuje treść (do ``max_body`` bajtów, domyślnie limit
API strony) i wrzuca zadanie do ``BackgroundWorker``; żądanie idzie dalej od razu. Skan
(``sqli.scan_request``) i zapis alertu (``Monitor.register_sql_injection``) wykonuje wątek
roboczy, więc nie blokują pętli zdarzeń, a zalew prób jest ograniczony rozmiarem kolejki.

Odpowiedź nie zmienia się nigdy. Źródło to pseudonim (HMAC) adresu klienta: pierwszy adres
z ``X-Forwarded-For`` (aplikacja stoi za proxy, np. Vercel), a bez nagłówka — adres połączenia.
"""

from __future__ import annotations

import contextlib
import logging
from collections.abc import Callable
from typing import Any

from .background import BackgroundWorker
from .sqli import Detection, scan_request

logger = logging.getLogger(__name__)

MAX_BODY = 96 * 1024
_BODY_METHODS = {"POST", "PUT", "PATCH"}

# (detection, method, path, client_ip, request_id) -> None; wołane w wątku roboczym
Reporter = Callable[[Detection, str, str, str | None, str | None], None]


def monitor_reporter(get_monitor: Callable[[], Any], channel: str) -> Reporter:
    """Zgłaszanie do monitora panelu; ``get_monitor`` wołany leniwie przy pierwszym wykryciu."""

    def report(
        detection: Detection,
        method: str,
        path: str,
        client_ip: str | None,
        request_id: str | None,
    ) -> None:
        from .settings import user_label

        monitor = get_monitor()
        source = monitor.settings.user_key(f"ip:{client_ip}") if client_ip else None
        monitor.register_sql_injection(
            channel=channel,
            source=source,
            source_label=user_label(f"ip:{client_ip}") if client_ip else None,
            patterns=detection.patterns,
            locations=detection.locations,
            method=method,
            path=path,
            request_id=request_id,
        )

    return report


def client_address(scope: dict[str, Any], headers: dict[bytes, bytes]) -> str | None:
    forwarded = headers.get(b"x-forwarded-for", b"").decode("latin-1").split(",")[0].strip()
    if forwarded:
        return forwarded[:64]
    real_ip = headers.get(b"x-real-ip", b"").decode("latin-1").strip()
    if real_ip:
        return real_ip[:64]
    client = scope.get("client")
    return client[0] if client else None


def _current_request_id() -> str | None:
    with contextlib.suppress(Exception):
        from observability import current_request_id

        return current_request_id()
    return None


class SqlInjectionAuditMiddleware:
    def __init__(
        self,
        app: Any,
        *,
        reporter: Reporter | None,
        worker: BackgroundWorker | None = None,
        max_body: int = MAX_BODY,
    ) -> None:
        self.app = app
        self.reporter = reporter
        self.worker = worker or BackgroundWorker("sql-injection-audit")
        self.max_body = max_body

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope.get("type") != "http" or self.reporter is None:
            await self.app(scope, receive, send)
            return
        method = scope.get("method", "GET")
        headers = {name.lower(): value for name, value in scope.get("headers", [])}
        body = b""
        replay: list[dict[str, Any]] = []
        length = _int(headers.get(b"content-length"))
        if method in _BODY_METHODS and (length is None or length <= self.max_body):
            chunks: list[bytes] = []
            size = 0
            while True:
                message = await receive()
                replay.append(message)
                if message.get("type") != "http.request":
                    break
                chunk = message.get("body", b"")
                size += len(chunk)
                if size > self.max_body:  # za duże: nie skanujemy, resztę czyta aplikacja
                    chunks = []
                    break
                chunks.append(chunk)
                if not message.get("more_body", False):
                    break
            body = b"".join(chunks)

        self.worker.submit(
            self._scan_and_report,
            method,
            scope.get("path", ""),
            scope.get("query_string", b""),
            body,
            headers.get(b"content-type", b"").decode("latin-1").lower(),
            client_address(scope, headers),
            _current_request_id(),
        )

        if not replay:
            await self.app(scope, receive, send)
            return

        async def replay_receive() -> dict[str, Any]:
            if replay:
                return replay.pop(0)
            return await receive()

        await self.app(scope, replay_receive, send)

    def _scan_and_report(
        self,
        method: str,
        path: str,
        query_string: bytes,
        body: bytes,
        content_type: str,
        client_ip: str | None,
        request_id: str | None,
    ) -> None:
        """W wątku roboczym: skan, a przy wykryciu log i zgłoszenie (błędy połyka worker)."""
        detection = scan_request(path, query_string, body, content_type)
        if not detection.detected:
            return
        logger.warning(
            "sql_injection_detected method=%s path=%s patterns=%s",
            method,
            path[:200],
            ",".join(detection.patterns),
        )
        assert self.reporter is not None
        self.reporter(detection, method, path, client_ip, request_id)


def _int(value: bytes | None) -> int | None:
    try:
        return int(value) if value is not None else None
    except ValueError:
        return None
