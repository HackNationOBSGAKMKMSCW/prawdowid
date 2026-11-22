"""Listing pages (``/aktualnosci``, ``/komunikaty``): article links with their titles."""

import asyncio
from collections.abc import Sequence

from ..models import EvidenceHit, TrustedSource
from ..parsing import PageEntry, parse_html
from . import SearchContext, SourceAdapter, register_adapter
from ._pages import HTML_TYPES, cached_entries, search_entries


async def load_listing(source: TrustedSource, ctx: SearchContext) -> list[PageEntry]:
    page = await ctx.fetcher.get(
        source.params.get("listing_url") or source.url,
        accept=HTML_TYPES,
        accept_header="text/html,application/xhtml+xml",
    )
    parsed = await asyncio.to_thread(
        parse_html, page.body, page.final_url, path_prefix=source.path_prefix
    )
    return parsed.links


@register_adapter("listing")
class ListingAdapter(SourceAdapter):
    prefetchable = True

    async def search(
        self, sources: Sequence[TrustedSource], queries: Sequence[str], ctx: SearchContext
    ) -> list[EvidenceHit]:
        del queries
        return await search_entries("listing", sources, ctx, load_listing)

    async def prefetch(self, source: TrustedSource, ctx: SearchContext) -> None:
        await cached_entries("listing", source, ctx, load_listing)
