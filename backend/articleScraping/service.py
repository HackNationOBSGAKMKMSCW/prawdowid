"""Orchestrate trusted link sources and isolated article extraction outcomes."""

import asyncio
import threading
import time
from collections.abc import Sequence
from datetime import UTC, datetime

from apiReading.exceptions import (
    ApiAuthError,
    ApiRateLimitError,
    ApiReadingError,
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
)
from .mapping import map_article
from .models import ArticleFailure, ScrapedArticle, ScrapingReport
from .protocols import ArticleExtractor, CandidateLink, Clock, LinkSource, RawArticle, SystemClock
from .url_validation import InvalidUrlError, validate_url

CACHE_TTL_SECONDS = 300
_article_cache: dict[str, tuple[float, ScrapedArticle | ArticleFailure]] = {}
_cache_lock = threading.Lock()


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _failure(
    url: str, error: ApiReadingError | None = None, *, kind: str | None = None
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
    )


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
) -> tuple[list[CandidateLink], list[ArticleFailure]]:
    candidates = [
        candidate
        for source in link_sources
        for candidate in source.extract(analysis, reading_results)
    ]
    # Fact-check publisher links have priority over the smaller user-text quota.
    candidates.sort(key=lambda candidate: candidate.source != "fact_check")
    selected: list[CandidateLink] = []
    failures: list[ArticleFailure] = []
    seen: set[str] = set()
    source_counts = {"fact_check": 0, "user_text": 0}

    for candidate in candidates:
        try:
            url = validate_url(candidate.url)
        except InvalidUrlError:
            failures.append(ArticleFailure(url=candidate.url[:2048], kind="InvalidUrl"))
            continue
        if url in seen:
            continue
        seen.add(url)

        if len(selected) >= MAX_LINKS or (
            candidate.source == "user_text" and source_counts["user_text"] >= MAX_USER_TEXT_LINKS
        ):
            failures.append(ArticleFailure(url=url, kind="LinkLimitExceeded"))
            continue
        if candidate.source in source_counts:
            source_counts[candidate.source] += 1
        selected.append(CandidateLink(url=url, source=candidate.source))
    return selected, failures


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
            results[index] = cached

    queue: asyncio.Queue[int] = asyncio.Queue()
    for index in pending:
        queue.put_nowait(index)
    abort_batch = asyncio.Event()

    async def worker() -> None:
        while not queue.empty():
            index = queue.get_nowait()
            candidate = candidates[index]
            if abort_batch.is_set():
                results[index] = _failure(candidate.url, kind="BatchAborted")
                continue
            try:
                raw_article: RawArticle = await extractor.extract(candidate.url)
                article = map_article(candidate.url, raw_article)
                results[index] = article
                if use_cache:
                    _cache_write(candidate.url, article)
            except ApiReadingError as exc:
                results[index] = _failure(candidate.url, exc)
                if use_cache:
                    _cache_write(candidate.url, results[index])
                if isinstance(exc, (ApiAuthError, ApiRateLimitError)):
                    abort_batch.set()

    worker_count = min(max(1, max_concurrency), len(pending)) if pending else 0
    try:
        async with asyncio.timeout(deadline_seconds):
            await asyncio.gather(*(worker() for _ in range(worker_count)))
    except TimeoutError:
        for index, result in enumerate(results):
            if result is None:
                results[index] = _failure(candidates[index].url, kind="Timeout")

    return [result for result in results if result is not None]


async def run(
    analysis: AnalysisDataContainer,
    reading_results: Sequence[ReadingResult] = (),
    *,
    extractor: ArticleExtractor | None = None,
    link_sources: Sequence[LinkSource] | None = None,
    clock: Clock | None = None,
) -> ScrapingReport:
    """Extract article bodies from analysis and fact-check URLs, isolating failures."""

    clock = clock or SystemClock()
    started_at = _as_utc(analysis.started_at or clock.now())
    user_text = analysis.original_text or analysis.source_text
    sources = (
        link_sources if link_sources is not None else (FactCheckLinkSource(), TextLinkSource())
    )
    candidates, failures = _select_candidates(analysis, reading_results, sources)

    settings = Settings.from_environment() if extractor is None else None
    if settings is not None and not settings.article_scraping_enabled:
        failures.extend(
            _failure(candidate.url, kind="ScrapingDisabled") for candidate in candidates
        )
        return ScrapingReport(
            started_at=started_at,
            user_text=user_text,
            articles=[],
            failures=failures,
            finished_at=_as_utc(clock.now()),
        )

    owns_extractor = extractor is None
    active_extractor = (
        extractor
        if extractor is not None
        else DiffbotArticleClient(
            api_key=settings.diffbot_api_token,
            max_concurrency=settings.article_max_concurrency,
        )
    )
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
    return ScrapingReport(
        started_at=started_at,
        user_text=user_text,
        articles=articles,
        failures=failures,
        finished_at=_as_utc(clock.now()),
    )
