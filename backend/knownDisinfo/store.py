"""Where documented disinformation cases come from.

Today: the EUvsDisinfo MCP server (``McpDisinfoStore``). Later: a PostgreSQL table with the
same cases. Matching only uses the ``DisinfoStore`` protocol, so switching means writing

    class PostgresDisinfoStore:
        async def search(self, query: str, limit: int) -> list[DisinfoCase]: ...

and passing it to ``knownDisinfo.run(analysis, store=...)``.
"""

from __future__ import annotations

import html
import re
from typing import Any, Protocol

from .mcp import EUvsDisinfoMcp, McpError
from .models import DisinfoCase

_BLOCK_END = re.compile(r"</(p|div|li|h[1-6])>|<br\s*/?>", re.IGNORECASE)
_TAG = re.compile(r"<[^>]+>")
_RESPONSE = re.compile(r"<h[1-6][^>]*>\s*RESPONSE\s*</h[1-6]>", re.IGNORECASE)
_SUMMARY = re.compile(r"<h[1-6][^>]*>\s*SUMMARY\s*</h[1-6]>", re.IGNORECASE)


class DisinfoStore(Protocol):
    async def search(self, query: str, limit: int) -> list[DisinfoCase]: ...


def html_text(markup: str) -> str:
    text = html.unescape(_TAG.sub(" ", _BLOCK_END.sub("\n", markup or "")))
    lines = (" ".join(line.split()) for line in text.splitlines())
    return "\n".join(line for line in lines if line)


def to_case(item: dict[str, Any]) -> DisinfoCase | None:
    """One ``search`` result -> case; ``None`` for analytical articles and broken rows."""
    link = str(item.get("link") or "").strip()
    if item.get("type") != "claim_review" or not link:
        return None
    content = _SUMMARY.sub("", str(item.get("content") or ""))
    parts = _RESPONSE.split(content, maxsplit=1)
    summary, response = parts[0], (parts[1] if len(parts) > 1 else "")
    return DisinfoCase(
        case_id=link,
        title=html_text(str(item.get("title") or "")) or link,
        summary=html_text(summary),
        disproof=html_text(response),
        url=link,
    )


class McpDisinfoStore:
    """Full-text ``search`` tool of the EUvsDisinfo MCP; keeps only ``claim_review`` cases."""

    def __init__(self, mcp: EUvsDisinfoMcp):
        self.mcp = mcp

    async def search(self, query: str, limit: int) -> list[DisinfoCase]:
        query = " ".join(query.split())
        if len(query) < 3:  # the tool rejects shorter queries
            return []
        data = await self.mcp.call_tool("search", {"query": query})
        results = data.get("results") if isinstance(data, dict) else None
        if not isinstance(results, list):
            raise McpError("bad_response", "wynik search bez listy results")
        cases = [case for item in results if isinstance(item, dict) if (case := to_case(item))]
        return cases[:limit]
