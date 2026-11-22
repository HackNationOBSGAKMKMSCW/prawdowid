"""Search all whitelisted sources for material matching the analysed claim."""

import asyncio
import logging
import time
from collections import defaultdict
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta

import httpx
from apiReading.exceptions import ApiAuthError, ApiReadingError, ApiTimeoutError
from articleScraping.safe_http import SafeFetcher
from textAnalysis.container import AnalysisDataContainer

from .adapters import SearchContext, get_adapter
from .cache import CACHE
from .detect import detect_and_update
from .models import (
    PENDING_ADAPTER,
    EvidenceHit,
    LastCheck,
    SourceFailure,
    TrustedSearchReport,
    TrustedSource,
)
from .ranking import rank_hits
from .registry import SourceNotFoundError, SourceRegistry, default_registry
from .settings import TrustedSettings
from .text import STOPWORDS, fold

logger = logging.getLogger(__name__)

MAX_QUERIES = 5
DETECTION_RETRY_AFTER = timedelta(hours=1)
_background: set[asyncio.Task[None]] = set()


def keyword_query(text: str, limit: int = 4) -> str:
    """Short phrase of content words (``Ziemia jest płaska`` -> ``Ziemia płaska``)."""

    words = [word.strip(".,;:!?\"'()[]„”«»") for word in text.split()]
    content = [word for word in words if len(word) > 2 and fold(word) not in STOPWORDS]
    return " ".join(content[:limit])


async def queries_for_text(text: str) -> list[str]:
    """Queries for raw claim text, built the same way as in the pipeline.

    Runs textAnalysis (LLM ``search_queries``); without it (no key, error)
    falls back to the text itself plus a short keyword phrase.
    """

    text = " ".join(text.split())[:2000]
    try:
        import textAnalysis

        queries = queries_for(await textAnalysis.run(text))
        if queries:
            return queries
    except asyncio.CancelledError:
        raise
    except Exception as exc:  # noqa: BLE001 - analysis is optional here
        logger.warning("textAnalysis unavailable for query building: %s", type(exc).__name__)
    fallback = [text[:200], keyword_query(text)]
    return [query for index, query in enumerate(fallback) if query and query not in fallback[:index]]


def queries_for(analysis: AnalysisDataContainer) -> list[str]:
    """Search phrases: LLM ``search_queries`` first, then claims, then keywords."""

    candidates = [
        *analysis.search_queries,
        *analysis.statements[:3],
    ]
    if not candidates and analysis.keyword_terms:
        candidates.append(" ".join(analysis.keyword_terms[:4]))
    if not candidates and analysis.source_text.strip():
        candidates.append(analysis.source_text.strip()[:200])
    unique: list[str] = []
    for candidate in candidates:
        query = " ".join(candidate.split())[:200]
        if query and query.lower() not in {existing.lower() for existing in unique}:
            unique.append(query)
    return unique[:MAX_QUERIES]


@asynccontextmanager
async def search_context(
    settings: TrustedSettings | None = None,
    http_client: httpx.AsyncClient | None = None,
    fetcher: SafeFetcher | None = None,
) -> AsyncIterator[SearchContext]:
    """Shared HTTP resources for one run; injected clients are not closed here."""

    settings = settings or TrustedSettings.from_environment()
    client = http_client or httpx.AsyncClient(
        headers={"User-Agent": "PrawdowidBot/1.0 (+fact-checking)"}
    )
    page_fetcher = fetcher or SafeFetcher(name="trusted_source", timeout=settings.source_timeout)
    try:
        yield SearchContext(http=client, fetcher=page_fetcher, cache=CACHE, settings=settings)
    finally:
        if fetcher is None:
            await page_fetcher.aclose()
        if http_client is None:
            await client.aclose()


def _failure(source_id: str, exc: BaseException) -> SourceFailure:
    if isinstance(exc, TimeoutError | ApiTimeoutError):
        kind = "Timeout"
    elif isinstance(exc, ApiAuthError):
        kind = "NotConfigured" if exc.status_code == 401 else "AuthError"
    else:
        kind = type(exc).__name__
    return SourceFailure(
        source_id=source_id, kind=kind, status_code=getattr(exc, "status_code", None)
    )


def _detection_due(source: TrustedSource, now: datetime) -> bool:
    check = source.last_check
    return check is None or check.ok or now - check.at >= DETECTION_RETRY_AFTER


async def ensure_detected(
    registry: SourceRegistry,
    ctx: SearchContext,
    sources: Sequence[TrustedSource] | None = None,
    *,
    force: bool = False,
) -> list[TrustedSource]:
    """Detect the adapter of pending sources (or all given sources when ``force``)."""

    now = datetime.now(UTC)
    targets = [
        source
        for source in (sources if sources is not None else registry.list())
        if force or (source.adapter == PENDING_ADAPTER and _detection_due(source, now))
    ]
    limiter = asyncio.Semaphore(4)

    async def one(source: TrustedSource) -> TrustedSource:
        async with limiter:
            try:
                updated = await asyncio.wait_for(
                    detect_and_update(source, ctx), timeout=ctx.settings.source_timeout * 4
                )
            except TimeoutError:
                updated = source.model_copy(
                    update={"last_check": LastCheck(at=datetime.now(UTC), ok=False, error="Timeout")}
                )
        try:
            registry.get(source.id)  # removed meanwhile? then do not resurrect it
        except SourceNotFoundError:
            return updated
        return registry.save(updated)

    return list(await asyncio.gather(*(one(source) for source in targets)))


