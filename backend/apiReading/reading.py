"""Read fact-check data for statements returned by the text analyzer."""

import asyncio
import re
import time
from collections.abc import Mapping

import httpx
from textAnalysis.container import AnalysisDataContainer
from textAnalysis.settings import Settings

from .models import Category, ReadingRequest, ReadingResult
from .reader import read


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


MAX_QUERY_CHARS = 100
MAX_KEYWORDS_IN_QUERY = 3
MAX_FALLBACK_ATTEMPTS = 2
MAX_CONCURRENCY = 10
_META_PREFIX = re.compile(
    r"^\s*(?:"
    r"(?:autor|tekst|artykuł|wypowiedź)(?:\s+tekstu)?\s+"
    r"(?:twierdzi|zawiera\s+twierdzenie|stwierdza|sugeruje|utrzymuje|podaje)"
    r"|w\s+tekście\s+(?:zanegowano|stwierdzono|twierdzono|wskazano|podano)"
    r")\s*,?\s*(?:że\s+)?",
    re.IGNORECASE,
)


def _shorten(text: str, limit: int = MAX_QUERY_CHARS) -> str:
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    first = re.split(r"(?<=[.!?])\s", text, maxsplit=1)[0]
    candidate = first if len(first) <= limit else text[:limit].rsplit(" ", 1)[0]
    return (candidate or text[:limit]).strip()


def clean_statement(statement: str) -> str:
    """Strip meta framing ("Autor twierdzi, że ...") and cap length for search."""
    cleaned = _META_PREFIX.sub("", statement.strip()).strip().rstrip(".")
    return _shorten(cleaned or statement)


def build_queries(analysis: AnalysisDataContainer, statement: str, first: bool) -> list[str]:
    """Ranked, de-duplicated query variants: original text, cleaned statement, keywords."""
    candidates: list[str] = []
    if first and analysis.original_text.strip():
        candidates.append(_shorten(analysis.original_text))
    candidates.append(clean_statement(statement))
    terms = [t.strip() for t in analysis.keyword_terms if t.strip()]
    if terms:
        candidates.append(" ".join(terms[:MAX_KEYWORDS_IN_QUERY]))
    queries: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        if candidate and candidate.casefold() not in seen:
            seen.add(candidate.casefold())
            queries.append(candidate)
    return queries[: MAX_FALLBACK_ATTEMPTS + 1]


async def run(analysis: AnalysisDataContainer) -> list[ReadingResult]:
    """Fetch one result per analyzed statement using the fact-check source.

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
    print(
        f"[apiReading] Przygotowano zapytania: liczba={len(statements)}; "
        f"język={analysis.language_code or 'nieznany'}, źródło=Google Fact Check.",
        flush=True,
    )

    query_variants = [
        build_queries(analysis, statement, first=index == 0)
        for index, statement in enumerate(statements)
    ]
    requests = [
        ReadingRequest(
            query=variants[0],
            categories=[Category.FACT_CHECK],
            language_code=analysis.language_code,
            page_size=10,
            metadata={"analysis_category": analysis.category},
        )
        for variants in query_variants
    ]
    semaphore = asyncio.Semaphore(MAX_CONCURRENCY)

    async def fetch_one(index: int, request: ReadingRequest) -> ReadingResult:
        async with semaphore:
            return await _fetch_with_fallback(index, request)

    async def _fetch_with_fallback(index: int, request: ReadingRequest) -> ReadingResult:
        variants = query_variants[index - 1]
        result = await _fetch_once(index, request)
        for attempt, query in enumerate(variants[1:], 2):
            if result.items or any(o.error is not None for o in result.results):
                break
            print(
                f"[apiReading] Zapytanie {index}: brak wyników, wariant {attempt}: {query!r}.",
                flush=True,
            )
            request = request.model_copy(update={"query": query})
            result = await _fetch_once(index, request)
        if result.items:
            print(f"[apiReading] Zapytanie {index}: dane dla {result.request.query!r}.", flush=True)
        return result

    async def _fetch_once(index: int, request: ReadingRequest) -> ReadingResult:
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
        f"[apiReading] Pakiet zakończył pracę po {time.perf_counter() - started_at:.1f}s.",
        flush=True,
    )
    for result in results:
        print(format_result(result), flush=True)
    return results
