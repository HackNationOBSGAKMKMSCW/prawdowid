"""Minimal client for the EUvsDisinfo MCP server (Streamable HTTP, stateless mode).

Every call is one JSON-RPC POST with a client-generated ``mcp-session-id`` (the server's
documented stateless mode), so there is no initialize handshake or session to keep.
The key goes in the ``X-API-Key`` header, never in the URL, and never into errors or logs.
"""

from __future__ import annotations

import contextlib
import itertools
import json
import uuid
from typing import Any

import httpx

from .settings import DisinfoSettings

_ACCEPT = "application/json, text/event-stream"
_ids = itertools.count(1)


class McpError(RuntimeError):
    def __init__(self, code: int | str, message: str):
        self.code = code
        super().__init__(f"EUvsDisinfo MCP {code}: {message[:300]}")


def _sse_messages(body: str) -> list[Any]:
    """JSON payloads of the ``data:`` fields of an SSE body."""
    messages, data = [], []
    for line in [*body.splitlines(), ""]:
        if line.startswith("data:"):
            data.append(line[5:].removeprefix(" "))
        elif not line.strip() and data:
            with contextlib.suppress(json.JSONDecodeError):
                messages.append(json.loads("\n".join(data)))
            data = []
    return messages


def _rpc_payload(response: httpx.Response, request_id: int) -> dict[str, Any]:
    if "text/event-stream" in response.headers.get("content-type", ""):
        messages = [m for m in _sse_messages(response.text) if isinstance(m, dict)]
        replies = [m for m in messages if m.get("id") == request_id] or messages
        if not replies:
            raise McpError("bad_response", "pusta odpowiedź SSE")
        return replies[-1]
    try:
        payload = response.json()
    except ValueError:
        raise McpError("bad_response", "odpowiedź nie jest JSON-em") from None
    if not isinstance(payload, dict):
        raise McpError("bad_response", "odpowiedź nie jest obiektem JSON-RPC")
    return payload


def _error_message(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        return response.reason_phrase or "błąd HTTP"
    error = payload.get("error") if isinstance(payload, dict) else None
    if isinstance(error, dict):
        return str(error.get("message") or error.get("code") or "błąd")
    return response.reason_phrase or "błąd HTTP"


def _tool_text(result: dict[str, Any]) -> str:
    parts = result.get("content") or []
    return "\n".join(str(part.get("text", "")) for part in parts if isinstance(part, dict)).strip()


class EUvsDisinfoMcp:
    def __init__(self, settings: DisinfoSettings, *, client: httpx.AsyncClient | None = None):
        self.settings = settings
        self._client = client or httpx.AsyncClient(timeout=settings.timeout)
        self._owns_client = client is None

    def __repr__(self) -> str:
        return f"EUvsDisinfoMcp(url={self.settings.mcp_url!r})"

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def __aenter__(self) -> EUvsDisinfoMcp:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.aclose()

    async def _rpc(self, method: str, params: dict[str, Any] | None = None) -> Any:
        if not self.settings.api_key:
            raise McpError(401, "brak klucza EUvsDisinfo_API_KEY")
        request_id = next(_ids)
        headers = {
            "X-API-Key": self.settings.api_key,
            "Accept": _ACCEPT,
            "Content-Type": "application/json",
            "mcp-session-id": str(uuid.uuid4()),
        }
        body = {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params or {}}
        try:
            response = await self._client.post(
                self.settings.mcp_url, json=body, headers=headers, timeout=self.settings.timeout
            )
        except httpx.TimeoutException:
            raise McpError("timeout", f"brak odpowiedzi w {self.settings.timeout:g} s") from None
        except httpx.HTTPError as exc:
            raise McpError("network", type(exc).__name__) from None
        if response.status_code >= 400:
            raise McpError(response.status_code, _error_message(response))
        payload = _rpc_payload(response, request_id)
        error = payload.get("error")
        if error:
            message = error.get("message", "") if isinstance(error, dict) else str(error)
            code = error.get("code", "rpc") if isinstance(error, dict) else "rpc"
            raise McpError(code, str(message))
        return payload.get("result")

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        """Tool result: ``structuredContent`` when present, else the text (parsed if JSON)."""
        result = await self._rpc("tools/call", {"name": name, "arguments": arguments})
        if not isinstance(result, dict):
            raise McpError("bad_response", "wynik narzędzia nie jest obiektem")
        if result.get("isError"):
            raise McpError("tool_error", _tool_text(result) or name)
        if result.get("structuredContent") is not None:
            return result["structuredContent"]
        text = _tool_text(result)
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return text

    async def list_tools(self) -> list[dict[str, Any]]:
        result = await self._rpc("tools/list")
        return list((result or {}).get("tools") or [])

    async def health(self) -> dict[str, Any]:
        url = self.settings.mcp_url.rsplit("/", 1)[0] + "/health"
        try:
            response = await self._client.get(url, timeout=self.settings.timeout)
            return response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise McpError("health", type(exc).__name__) from None
