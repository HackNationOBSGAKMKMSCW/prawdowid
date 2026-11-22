"""Sitemaps: only recent child sitemaps are read, so huge archives never get downloaded."""

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from urllib.parse import urlsplit

from apiReading.exceptions import ApiResponseError

from ..models import EvidenceHit, TrustedSource
from ..parsing import MAX_ENTRIES, PageEntry, parse_sitemap
from ..text import url_words
from . import SearchContext, SourceAdapter, register_adapter
from ._pages import XML_TYPES, cached_entries, search_entries

MAX_CHILD_SITEMAPS = 3
MAX_SITEMAP_BYTES = 10 * 1024 * 1024
DEFAULT_MAX_AGE_DAYS = 90


async def _fetch_sitemap(url: str, ctx: SearchContext):  # type: ignore[no-untyped-def]
    page = await ctx.fetcher.get(
        url,
        accept=XML_TYPES,
        accept_header="application/xml, text/xml;q=0.9, */*;q=0.5",
        max_bytes=MAX_SITEMAP_BYTES,
    )
    document = parse_sitemap(page.body)
    if document is None:
        raise ApiResponseError("sitemap", "sitemap could not be parsed")
    return document


def _title_from_slug(url: str) -> str:
    return " ".join(url_words(url).split()[-12:])


async def load_sitemap(source: TrustedSource, ctx: SearchContext) -> list[PageEntry]:
    max_age = int(source.params.get("max_age_days") or DEFAULT_MAX_AGE_DAYS)
    cutoff = datetime.now(UTC) - timedelta(days=max_age)
    document = await _fetch_sitemap(source.params.get("sitemap_url") or source.url, ctx)
    entries = document.entries
    if document.is_index:
        children = sorted(
            document.entries,
            key=lambda entry: entry.published_at or datetime.min.replace(tzinfo=UTC),
            reverse=True,
        )
        recent = [child for child in children if child.published_at is None or child.published_at >= cutoff]
        entries = []
        for child in recent[:MAX_CHILD_SITEMAPS]:
            child_document = await _fetch_sitemap(child.url, ctx)
            if not child_document.is_index:
                entries.extend(child_document.entries)
            if len(entries) >= MAX_ENTRIES:
                break

    prefix = source.path_prefix.rstrip("/")
    selected: list[PageEntry] = []
    for entry in entries[:MAX_ENTRIES]:
        if entry.published_at is not None and entry.published_at < cutoff:
            continue
        if prefix and not urlsplit(entry.url).path.startswith(prefix):
            continue
        selected.append(
            PageEntry(
                url=entry.url,
                title=entry.title or _title_from_slug(entry.url),
                published_at=entry.published_at,
            )
        )
    return selected


@register_adapter("sitemap")
class SitemapAdapter(SourceAdapter):
    prefetchable = True

    async def search(
        self, sources: Sequence[TrustedSource], queries: Sequence[str], ctx: SearchContext
    ) -> list[EvidenceHit]:
        del queries
        return await search_entries("sitemap", sources, ctx, load_sitemap)

    async def prefetch(self, source: TrustedSource, ctx: SearchContext) -> None:
        await cached_entries("sitemap", source, ctx, load_sitemap)
