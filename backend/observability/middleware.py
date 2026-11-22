"""Pure ASGI middleware (FastAPI/Starlette compatible, no framework import needed).

    app.add_middleware(ObservabilityMiddleware)

Each HTTP request gets a ``request_id`` (honours an incoming ``X-Request-ID``), all LLM /
search / injection events inside it are tagged with that id, and one ``request_summary``
line is written when the response finishes. The id is returned as ``X-Request-ID``.
"""

from __future__ import annotations

import re
from typing import Any

from .context import new_request_id, request_scope
from .events import log_event

_SAFE_ID = re.compile(r"^[A-Za-z0-9._-]{1,64}$")


class ObservabilityMiddleware:
    def __init__(
        self, app: Any, *, skip_paths: tuple[str, ...] = ("/health", "/docs", "/openapi.json")
    ) -> None:
        self.app = app
        self.skip_paths = skip_paths

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope.get("type") != "http" or scope.get("path", "").startswith(self.skip_paths):
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get("headers") or [])
        incoming = headers.get(b"x-request-id", b"").decode("latin-1")
        request_id = incoming if _SAFE_ID.match(incoming) else new_request_id()
        name = f"{scope.get('method', 'GET')} {scope.get('route_path') or scope.get('path', '')}"
        status_holder: dict[str, int] = {}

        async def send_wrapper(message: dict[str, Any]) -> None:
            if message.get("type") == "http.response.start":
                status_holder["status"] = message.get("status", 0)
                message.setdefault("headers", [])
                message["headers"] = [
                    *message["headers"],
                    (b"x-request-id", request_id.encode("latin-1")),
                ]
            await send(message)

        with request_scope(name, request_id=request_id):
            try:
                await self.app(scope, receive, send_wrapper)
            finally:
                status = status_holder.get("status")
                log_event(
                    "http_request",
                    level="warning" if status is None or status >= 500 else "info",
                    method=scope.get("method"),
                    path=scope.get("path"),
                    status_code=status,
                )
