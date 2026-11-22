"""ASGI request-target and body limits for public API endpoints."""

from __future__ import annotations

import json
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
