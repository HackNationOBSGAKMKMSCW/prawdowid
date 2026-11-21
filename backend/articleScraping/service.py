"""Orchestrate trusted link sources and isolated article extraction outcomes."""

import asyncio
import threading
import time
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Literal
from urllib.parse import urlsplit

from apiReading.exceptions import (
    ApiAuthError,
    ApiHttpError,
    ApiRateLimitError,
    ApiReadingError,
    ApiResponseError,
    ApiTimeoutError,
)
from apiReading.models import ReadingResult
from textAnalysis.container import AnalysisDataContainer
from textAnalysis.settings import Settings

from .diffbot import DiffbotArticleClient, NotAnArticleError
from .links import (
    MAX_LINKS,
    MAX_USER_TEXT_LINKS,
    FactCheckLinkSource,
    TextLinkSource,
    select_candidates,
)
from .local import LocalArticleExtractor
from .mapping import map_article
from .models import ArticleFailure, ScrapedArticle, ScrapingReport
from .protocols import ArticleExtractor, CandidateLink, Clock, LinkSource, RawArticle, SystemClock

CACHE_TTL_SECONDS = 300
_article_cache: dict[str, tuple[float, ScrapedArticle | ArticleFailure]] = {}
_cache_lock = threading.Lock()
_RETRYABLE_HTTP_STATUSES = {429, 502, 503, 504}


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _failure(
    url: str,
    error: ApiReadingError | None = None,
    *,
    kind: str | None = None,
    source: Literal["fact_check", "user_text"] | None = None,
) -> ArticleFailure:
    if kind is None and isinstance(error, ApiRateLimitError):
        kind = "RateLimited"
    elif kind is None and isinstance(error, ApiTimeoutError):
        kind = "Timeout"
    elif kind is None and isinstance(error, NotAnArticleError):
        kind = "NotAnArticle"
    return ArticleFailure(
        url=url,
        kind=kind or (type(error).__name__ if error is not None else "ApiResponseError"),
        status_code=error.status_code if error is not None else None,
        source=source,
    )


def _is_cacheable_failure(error: ApiReadingError) -> bool:
    if isinstance(error, (ApiAuthError, ApiRateLimitError)):
        return False
    if isinstance(error, (NotAnArticleError, ApiResponseError)):
        return True
    return isinstance(error, ApiHttpError) and error.status_code not in _RETRYABLE_HTTP_STATUSES


def _cache_read(url: str) -> ScrapedArticle | ArticleFailure | None:
    now = time.monotonic()
    with _cache_lock:
        cached = _article_cache.get(url)
        if cached is None:
            return None
        expires_at, result = cached
        if expires_at <= now:
            _article_cache.pop(url, None)
            return None
        return result


def _cache_write(url: str, result: ScrapedArticle | ArticleFailure) -> None:
    now = time.monotonic()
    with _cache_lock:
        expired = [key for key, (expires_at, _) in _article_cache.items() if expires_at <= now]
        for key in expired:
            _article_cache.pop(key, None)
        if len(_article_cache) >= 1000:
            _article_cache.pop(next(iter(_article_cache)))
        _article_cache[url] = (now + CACHE_TTL_SECONDS, result)


def _select_candidates(
    analysis: AnalysisDataContainer,
    reading_results: Sequence[ReadingResult],
    link_sources: Sequence[LinkSource],
    max_links: int = MAX_LINKS,
    max_user_links: int = MAX_USER_TEXT_LINKS,
) -> tuple[list[CandidateLink], list[ArticleFailure], int]:
    candidates = [
        candidate
        for source in link_sources
        for candidate in source.extract(analysis, reading_results)
    ]
    selected, rejected = select_candidates(candidates, max_links, max_user_links)
    failures = [
        _failure(
            candidate.url[:2048] if kind == "InvalidUrl" else candidate.url,
            kind=kind,
            source=candidate.source,
        )
        for candidate, kind in rejected
    ]
    return selected, failures, len(candidates)


