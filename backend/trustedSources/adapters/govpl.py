"""gov.pl portal search (``/api/data/search``), scoped per subsite (``/web/<site_id>``)."""

import asyncio
import re
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any, ClassVar
from urllib.parse import urljoin, urlsplit

import httpx
from apiReading.base import BaseApiClient, RequestSpec
from apiReading.exceptions import ApiReadingError, ApiResponseError, InvalidFiltersError
from apiReading.models import Category, FetchResult, Item, ReadingRequest

from ..models import EvidenceHit, TrustedSource
from ..text import clean_snippet
from . import SearchContext, SourceAdapter, register_adapter

GOVPL_HOST = "www.gov.pl"
_SITE_ID = re.compile(r"^[a-z0-9][a-z0-9-]{0,99}$")
_DICTIONARY_TTL = 24 * 3600
MAX_QUERIES = 2
PAGE_SIZE = 8


class GovPlSearchClient(BaseApiClient):
    """Public JSON search used by the gov.pl site itself (no key required)."""

    name = "gov_pl"
    base_url = "https://www.gov.pl"
    supported_categories: ClassVar[frozenset[Category]] = frozenset({Category.OFFICIAL})
    requires_api_key: ClassVar[bool] = False

    def filters_from_request(self, request: ReadingRequest) -> dict[str, Any]:
        return {"query": request.query, "size": min(request.page_size, 50)}

    def build_request(self, filters: dict[str, Any]) -> RequestSpec:
        if set(filters) - {"query", "size", "page", "site_id"}:
            raise InvalidFiltersError(self.name, "unsupported filter")
        query = filters.get("query")
        if not isinstance(query, str) or not query.strip():
            raise InvalidFiltersError(self.name, "query is required")
        size = filters.get("size", 10)
        if not isinstance(size, int) or isinstance(size, bool) or not 1 <= size <= 50:
            raise InvalidFiltersError(self.name, "size must be an integer from 1 to 50")
        params: dict[str, Any] = {"query": query.strip()[:200], "size": size}
        page = filters.get("page")
        if page is not None:
            if not isinstance(page, int) or isinstance(page, bool) or page < 1:
                raise InvalidFiltersError(self.name, "page must be a positive integer")
            params["page"] = page
        site_id = filters.get("site_id")
        if site_id is not None:
            if not isinstance(site_id, str) or not _SITE_ID.match(site_id):
                raise InvalidFiltersError(self.name, "invalid site_id")
            params["ministryId"] = site_id
        return RequestSpec("GET", "/api/data/search", params=params)

    def parse_response(self, response: httpx.Response) -> FetchResult:
        payload = response.json()
        if not isinstance(payload, dict) or not isinstance(payload.get("results", []), list):
            raise ApiResponseError(self.name, "expected a search response object")
        items: list[Item] = []
        for result in payload.get("results") or []:
            if not isinstance(result, dict) or not isinstance(result.get("url"), str):
                continue
            url = urljoin(f"{self.base_url}/", result["url"])
            items.append(
                Item(
                    id=url,
                    source=self.name,
                    payload={
                        "url": url,
                        "title": result.get("title") or "",
                        "intro": result.get("intro") or "",
                        "publishDate": result.get("publishDate"),
                        "path": result.get("path"),
                    },
                )
            )
        total = payload.get("count")
        return FetchResult(
            source=self.name,
            items=items,
            fetched_at=datetime.now(UTC),
            total=total if isinstance(total, int) else None,
        )

    async def site_dictionary(self) -> dict[str, str]:
        """Map of every gov.pl subsite id to its institution name."""

        response = await self._request(RequestSpec("GET", "/api/data/indexdictionary"))
        try:
            payload = response.json()
        except ValueError as exc:
            raise ApiResponseError(self.name, "could not decode dictionary", cause=exc) from exc
        sites = payload.get("ministryId") if isinstance(payload, dict) else None
        if not isinstance(sites, dict):
            raise ApiResponseError(self.name, "expected a ministryId dictionary")
        return {str(key): str(value) for key, value in sites.items()}


