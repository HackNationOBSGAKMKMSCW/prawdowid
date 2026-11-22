"""Local article extraction: fetch the page ourselves and parse it with trafilatura.

Because this extractor fetches user-supplied URLs directly, every redirect is
validated and DNS resolution is pinned to a public address before connecting
(see ``safe_http.SafeFetcher``).
"""

import asyncio
from datetime import UTC, datetime
from email.utils import format_datetime

import httpx
import trafilatura

from .diffbot import NotAnArticleError
from .protocols import RawArticle
from .safe_http import (
    DEFAULT_MAX_BYTES,
    MAX_REDIRECTS,
    Resolver,
    SafeFetcher,
    UnsupportedContentError,
    is_public_address,
    resolve_host,
)

SOURCE_NAME = "local_article"
MAX_RESPONSE_BYTES = DEFAULT_MAX_BYTES
MIN_ARTICLE_CHARS = 100
_ACCEPTED_TYPES = ("text/html", "application/xhtml+xml", "text/plain")

# Backwards-compatible aliases for callers that imported the old private helpers.
_resolve = resolve_host
_is_public = is_public_address

__all__ = ["MAX_REDIRECTS", "LocalArticleExtractor", "Resolver"]


class LocalArticleExtractor:
    """Implements ``ArticleExtractor`` without an external extraction service."""

    name = SOURCE_NAME

    def __init__(
        self,
        *,
        client: httpx.AsyncClient | None = None,
        timeout: float = 15.0,
        max_response_bytes: int = MAX_RESPONSE_BYTES,
        resolver: Resolver = resolve_host,
    ) -> None:
        self._fetcher = SafeFetcher(
            name=self.name,
            client=client,
            timeout=timeout,
            max_response_bytes=max_response_bytes,
            resolver=resolver,
        )

    async def aclose(self) -> None:
        """Close the HTTP client only when this extractor owns it."""

        await self._fetcher.aclose()

    async def extract(self, url: str) -> RawArticle:
        html, final_url = await self._fetch(url)
        return await asyncio.to_thread(self._parse, html, final_url)

    async def _fetch(self, url: str) -> tuple[bytes, str]:
        try:
            page = await self._fetcher.get(
                url,
                accept=_ACCEPTED_TYPES,
                accept_header="text/html,application/xhtml+xml",
            )
        except UnsupportedContentError as exc:
            raise NotAnArticleError(self.name, "page is not an HTML document") from exc
        return page.body, page.final_url

    def _parse(self, html: bytes, url: str) -> RawArticle:
        document = trafilatura.bare_extraction(
            html,
            url=url,
            with_metadata=True,
            include_comments=False,
            include_tables=False,
            favor_precision=True,
        )
        text = (getattr(document, "text", None) or "").strip()
        if len(text) < MIN_ARTICLE_CHARS:
            raise NotAnArticleError(self.name, "page did not contain an article")
        return RawArticle(
            text=text,
            title=getattr(document, "title", None),
            author=getattr(document, "author", None),
            date=_to_rfc1123(getattr(document, "date", None)),
        )


def _to_rfc1123(value: str | None) -> str | None:
    """Convert Trafilatura's ISO date to the format expected by ``map_article``."""

    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return format_datetime(parsed.astimezone(UTC), usegmt=True)