async def _extract_all(
    candidates: list[CandidateLink],
    extractor: ArticleExtractor,
    *,
    max_concurrency: int,
    deadline_seconds: float,
    use_cache: bool,
) -> list[ScrapedArticle | ArticleFailure]:
    results: list[ScrapedArticle | ArticleFailure | None] = [None] * len(candidates)
    pending: list[int] = []
    for index, candidate in enumerate(candidates):
        cached = _cache_read(candidate.url) if use_cache else None
        if cached is None:
            pending.append(index)
        else:
            results[index] = cached.model_copy(update={"source": candidate.source})
            host = urlsplit(candidate.url).hostname or "unknown"
            if isinstance(cached, ArticleFailure):
                print(
                    f"[articleScraping] Link {index + 1}/{len(candidates)} ({host}): "
                    f"błąd: {cached.kind}",
                    flush=True,
                )
            else:
                print(
                    f"[articleScraping] Link {index + 1}/{len(candidates)} ({host}): OK po 0.0s",
                    flush=True,
                )

    queue: asyncio.Queue[int] = asyncio.Queue()
    for index in pending:
        queue.put_nowait(index)
    abort_batch = asyncio.Event()

    async def worker() -> None:
        while not queue.empty():
            index = queue.get_nowait()
            candidate = candidates[index]
            host = urlsplit(candidate.url).hostname or "unknown"
            if abort_batch.is_set():
                results[index] = _failure(
                    candidate.url, kind="BatchAborted", source=candidate.source
                )
                print(
                    f"[articleScraping] Link {index + 1}/{len(candidates)} ({host}): "
                    "błąd: BatchAborted",
                    flush=True,
                )
                continue
            link_started_at = time.perf_counter()
            try:
                raw_article: RawArticle = await extractor.extract(candidate.url)
                article = map_article(candidate.url, raw_article, source=candidate.source)
                results[index] = article
                if use_cache:
                    _cache_write(candidate.url, article)
                print(
                    f"[articleScraping] Link {index + 1}/{len(candidates)} ({host}): "
                    f"OK po {time.perf_counter() - link_started_at:.1f}s",
                    flush=True,
                )
            except ApiReadingError as exc:
                failure = _failure(candidate.url, exc, source=candidate.source)
                results[index] = failure
                if use_cache and _is_cacheable_failure(exc):
                    _cache_write(candidate.url, failure)
                if isinstance(exc, (ApiAuthError, ApiRateLimitError)):
                    abort_batch.set()
                print(
                    f"[articleScraping] Link {index + 1}/{len(candidates)} ({host}): "
                    f"błąd: {failure.kind}",
                    flush=True,
                )

    worker_count = min(max(1, max_concurrency), len(pending)) if pending else 0
    try:
        async with asyncio.timeout(deadline_seconds):
            await asyncio.gather(*(worker() for _ in range(worker_count)))
    except TimeoutError:
        for index, result in enumerate(results):
            if result is None:
                candidate = candidates[index]
                results[index] = _failure(candidate.url, kind="Timeout", source=candidate.source)
                host = urlsplit(candidate.url).hostname or "unknown"
                print(
                    f"[articleScraping] Link {index + 1}/{len(candidates)} ({host}): błąd: Timeout",
                    flush=True,
                )

    return [result for result in results if result is not None]


def _build_extractor(settings: Settings) -> ArticleExtractor:
    """Local trafilatura extraction by default; Diffbot only when explicitly selected."""

    choice = settings.article_extractor
    if choice == "diffbot":
        return DiffbotArticleClient(
            api_key=settings.diffbot_api_token,
            max_concurrency=settings.article_max_concurrency,
        )
    if choice != "local":
        raise ValueError("ARTICLE_EXTRACTOR must be 'local' or 'diffbot'")
    return LocalArticleExtractor()


async def run(
    analysis: AnalysisDataContainer,
    reading_results: Sequence[ReadingResult] = (),
    *,
    extractor: ArticleExtractor | None = None,
    link_sources: Sequence[LinkSource] | None = None,
    clock: Clock | None = None,
) -> ScrapingReport:
    """Extract article bodies from analysis and fact-check URLs, isolating failures."""

    run_started_at = time.perf_counter()
    clock = clock or SystemClock()
    started_at = _as_utc(analysis.started_at or clock.now())
    user_text = analysis.original_text or analysis.source_text
    sources = (
        link_sources if link_sources is not None else (FactCheckLinkSource(), TextLinkSource())
    )
    settings = Settings.from_environment() if extractor is None else None
    candidates, failures, found_count = _select_candidates(
        analysis,
        reading_results,
        sources,
        settings.article_max_links if settings else MAX_LINKS,
        settings.article_max_user_links if settings else MAX_USER_TEXT_LINKS,
    )
    print(
        f"[articleScraping] Znaleziono kandydatów: {found_count}; wybrano: {len(candidates)}.",
        flush=True,
    )

    if settings is not None and not settings.article_scraping_enabled:
        failures.extend(
            _failure(candidate.url, kind="ScrapingDisabled", source=candidate.source)
            for candidate in candidates
        )
        print(
            f"[articleScraping] Zakończono: artykułów 0, błędów {len(failures)} "
            f"po {time.perf_counter() - run_started_at:.1f}s.",
            flush=True,
        )
        return ScrapingReport(
            started_at=started_at,
            user_text=user_text,
            articles=[],
            failures=failures,
            finished_at=_as_utc(clock.now()),
        )

    owns_extractor = extractor is None
    active_extractor = extractor if extractor is not None else _build_extractor(settings)
    try:
        extracted = await _extract_all(
            candidates,
            active_extractor,
            max_concurrency=settings.article_max_concurrency if settings else 1,
            deadline_seconds=settings.article_batch_timeout if settings else 60.0,
            use_cache=owns_extractor,
        )
    finally:
        if owns_extractor:
            await active_extractor.aclose()  # type: ignore[attr-defined]

    articles = [item for item in extracted if isinstance(item, ScrapedArticle)]
    failures.extend(item for item in extracted if isinstance(item, ArticleFailure))
    print(
        f"[articleScraping] Zakończono: artykułów {len(articles)}, błędów {len(failures)} "
        f"po {time.perf_counter() - run_started_at:.1f}s.",
        flush=True,
    )
    return ScrapingReport(
        started_at=started_at,
        user_text=user_text,
        articles=articles,
        failures=failures,
        finished_at=_as_utc(clock.now()),
    )