def site_id_from_url(url: str) -> str | None:
    """``https://www.gov.pl/web/rcb/raport-dobowy3`` -> ``rcb``; ``https://www.gov.pl/`` -> ``None``."""

    parts = urlsplit(url)
    if (parts.hostname or "").lower() not in {GOVPL_HOST, "gov.pl"}:
        return None
    segments = [segment for segment in parts.path.split("/") if segment]
    if len(segments) >= 2 and segments[0] == "web" and _SITE_ID.match(segments[1].lower()):
        return segments[1].lower()
    return None


def is_govpl_url(url: str) -> bool:
    return (urlsplit(url).hostname or "").lower() in {GOVPL_HOST, "gov.pl"}


async def site_dictionary(ctx: SearchContext) -> dict[str, str]:
    async def fetch() -> dict[str, str]:
        client = GovPlSearchClient(client=ctx.http, timeout=ctx.settings.source_timeout)
        return await client.site_dictionary()

    return await ctx.cache.get_or_fetch(("govpl", "dictionary"), _DICTIONARY_TTL, fetch)


def _parse_date(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


@register_adapter("govpl_search")
class GovPlSearchAdapter(SourceAdapter):
    """One request per (query, whitelisted subsite); never a portal-wide search.

    Results are kept only when they lie inside the queried subsite
    (``/web/<site_id>/…``). Sources without a ``site_id`` (the bare portal URL)
    are ignored: the whitelist names subsites, not the whole of gov.pl.
    """

    async def search(
        self,
        sources: Sequence[TrustedSource],
        queries: Sequence[str],
        ctx: SearchContext,
    ) -> list[EvidenceHit]:
        by_site: dict[str, TrustedSource] = {}
        for source in sources:
            site_id = source.params.get("site_id")
            if site_id:
                by_site.setdefault(site_id, source)
        if not by_site:
            return []
        client = GovPlSearchClient(
            client=ctx.http, timeout=ctx.settings.source_timeout, max_retries=1
        )
        limiter = asyncio.Semaphore(ctx.settings.max_concurrency)

        async def fetch(query: str, site_id: str) -> list[dict[str, Any]]:
            filters: dict[str, Any] = {"query": query, "size": PAGE_SIZE, "site_id": site_id}

            async def call() -> list[dict[str, Any]]:
                async with limiter:
                    result = await client.fetch_data(filters)
                return [item.payload for item in result.items]

            key = ("govpl", query.lower(), site_id, PAGE_SIZE)
            return await ctx.cache.get_or_fetch(key, ctx.settings.query_cache_ttl, call)

        plan = [(query, site_id) for query in list(queries)[:MAX_QUERIES] for site_id in by_site]
        outcomes = await asyncio.gather(
            *(fetch(query, site_id) for query, site_id in plan), return_exceptions=True
        )

        hits: list[EvidenceHit] = []
        errors: list[BaseException] = []
        for (query, site_id), outcome in zip(plan, outcomes, strict=True):
            if isinstance(outcome, BaseException):
                if not isinstance(outcome, ApiReadingError):
                    raise outcome
                errors.append(outcome)
                continue
            source = by_site[site_id]
            for payload in outcome:
                if site_id_from_url(payload["url"]) != site_id:
                    continue  # outside the whitelisted subsite
                hits.append(
                    EvidenceHit(
                        source_id=source.id,
                        source_name=source.name,
                        trust=source.trust,
                        url=payload["url"],
                        title=payload.get("title") or "",
                        snippet=clean_snippet(payload.get("intro")),
                        published_at=_parse_date(payload.get("publishDate")),
                        query=query,
                    )
                )
        if errors and len(errors) == len(plan):
            raise errors[0]
        return hits
