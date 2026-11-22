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
    TrustedLinkSource,
    select_candidates,
)
from .local import LocalArticleExtractor
from .mapping import map_article
from .models import (
    MIN_DISTINCT_SITES,
    ArticleFailure,
    ScrapedArticle,
    ScrapingReport,
    SourceLink,
)
from .protocols import ArticleExtractor, CandidateLink, Clock, LinkSource, RawArticle, SystemClock
from .url_validation import InvalidUrlError, site_key, validate_url

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
    source: Literal["fact_check", "trusted_source", "user_text"] | None = None,
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
) -> tuple[list[CandidateLink], list[CandidateLink], list[ArticleFailure], int]:
    """Selected links, reserve links (over the quota) and invalid-link failures."""

    candidates = [
        candidate
        for source in link_sources
        for candidate in source.extract(analysis, reading_results)
    ]
    selected, rejected = select_candidates(candidates, max_links, max_user_links)
    reserves = [candidate for candidate, kind in rejected if kind == "LinkLimitExceeded"]
    failures = [
        _failure(candidate.url[:2048], kind=kind, source=candidate.source)
        for candidate, kind in rejected
        if kind != "LinkLimitExceeded"
    ]
    return selected, reserves, failures, len(candidates)


def _next_reserves(
    reserves: list[CandidateLink], covered: set[str], needed: int
) -> list[CandidateLink]:
    """Pop up to ``needed`` reserve links, each from a different, not yet covered site."""

    picked: list[CandidateLink] = []
    sites: set[str] = set()
    for candidate in list(reserves):
        if len(picked) >= needed:
            break
        site = site_key(candidate.url)
        if candidate.source == "user_text" or site in covered or site in sites:
            continue
        reserves.remove(candidate)
        picked.append(candidate)
        sites.add(site)
    return picked


