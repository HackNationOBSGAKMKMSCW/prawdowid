"""Polish legal acts (Dziennik Ustaw, Monitor Polski) by title, through Sejm's ELI API.

Uses ``apiReading.clients.sejm_eli``. A hit links to the act's HTML text when the API
has one (so the article scraper gets the wording), otherwise to its ISAP page.
"""

import asyncio
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from apiReading.clients.sejm_eli import SejmEliClient
from apiReading.exceptions import ApiReadingError

from ..models import EvidenceHit, TrustedSource
from . import SearchContext, SourceAdapter, register_adapter

MAX_QUERIES = 4
RESULTS_PER_QUERY = 3


def _date(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        moment = datetime.fromisoformat(value)
    except ValueError:
        return None
    return moment if moment.tzinfo else moment.replace(tzinfo=UTC)


@register_adapter("sejm_eli")
class SejmEliAdapter(SourceAdapter):
    server_ranked = True

    async def search(
        self, sources: Sequence[TrustedSource], queries: Sequence[str], ctx: SearchContext
    ) -> list[EvidenceHit]:
        if not sources:
            return []
        source = sources[0]  # one API; extra entries for it would only repeat the requests
        client = SejmEliClient(client=ctx.http, timeout=ctx.settings.source_timeout, max_retries=1)

        async def fetch(query: str) -> list[dict[str, Any]]:
            async def call() -> list[dict[str, Any]]:
                result = await client.fetch_data({"query": query, "page_size": RESULTS_PER_QUERY})
                return [item.payload for item in result.items]

            key = ("sejm_eli", query.lower(), RESULTS_PER_QUERY)
            return await ctx.cache.get_or_fetch(key, ctx.settings.query_cache_ttl, call)

        plan = [query[:300] for query in list(queries)[:MAX_QUERIES]]
        outcomes = await asyncio.gather(*(fetch(query) for query in plan), return_exceptions=True)

        hits: list[EvidenceHit] = []
        errors: list[BaseException] = []
        for query, outcome in zip(plan, outcomes, strict=True):
            if isinstance(outcome, BaseException):
                if not isinstance(outcome, ApiReadingError):
                    raise outcome
                errors.append(outcome)
                continue
            for payload in outcome:
                url = payload.get("url_text_html") or payload.get("url_isap")
                if not url or not payload.get("title"):
                    continue
                details = [payload.get("display_address"), payload.get("status")]
                hits.append(
                    EvidenceHit(
                        source_id=source.id,
                        source_name=source.name,
                        trust=source.trust,
                        url=url,
                        title=str(payload["title"]),
                        snippet=", ".join(str(item) for item in details if item),
                        published_at=_date(payload.get("promulgation_date")),
                        query=query,
                    )
                )
        if errors and len(errors) == len(plan):
            raise errors[0]
        return hits