def _schedule_detection(registry: SourceRegistry, settings: TrustedSettings) -> None:
    """Detect pending sources in the background so the current request is not delayed."""

    async def job() -> None:
        async with search_context(settings) as ctx:
            await ensure_detected(registry, ctx)

    if any(not task.done() for task in _background):
        return
    task = asyncio.get_running_loop().create_task(job())
    _background.add(task)
    task.add_done_callback(_background.discard)


async def search(
    queries: Sequence[str],
    *,
    registry: SourceRegistry | None = None,
    settings: TrustedSettings | None = None,
    http_client: httpx.AsyncClient | None = None,
    fetcher: SafeFetcher | None = None,
    detect_pending: bool = False,
) -> TrustedSearchReport:
    """Search every enabled source with ``queries`` and return ranked hits."""

    started = time.perf_counter()
    registry = registry or default_registry()
    settings = settings or TrustedSettings.from_environment()
    queries = [query for query in queries if query.strip()][:MAX_QUERIES]
    if not queries:
        return TrustedSearchReport(queries=[], hits=[])

    async with search_context(settings, http_client, fetcher) as ctx:
        if detect_pending:
            await ensure_detected(registry, ctx)
        sources = registry.list(enabled_only=True)
        if not detect_pending and any(source.adapter == PENDING_ADAPTER for source in sources):
            _schedule_detection(registry, settings)

        groups: dict[str, list[TrustedSource]] = defaultdict(list)
        failures: list[SourceFailure] = []
        for source in sources:
            if source.adapter == PENDING_ADAPTER:
                continue
            if get_adapter(source.adapter) is None:
                logger.warning("unknown adapter '%s' for source %s", source.adapter, source.id)
                failures.append(SourceFailure(source_id=source.id, kind="UnknownAdapter"))
                continue
            groups[source.adapter].append(source)

        async def run_group(name: str, members: list[TrustedSource]) -> list[EvidenceHit]:
            adapter = get_adapter(name)
            assert adapter is not None
            # Page adapters time out per source internally; this guards the group as a whole.
            return await asyncio.wait_for(
                adapter.search(members, queries, ctx), timeout=settings.source_timeout + 2
            )

        names = list(groups)
        outcomes = await asyncio.gather(
            *(run_group(name, groups[name]) for name in names), return_exceptions=True
        )

    raw_hits: list[EvidenceHit] = []
    relaxed: set[str] = set()
    for name, outcome in zip(names, outcomes, strict=True):
        adapter = get_adapter(name)
        if isinstance(outcome, BaseException):
            if isinstance(outcome, asyncio.CancelledError):
                raise outcome
            if not isinstance(outcome, ApiReadingError | TimeoutError | ValueError):
                logger.exception("adapter %s failed", name, exc_info=outcome)
            failures.extend(_failure(source.id, outcome) for source in groups[name])
            continue
        raw_hits.extend(outcome)
        if adapter is not None and adapter.server_ranked:
            relaxed.update(source.id for source in groups[name])

    by_id = {source.id: source for source in sources}
    hits = rank_hits(
        raw_hits,
        queries,
        by_id,
        relaxed_sources=frozenset(relaxed),
        max_hits=settings.max_hits,
        max_hits_per_source=settings.max_hits_per_source,
    )
    return TrustedSearchReport(
        queries=list(queries),
        hits=hits,
        failures=failures,
        sources_queried=sum(len(members) for members in groups.values()),
        duration_ms=round((time.perf_counter() - started) * 1000),
    )


async def run(
    analysis: AnalysisDataContainer,
    *,
    registry: SourceRegistry | None = None,
    http_client: httpx.AsyncClient | None = None,
) -> TrustedSearchReport:
    """Pipeline entry point: search the whitelist for the analysed claim.

    Never raises for source or registry problems: the pipeline must keep working
    with the other evidence sources when the whitelist is unavailable.
    """

    queries = queries_for(analysis)
    try:
        report = await search(queries, registry=registry, http_client=http_client)
    except asyncio.CancelledError:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.exception("trusted source search failed")
        return TrustedSearchReport(
            queries=queries,
            hits=[],
            failures=[SourceFailure(source_id="*", kind=type(exc).__name__)],
        )
    logger.info(
        "trusted sources: %d hits from %d sources in %d ms (%d failures)",
        len(report.hits),
        report.sources_queried,
        report.duration_ms,
        len(report.failures),
    )
    return report


async def warm(
    *, registry: SourceRegistry | None = None, settings: TrustedSettings | None = None
) -> dict[str, int]:
    """Detect pending sources and prefetch listing/feed/sitemap pages into the cache."""

    registry = registry or default_registry()
    settings = settings or TrustedSettings.from_environment()
    async with search_context(settings) as ctx:
        await ensure_detected(registry, ctx)
        targets = []
        for source in registry.list(enabled_only=True):
            adapter = get_adapter(source.adapter)
            if adapter is not None and adapter.prefetchable:
                targets.append((adapter, source))

        async def one(adapter, source) -> bool:  # type: ignore[no-untyped-def]
            try:
                await asyncio.wait_for(adapter.prefetch(source, ctx), timeout=settings.source_timeout * 2)
                return True
            except (ApiReadingError, TimeoutError, ValueError):
                return False

        results = await asyncio.gather(*(one(adapter, source) for adapter, source in targets))
    return {"prefetched": sum(results), "failed": len(results) - sum(results)}
