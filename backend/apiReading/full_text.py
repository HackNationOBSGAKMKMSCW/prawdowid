"""Search fact checks using the original text supplied to the analyzer."""

import time
from collections.abc import Mapping

import httpx
from textAnalysis.container import AnalysisDataContainer
from textAnalysis.settings import Settings

from .models import Category, ReadingRequest, ReadingResult
from .reader import read

MAX_QUERY_CHARS = 1_000


async def run_full_text(analysis: AnalysisDataContainer) -> ReadingResult:
    """Search once with the analyzer's source text, without logging its contents."""
    started_at = time.perf_counter()
    print("[apiReading] Przygotowuję zapytanie z pełnego tekstu analizy...", flush=True)
    text = analysis.source_text.strip()
    if not text:
        print("[apiReading] Przerwano: analiza nie zawiera tekstu źródłowego.", flush=True)
        raise ValueError("analysis must contain source text to search")

    truncated = len(text) > MAX_QUERY_CHARS
    request = ReadingRequest(
        query=text[:MAX_QUERY_CHARS],
        categories=[Category.FACT_CHECK],
        language_code=analysis.language_code,
        page_size=10,
        metadata={
            "analysis_category": analysis.category,
            "truncated": truncated,
        },
    )
    settings = Settings.from_environment()
    api_keys: Mapping[str, str] = (
        {"google_fact_check": settings.google_fact_check_api_key}
        if settings.google_fact_check_api_key
        else {}
    )
    print(
        f"[apiReading] Przygotowano zapytanie: długość={len(request.query)} znaków; "
        f"język={analysis.language_code or 'nieznany'}, "
        f"źródło=Google Fact Check, obcięto={truncated}.",
        flush=True,
    )
    print("[apiReading] Otwieram klienta i uruchamiam zapytanie...", flush=True)

    try:
        async with httpx.AsyncClient() as client:
            result = await read(request, api_keys=api_keys, http_client=client)
    except Exception as exc:
        print(
            f"[apiReading] Odczyt przerwany po {time.perf_counter() - started_at:.1f}s "
            f"({type(exc).__name__}).",
            flush=True,
        )
        raise

    outcomes = []
    for outcome in result.results:
        if outcome.error is not None:
            outcomes.append(f"{outcome.source}: {type(outcome.error).__name__}")
        else:
            item_count = len(outcome.result.items) if outcome.result is not None else 0
            outcomes.append(f"{outcome.source}: {item_count} wyników")
    print(
        f"[apiReading] Zapytanie zakończone po {time.perf_counter() - started_at:.1f}s; "
        f"elementów: {len(result.items)}; {'; '.join(outcomes)}.",
        flush=True,
    )
    return result
