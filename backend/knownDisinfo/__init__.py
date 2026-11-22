"""Known disinformation: is a claim a documented EUvsDisinfo case?

    check = await knownDisinfo.run(analysis)       # textAnalysis result (uses .statements)
    for hit in check.matches:
        hit.index, hit.statement, hit.match.url    # verified pro-Kremlin disinformation

Never raises: a missing key gives ``status="disabled"``, an unreachable database
``status="error"`` (with ``warnings``).
"""

from __future__ import annotations

import contextlib
import time
from typing import Any

import observability

from .matching import JsonLLM, OpenAIJsonLLM, check
from .mcp import EUvsDisinfoMcp, McpError
from .models import CandidateRef, DisinfoCase, DisinfoCheck, StatementCheck
from .settings import DisinfoSettings
from .store import DisinfoStore, McpDisinfoStore


async def run(
    analysis: Any,
    *,
    store: DisinfoStore | None = None,
    llm: JsonLLM | None = None,
    settings: DisinfoSettings | None = None,
) -> DisinfoCheck:
    settings = settings or DisinfoSettings.from_environment()
    statements = [str(s) for s in getattr(analysis, "statements", None) or []]
    if store is None and not settings.configured:
        return DisinfoCheck(
            status="disabled", warnings=["Brak EUvsDisinfo_API_KEY: baza nie była sprawdzana."]
        )
    started = time.perf_counter()
    owned: list[Any] = []
    try:
        with observability.stage("known_disinfo"):
            if llm is None:
                llm = OpenAIJsonLLM.from_environment()
                owned.append(llm)
            if store is None:
                mcp = EUvsDisinfoMcp(settings)
                owned.append(mcp)
                store = McpDisinfoStore(mcp)
            result = await check(statements, store, llm, settings)
    except Exception as exc:  # noqa: BLE001 - reported in the result, never raised
        result = DisinfoCheck(
            status="error",
            warnings=[f"{type(exc).__name__}: {exc}"[:300]],
            duration_ms=int((time.perf_counter() - started) * 1000),
        )
    finally:
        for resource in owned:
            with contextlib.suppress(Exception):  # closing must not hide the result
                await resource.aclose()
    observability.log_event(
        "known_disinfo",
        level="info" if result.status != "error" else "warning",
        status=result.status,
        statements=len(statements),
        candidates=sum(len(s.candidates) for s in result.statements),
        matches=len(result.matches),
        duration_ms=result.duration_ms,
    )
    return result


__all__ = [
    "CandidateRef",
    "DisinfoCase",
    "DisinfoCheck",
    "DisinfoSettings",
    "DisinfoStore",
    "EUvsDisinfoMcp",
    "JsonLLM",
    "McpDisinfoStore",
    "McpError",
    "OpenAIJsonLLM",
    "StatementCheck",
    "check",
    "run",
]
