"""Fact-checker sites searched through Google Fact Check Tools, filtered to the publisher."""

import asyncio
from collections.abc import Sequence
from datetime import datetime
from typing import Any
from urllib.parse import urlsplit

from apiReading.clients import GoogleFactCheckClient
from apiReading.exceptions import ApiAuthError, ApiReadingError

from ..models import EvidenceHit, TrustedSource
from ..text import clean_snippet
from . import SearchContext, SourceAdapter, register_adapter

MAX_QUERIES = 3
PAGE_SIZE = 5

# Publishers indexed by Google Fact Check; detection maps these domains to this adapter.
KNOWN_PUBLISHERS = frozenset(
    {
        "demagog.org.pl",
        "konkret24.tvn24.pl",
        "sprawdzam.afp.com",
        "fakenews.pl",
    }
)


def _parse_date(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


@register_adapter("fact_check_publisher")
class FactCheckPublisherAdapter(SourceAdapter):
    server_ranked = True

    async def search(
        self,
        sources: Sequence[TrustedSource],
        queries: Sequence[str],
        ctx: SearchContext,
    ) -> list[EvidenceHit]:
        api_key = ctx.settings.google_fact_check_api_key
        if not api_key:
            raise ApiAuthError("google_fact_check", "API key is required", status_code=401)
        client = GoogleFactCheckClient(
            client=ctx.http, api_key=api_key, timeout=ctx.settings.source_timeout, max_retries=1
        )

        async def fetch(site: str, query: str) -> list[dict[str, Any]]:
            async def call() -> list[dict[str, Any]]:
                result = await client.fetch_data(
                    {"query": query, "review_publisher_site_filter": site, "page_size": PAGE_SIZE}
                )
                return [item.payload for item in result.items]

            key = ("fact_check", site, query.lower())
            return await ctx.cache.get_or_fetch(key, ctx.settings.query_cache_ttl, call)

        plan = [
            (source, query)
            for source in sources
            for query in list(queries)[:MAX_QUERIES]
            if source.params.get("site")
        ]
        outcomes = await asyncio.gather(
            *(fetch(source.params["site"], query) for source, query in plan),
            return_exceptions=True,
        )

        hits: list[EvidenceHit] = []
        errors: list[BaseException] = []
        for (source, query), outcome in zip(plan, outcomes, strict=True):
            if isinstance(outcome, BaseException):
                if not isinstance(outcome, ApiReadingError):
                    raise outcome
                errors.append(outcome)
                continue
            for claim in outcome:
                for review in claim.get("claimReview") or []:
                    url = review.get("url") if isinstance(review, dict) else None
                    if not isinstance(url, str) or not source.owns_url(urlsplit(url).hostname):
                        continue
                    rating = review.get("textualRating") or ""
                    claim_text = claim.get("text") or ""
                    hits.append(
                        EvidenceHit(
                            source_id=source.id,
                            source_name=source.name,
                            trust=source.trust,
                            url=url,
                            title=review.get("title") or claim_text or url,
                            snippet=clean_snippet(
                                f"{rating}: {claim_text}" if rating else claim_text
                            ),
                            published_at=_parse_date(review.get("reviewDate")),
                            query=query,
                        )
                    )
        if errors and len(errors) == len(plan):
            raise errors[0]
        return hits
