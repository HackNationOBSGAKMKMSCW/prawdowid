"""Read fact-check data for statements returned by the text analyzer."""

import asyncio
import time
from collections.abc import Mapping

import httpx
from textAnalysis.container import AnalysisDataContainer
from textAnalysis.settings import Settings

from .models import Category, ReadingRequest, ReadingResult
from .reader import read

# Google Fact Check matches short phrases, not whole sentences: a full claim usually
# returns nothing while "płaca minimalna" returns ten reviews. Short phrases run in
# addition to the per-statement queries and land in the verdict's shared pool.
MAX_SHORT_QUERIES = 8
SHORT_QUERY_PAGE_SIZE = 5


def short_queries(analysis: AnalysisDataContainer, statements: list[str]) -> list[str]:
    """LLM search phrases first, then keyword terms; no duplicates of statements."""

    seen = {statement.lower() for statement in statements}
    phrases: list[str] = []
    for candidate in (*analysis.search_queries, *analysis.keyword_terms):
        phrase = " ".join(str(candidate).split())
        if phrase and phrase.lower() not in seen:
            seen.add(phrase.lower())
            phrases.append(phrase)
    return phrases[:MAX_SHORT_QUERIES]


def format_result(result: ReadingResult) -> str:
    """Render one result as readable lines: claim, publisher, rating, url."""
    lines = [f"[apiReading] Wyniki dla: {result.request.query} (elementów: {len(result.items)})"]
    for outcome in result.results:
        if outcome.error is not None:
            lines.append(
                f"  BŁĄD {outcome.source}: {type(outcome.error).__name__}: {outcome.error}"
            )
    if not result.items:
        lines.append("  Nie znaleziono sprawdzonych faktów.")
    for item in result.items:
        claim = item.payload
        lines.append(f"  [{item.source}] {claim.get('text', '')} (autor: {claim.get('claimant')})")
        for review in claim.get("claimReview") or []:
            publisher = (review.get("publisher") or {}).get("name")
            lines.append(f"    - {publisher} | {review.get('textualRating')} | {review.get('url')}")
    return "\n".join(lines)


async def run(analysis: AnalysisDataContainer) -> list[ReadingResult]:
    """Fetch one result per analyzed statement, plus short search phrases, from fact-checks.

    Results for statements come first, in statement order; phrase results follow
    (their query is not a statement, so the verdict treats them as a shared pool).

    The analyzer's topic category is preserved as metadata; the provider does
    not support filtering on that topic label.
    """
    started_at = time.perf_counter()
    print("[apiReading] Przygotowuję zapytania z obiektu analizy...", flush=True)
    statements = [statement.strip() for statement in analysis.statements if statement.strip()]
    if not statements:
        print("[apiReading] Przerwano: analiza nie zawiera stwierdzeń.", flush=True)
        raise ValueError("analysis must contain at least one statement to search")
    settings = Settings.from_environment()
    api_keys: Mapping[str, str] = (
        {"google_fact_check": settings.google_fact_check_api_key}
        if settings.google_fact_check_api_key
        else {}
    )
    phrases = short_queries(analysis, statements)
    print(
        f"[apiReading] Przygotowano zapytania: liczba={len(statements) + len(phrases)} "
        f"(stwierdzenia: {len(statements)}, krótkie frazy: {len(phrases)}); "
        f"język={analysis.language_code or 'nieznany'}, źródło=Google Fact Check.",
        flush=True,
    )

    requests = [
        ReadingRequest(
            query=query,
            categories=[Category.FACT_CHECK],
            language_code=analysis.language_code,
            page_size=page_size,
            metadata={"analysis_category": analysis.category},
        )
        for queries, page_size in ((statements, 10), (phrases, SHORT_QUERY_PAGE_SIZE))
        for query in queries
    ]

    async def fetch_one(index: int, request: ReadingRequest) -> ReadingResult:
        request_started_at = time.perf_counter()
        print(
            f"[apiReading] Zapytanie {index}/{len(requests)}: start ({len(request.query)} znaków).",
            flush=True,
        )
        try:
            result = await read(request, api_keys=api_keys, http_client=client)
        except Exception as exc:
            print(
                f"[apiReading] Zapytanie {index}/{len(requests)} przerwane po "
                f"{time.perf_counter() - request_started_at:.1f}s ({type(exc).__name__}).",
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
            f"[apiReading] Zapytanie {index}/{len(requests)} zakończone po "
            f"{time.perf_counter() - request_started_at:.1f}s; "
            f"elementów: {len(result.items)}; {'; '.join(outcomes)}.",
            flush=True,
        )
        return result

    print("[apiReading] Otwieram klienta i uruchamiam zapytania równolegle...", flush=True)
    try:
        async with httpx.AsyncClient() as client:
            results = list(
                await asyncio.gather(
                    *(fetch_one(index, request) for index, request in enumerate(requests, 1))
                )
            )
    except Exception as exc:
        print(
            f"[apiReading] Odczyt przerwany po {time.perf_counter() - started_at:.1f}s "
            f"({type(exc).__name__}).",
            flush=True,
        )
        raise

    print(
        f"[apiReading] Pakiet zakończył pracę po {time.perf_counter() - started_at:.1f}s; "
        f"zapytań={len(results)}, wyników={sum(len(result.items) for result in results)}.",
        flush=True,
    )
    return results
