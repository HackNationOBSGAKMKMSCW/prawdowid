"""Wikipedia articles found by the MediaWiki search API (``/w/api.php?list=search``).

Encyclopaedic context for general facts (geography, history, institutions) that the
official sites never state outright. The source's trust is ``other``, not ``official``.
"""

import asyncio
import re
from collections.abc import Sequence
from typing import Any
from urllib.parse import quote

import httpx
from apiReading.exceptions import ApiConnectionError, ApiReadingError, ApiResponseError, ApiTimeoutError

from ..models import EvidenceHit, TrustedSource
from ..text import clean_snippet
from . import SearchContext, SourceAdapter, register_adapter

MAX_QUERIES = 4
RESULTS_PER_QUERY = 3
_LANG = re.compile(r"^[a-z]{2,3}$")


def wiki_language(source: TrustedSource) -> str:
    """``params.lang`` or the subdomain of ``pl.wikipedia.org``; ``pl`` by default."""

    lang = str(source.params.get("lang") or "").strip().lower()
    if not lang:
        host = source.domains[0] if source.domains else ""
        lang = host.split(".", 1)[0] if host.endswith("wikipedia.org") else ""
    return lang if _LANG.match(lang) else "pl"


def article_url(lang: str, title: str) -> str:
    return f"https://{lang}.wikipedia.org/wiki/{quote(title.replace(' ', '_'), safe='_()')}"


@register_adapter("wikipedia")
class WikipediaAdapter(SourceAdapter):
    server_ranked = True

    async def search(
        self, sources: Sequence[TrustedSource], queries: Sequence[str], ctx: SearchContext
    ) -> list[EvidenceHit]:
        by_lang: dict[str, TrustedSource] = {}
        for source in sources:
            by_lang.setdefault(wiki_language(source), source)
        if not by_lang:
            return []

        async def fetch(lang: str, query: str) -> list[dict[str, Any]]:
            async def call() -> list[dict[str, Any]]:
                try:
                    response = await ctx.http.get(
                        f"https://{lang}.wikipedia.org/w/api.php",
                        params={
                            "action": "query",
                            "list": "search",
                            "srsearch": query[:200],
                            "srlimit": RESULTS_PER_QUERY,
                            "srprop": "snippet",
                            "format": "json",
                            "utf8": 1,
                        },
                        timeout=ctx.settings.source_timeout,
                    )
                except httpx.TimeoutException as exc:
                    raise ApiTimeoutError("wikipedia", "timeout", cause=exc) from None
                except httpx.HTTPError as exc:
                    raise ApiConnectionError("wikipedia", type(exc).__name__, cause=exc) from None
                if response.status_code != 200:
                    raise ApiResponseError(
                        "wikipedia", "unexpected status", status_code=response.status_code
                    )
                try:
                    results = response.json()["query"]["search"]
                except (ValueError, KeyError, TypeError):
                    raise ApiResponseError("wikipedia", "unexpected response") from None
                return [item for item in results if isinstance(item, dict) and item.get("title")]

            key = ("wikipedia", lang, query.lower(), RESULTS_PER_QUERY)
            return await ctx.cache.get_or_fetch(key, ctx.settings.query_cache_ttl, call)

        plan = [(lang, query) for query in list(queries)[:MAX_QUERIES] for lang in by_lang]
        outcomes = await asyncio.gather(*(fetch(*step) for step in plan), return_exceptions=True)

        hits: list[EvidenceHit] = []
        errors: list[BaseException] = []
        for (lang, query), outcome in zip(plan, outcomes, strict=True):
            if isinstance(outcome, BaseException):
                if not isinstance(outcome, ApiReadingError):
                    raise outcome
                errors.append(outcome)
                continue
            source = by_lang[lang]
            for item in outcome:
                title = str(item["title"])
                hits.append(
                    EvidenceHit(
                        source_id=source.id,
                        source_name=source.name,
                        trust=source.trust,
                        url=article_url(lang, title),
                        title=title,
                        snippet=clean_snippet(item.get("snippet")),
                        query=query,
                    )
                )
        if errors and len(errors) == len(plan):
            raise errors[0]
        return hits
