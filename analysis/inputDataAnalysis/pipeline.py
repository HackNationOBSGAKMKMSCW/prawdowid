"""Punkt wejścia: równoległa analiza manipulacji i dat."""

from __future__ import annotations

import asyncio
from collections.abc import Iterable
from datetime import date
from typing import Any

from .llm import StructuredCall, reset_clients, structured_call
from .manipulation import analyze_manipulation
from .models import AnalysisResult, TruthSource
from .temporal import analyze_dates


def _coerce_sources(sources: Iterable[TruthSource | dict[str, Any]] | None) -> list[TruthSource]:
    return [
        s if isinstance(s, TruthSource) else TruthSource.model_validate(s) for s in sources or []
    ]


async def analyze_async(
    user_input: str,
    sources: Iterable[TruthSource | dict[str, Any]] | None = None,
    article_date: date | str | None = None,
    *,
    call: StructuredCall = structured_call,
) -> AnalysisResult:
    """Analizuje tekst użytkownika względem źródeł prawdy (do użycia w kodzie asynchronicznym).

    ``call`` pozwala podstawić własną funkcję LLM (np. atrapę w testach).
    Błędy LLM są propagowane jako ``inputDataAnalysis.llm.LLMError``.
    """
    srcs = _coerce_sources(sources)
    if isinstance(article_date, str):
        article_date = date.fromisoformat(article_date[:10]) if article_date.strip() else None
    manipulation, dates = await asyncio.gather(
        analyze_manipulation(user_input, srcs, article_date, call=call),
        analyze_dates(user_input, srcs, article_date, call=call),
    )
    return AnalysisResult(manipulation=manipulation, dates=dates)


def analyze(
    user_input: str,
    sources: Iterable[TruthSource | dict[str, Any]] | None = None,
    article_date: date | str | None = None,
    *,
    call: StructuredCall = structured_call,
) -> AnalysisResult:
    """Synchroniczna wersja ``analyze_async``. W FastAPI/async użyj ``await analyze_async(...)``."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        pass
    else:
        raise RuntimeError("analyze() wywołano wewnątrz pętli zdarzeń; użyj await analyze_async().")

    async def run() -> AnalysisResult:
        try:
            return await analyze_async(user_input, sources, article_date, call=call)
        finally:
            await reset_clients()

    return asyncio.run(run())
