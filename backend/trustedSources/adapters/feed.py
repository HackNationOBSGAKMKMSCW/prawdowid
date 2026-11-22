"""RSS/Atom feeds: recent items with titles, summaries and dates."""

from collections.abc import Sequence

from apiReading.exceptions import ApiResponseError

from ..models import EvidenceHit, TrustedSource
from ..parsing import PageEntry, parse_feed
from . import SearchContext, SourceAdapter, register_adapter
from ._pages import XML_TYPES, cached_entries, search_entries

MAX_FEED_BYTES = 5 * 1024 * 1024


async def load_feed(source: TrustedSource, ctx: SearchContext) -> list[PageEntry]:
    feed_url = source.params.get("feed_url") or source.url
    page = await ctx.fetcher.get(
        feed_url,
        accept=(*XML_TYPES, "text/html"),
        accept_header="application/rss+xml, application/atom+xml, application/xml;q=0.9, */*;q=0.5",
        max_bytes=MAX_FEED_BYTES,
    )
    entries = parse_feed(page.body, page.final_url)
    if entries is None:
        raise ApiResponseError(source.id, "feed could not be parsed")
    return entries


@register_adapter("feed")
class FeedAdapter(SourceAdapter):
    prefetchable = True

    async def search(
        self, sources: Sequence[TrustedSource], queries: Sequence[str], ctx: SearchContext
    ) -> list[EvidenceHit]:
        del queries
        return await search_entries("feed", sources, ctx, load_feed)

    async def prefetch(self, source: TrustedSource, ctx: SearchContext) -> None:
        await cached_entries("feed", source, ctx, load_feed)
