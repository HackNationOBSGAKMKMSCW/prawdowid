"""Decide how to search a newly whitelisted URL.

Order: gov.pl subsite → known fact-check publisher → RSS/Atom feed (advertised
by the page or at a common path) → listing page with article links →
sitemap (robots.txt or common paths) → reference (dashboard/app, link only).
All page downloads go through ``SafeFetcher``.
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urljoin, urlsplit

from apiReading.exceptions import ApiReadingError

from .adapters import SearchContext
from .adapters._pages import HTML_TYPES, XML_TYPES
from .adapters.govpl import site_dictionary
from .models import PENDING_ADAPTER, LastCheck, TrustedSource
from .parsing import parse_feed, parse_html, parse_sitemap
from .registry import static_classification

logger = logging.getLogger(__name__)

MIN_FEED_ITEMS = 3
MIN_LISTING_LINKS = 5
MIN_SITEMAP_URLS = 10
_FEED_PATHS = ("/feed/", "/rss.xml", "/rss", "/feed.xml", "/atom.xml")
_SITEMAP_PATHS = ("/sitemap.xml", "/sitemap_index.xml", "/wp-sitemap.xml")


@dataclass
class Detection:
    adapter: str
    params: dict[str, Any] = field(default_factory=dict)
    name: str | None = None
    description: str = ""
    detail: str = ""


async def _try_feed(url: str, ctx: SearchContext) -> bool:
    try:
        page = await ctx.fetcher.get(url, accept=(*XML_TYPES, "text/html"), max_bytes=5_000_000)
    except ApiReadingError:
        return False
    entries = parse_feed(page.body, page.final_url)
    return entries is not None and len(entries) >= MIN_FEED_ITEMS


async def _try_sitemap(url: str, ctx: SearchContext) -> bool:
    try:
        page = await ctx.fetcher.get(url, accept=XML_TYPES, max_bytes=10_000_000)
    except ApiReadingError:
        return False
    document = parse_sitemap(page.body)
    return document is not None and (document.is_index or len(document.entries) >= MIN_SITEMAP_URLS)


async def _robots_sitemaps(origin: str, ctx: SearchContext) -> list[str]:
    try:
        page = await ctx.fetcher.get(urljoin(origin, "/robots.txt"), max_bytes=500_000)
    except ApiReadingError:
        return []
    host = urlsplit(origin).hostname
    found = []
    for line in page.body.decode("utf-8", "replace").splitlines():
        if line.lower().startswith("sitemap:"):
            candidate = line.split(":", 1)[1].strip()
            if urlsplit(candidate).hostname == host:
                found.append(candidate)
    return found[:3]


async def detect(source: TrustedSource, ctx: SearchContext) -> Detection:
    adapter, params, _, _, _ = static_classification(source.url)
    if adapter == "govpl_search":
        site_id = params.get("site_id")
        name = None
        if site_id:
            try:
                name = (await site_dictionary(ctx)).get(site_id)
            except ApiReadingError:
                logger.warning("gov.pl site dictionary unavailable")
            if name is None:
                return Detection(adapter, params, detail=f"site '{site_id}' not confirmed")
        return Detection(adapter, params, name=name, detail="gov.pl search")
    if adapter != PENDING_ADAPTER:
        return Detection(adapter, params, detail="known publisher")

    page = await ctx.fetcher.get(source.url, accept=HTML_TYPES, accept_header="text/html")
    parsed = await asyncio.to_thread(
        parse_html, page.body, page.final_url, path_prefix=source.path_prefix
    )
    origin = f"{urlsplit(page.final_url).scheme}://{urlsplit(page.final_url).netloc}"
    meta = {"name": parsed.title or None, "description": parsed.description}

    same_host = [
        feed for feed in parsed.feed_urls if urlsplit(feed).hostname == urlsplit(origin).hostname
    ]
    for feed_url in [*same_host[:2], *(urljoin(origin, path) for path in _FEED_PATHS)]:
        if await _try_feed(feed_url, ctx):
            return Detection("feed", {"feed_url": feed_url}, detail=f"feed {feed_url}", **meta)

    if len(parsed.links) >= MIN_LISTING_LINKS:
        return Detection(
            "listing",
            {"listing_url": page.final_url},
            detail=f"{len(parsed.links)} article links",
            **meta,
        )

    candidates = await _robots_sitemaps(origin, ctx)
    candidates += [urljoin(origin, path) for path in _SITEMAP_PATHS if urljoin(origin, path) not in candidates]
    for sitemap_url in candidates:
        if await _try_sitemap(sitemap_url, ctx):
            return Detection("sitemap", {"sitemap_url": sitemap_url}, detail=f"sitemap {sitemap_url}", **meta)

    return Detection("reference", {}, detail="no searchable content (dashboard or app)", **meta)


async def detect_and_update(source: TrustedSource, ctx: SearchContext) -> TrustedSource:
    """Run detection and return the updated source (never raises for network errors)."""

    now = datetime.now(UTC)
    if source.adapter_locked:
        return source.model_copy(
            update={"last_check": LastCheck(at=now, ok=True, detail="adapter set manually")}
        )
    try:
        result = await detect(source, ctx)
    except ApiReadingError as exc:
        kind = type(exc).__name__
        status = f" {exc.status_code}" if exc.status_code else ""
        return source.model_copy(
            update={"last_check": LastCheck(at=now, ok=False, error=f"{kind}{status}")}
        )
    except Exception as exc:  # noqa: BLE001 - one broken page must not stop bulk checks
        logger.warning("detection failed for %s: %s", source.id, type(exc).__name__)
        return source.model_copy(
            update={"last_check": LastCheck(at=now, ok=False, error=type(exc).__name__)}
        )
    default_name = urlsplit(source.url).hostname
    update: dict[str, Any] = {
        "adapter": result.adapter,
        "params": result.params,
        "last_check": LastCheck(at=now, ok=True, detail=result.detail),
    }
    if result.name and source.name == default_name:
        update["name"] = result.name
    if result.description and not source.description:
        update["description"] = result.description
    return source.model_copy(update=update)