def _source_links(
    attempted: Sequence[CandidateLink],
    results: Sequence[ScrapedArticle | ArticleFailure],
    reserves: Sequence[CandidateLink],
    trusted: object | None,
) -> list[SourceLink]:
    """All links found for the claim, with what happened to each one."""

    links: list[SourceLink] = []
    seen: set[str] = set()

    def add(url: str, kind, status, title=None, publisher=None) -> None:  # type: ignore[no-untyped-def]
        if url in seen:
            return
        seen.add(url)
        links.append(
            SourceLink(
                url=url, site=site_key(url), kind=kind, title=title, publisher=publisher, status=status
            )
        )

    for candidate, result in zip(attempted, results, strict=True):
        scraped = isinstance(result, ScrapedArticle)
        title = result.title if scraped and result.title else candidate.title
        add(candidate.url, candidate.source, "scraped" if scraped else "failed", title, candidate.publisher)
    for candidate in reserves:
        add(candidate.url, candidate.source, "not_scraped", candidate.title, candidate.publisher)
    for hit in getattr(trusted, "hits", None) or []:
        if getattr(hit, "kind", None) != "reference":
            continue
        try:
            url = validate_url(hit.url)
        except (InvalidUrlError, TypeError):
            continue
        add(url, "trusted_reference", "reference", getattr(hit, "title", None),
            getattr(hit, "source_name", None))
    return links


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
                article = map_article(
                    candidate.url,
                    raw_article,
                    source=candidate.source,
                    title=candidate.title,
                    publisher=candidate.publisher,
                )
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
    trusted: object | None = None,
    submitted_at: datetime | None = None,
    min_sites: int = MIN_DISTINCT_SITES,
) -> ScrapingReport:
    """Download full articles for the claim and return the final structured report.

    Links come from fact-check results, the trusted-source whitelist
    (``trusted``: ``trustedSources.TrustedSearchReport``) and the user text.
    Articles must come from at least ``min_sites`` different sites: when the
    first batch does not reach that, reserve links from other sites are
    downloaded until it does or no reserves are left (``min_sites_met``).

    ``submitted_at`` is when the user sent the request; by default it is
    ``analysis.started_at`` (``textAnalysis.run(text, started_at=...)``).
    """

    run_started_at = time.perf_counter()
    clock = clock or SystemClock()
    request_time = _as_utc(submitted_at or analysis.started_at or clock.now())
    user_input = analysis.original_text or analysis.source_text
    sources = (
        link_sources
        if link_sources is not None
        else (FactCheckLinkSource(), TrustedLinkSource(trusted), TextLinkSource())  # type: ignore[arg-type]
    )
    settings = Settings.from_environment() if extractor is None else None
    candidates, reserves, failures, found_count = _select_candidates(
        analysis,
        reading_results,
        sources,
        settings.article_max_links if settings else MAX_LINKS,
        settings.article_max_user_links if settings else MAX_USER_TEXT_LINKS,
    )
    by_source = {
        name: sum(1 for c in candidates if c.source == name) for name in ("fact_check", "user_text")
    }
    print(
        f"[articleScraping] Znaleziono kandydatów: {found_count}; wybrano: {len(candidates)}; "
        f"zapas: {len(reserves)} "
        f"(fact_check: {by_source['fact_check']}, user_text: {by_source['user_text']}).",
        flush=True,
    )
    if not by_source["fact_check"]:
        print(
            "[articleScraping] Brak linków z fact-checków (API nie zwróciło twierdzeń lub bez URL).",
            flush=True,
        )

    def build_report(
        attempted: Sequence[CandidateLink], results: Sequence[ScrapedArticle | ArticleFailure]
    ) -> ScrapingReport:
        articles = [item for item in results if isinstance(item, ScrapedArticle)]
        distinct = len({article.site for article in articles})
        return ScrapingReport(
            submitted_at=request_time,
            user_input=user_input,
            articles=articles,
            sources=_source_links(attempted, results, reserves, trusted),
            distinct_sites=distinct,
            min_sites_met=distinct >= min_sites,
            failures=[*failures, *(item for item in results if isinstance(item, ArticleFailure))],
            finished_at=_as_utc(clock.now()),
        )

    if settings is not None and not settings.article_scraping_enabled:
        disabled = [
            _failure(candidate.url, kind="ScrapingDisabled", source=candidate.source)
            for candidate in candidates
        ]
        print("[articleScraping] Pobieranie wyłączone (ARTICLE_SCRAPING_ENABLED).", flush=True)
        return build_report(candidates, disabled)

    owns_extractor = extractor is None
    active_extractor = extractor if extractor is not None else _build_extractor(settings)
    deadline = settings.article_batch_timeout if settings else 60.0
    concurrency = settings.article_max_concurrency if settings else 1
    attempted: list[CandidateLink] = list(candidates)
    results: list[ScrapedArticle | ArticleFailure] = []
    try:
        results = await _extract_all(
            candidates,
            active_extractor,
            max_concurrency=concurrency,
            deadline_seconds=deadline,
            use_cache=owns_extractor,
        )
        while True:
            covered = {item.site for item in results if isinstance(item, ScrapedArticle)}
            remaining = deadline - (time.perf_counter() - run_started_at)
            if len(covered) >= min_sites or remaining <= 1:
                break
            extra = _next_reserves(reserves, covered, min_sites - len(covered))
            if not extra:
                break
            print(
                f"[articleScraping] Artykuły z {len(covered)} stron(y), wymagane {min_sites}; "
                f"pobieram zapasowe: {len(extra)}.",
                flush=True,
            )
            attempted.extend(extra)
            results.extend(
                await _extract_all(
                    extra,
                    active_extractor,
                    max_concurrency=concurrency,
                    deadline_seconds=remaining,
                    use_cache=owns_extractor,
                )
            )
    finally:
        if owns_extractor:
            await active_extractor.aclose()  # type: ignore[attr-defined]

    final = build_report(attempted, results)
    if not final.min_sites_met:
        print(
            f"[articleScraping] Uwaga: artykuły tylko z {final.distinct_sites} stron(y) "
            f"(wymagane {min_sites}); brak innych źródeł.",
            flush=True,
        )
    print(
        f"[articleScraping] Zakończono: artykułów {len(final.articles)} z {final.distinct_sites} "
        f"stron, błędów {len(final.failures)} po {time.perf_counter() - run_started_at:.1f}s.",
        flush=True,
    )
    return final
