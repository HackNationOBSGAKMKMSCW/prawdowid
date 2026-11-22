"""Shared plumbing for adapters that download whole pages and match them locally."""

import asyncio
import logging
from collections.abc import Awaitable, Callable, Sequence

from apiReading.exceptions import ApiReadingError

from ..models import EvidenceHit, TrustedSource
from ..parsing import PageEntry
from . import SearchContext

XML_TYPES = (
    "application/rss+xml",
    "application/atom+xml",
    "application/xml",
    "text/xml",
    "application/rdf+xml",
    "application/x-gzip",
    "application/gzip",
    "application/octet-stream",
    "text/plain",
)
HTML_TYPES = ("text/html", "application/xhtml+xml")
logger = logging.getLogger(__name__)

EntryLoader = Callable[[TrustedSource, SearchContext], Awaitable[list[PageEntry]]]


async def cached_entries(
    kind: str, source: TrustedSource, ctx: SearchContext, load: EntryLoader
) -> list[PageEntry]:
    """Entries for ``source`` from cache (TTL ``cache_ttl``), stale copy on refresh errors."""

    return await ctx.cache.get_or_fetch(
        _key(kind, source), ctx.settings.cache_ttl, lambda: load(source, ctx)
    )


def _key(kind: str, source: TrustedSource) -> tuple[object, ...]:
    return (kind, source.id, source.url, tuple(sorted(map(str, source.params.items()))))


async def search_entries(
    kind: str, sources: Sequence[TrustedSource], ctx: SearchContext, load: EntryLoader
) -> list[EvidenceHit]:
    """Return every cached entry as an unranked hit; ``ranking`` does the matching."""

    async def one(source: TrustedSource) -> list[PageEntry]:
        try:
            return await asyncio.wait_for(
                cached_entries(kind, source, ctx, load), timeout=ctx.settings.source_timeout
            )
        except TimeoutError:
            stale = ctx.cache.peek(_key(kind, source))
            if stale is not None:
                return stale[0]
            raise

    outcomes = await asyncio.gather(*(one(source) for source in sources), return_exceptions=True)
    hits: list[EvidenceHit] = []
    errors: list[BaseException] = []
    for source, outcome in zip(sources, outcomes, strict=True):
        if isinstance(outcome, BaseException):
            if not isinstance(outcome, (ApiReadingError, ValueError, TimeoutError)):
                raise outcome
            logger.info("trusted source %s unavailable: %s", source.id, type(outcome).__name__)
            errors.append(outcome)
            continue
        hits.extend(
            EvidenceHit(
                source_id=source.id,
                source_name=source.name,
                trust=source.trust,
                url=entry.url,
                title=entry.title,
                snippet=entry.snippet,
                published_at=entry.published_at,
            )
            for entry in outcome
        )
    if errors and len(errors) == len(sources):
        raise errors[0]
    return hits
