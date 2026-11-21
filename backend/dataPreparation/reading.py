"""Read fact-check data for statements returned by the text analyzer."""

import asyncio
from collections.abc import Mapping

import httpx

from .apiReading import Category, ReadingRequest, ReadingResult, read
from .container import AnalysisDataContainer
from .settings import Settings


async def run_api_reading(
    analysis: AnalysisDataContainer,
    *,
    category: Category = Category.FACT_CHECK,
    language_code: str | None = None,
    page_size: int = 10,
    api_keys: Mapping[str, str] | None = None,
    http_client: httpx.AsyncClient | None = None,
) -> list[ReadingResult]:
    """Fetch one result per analyzed statement using the requested source category.

    The analyzer's topic category is preserved as metadata. ``category`` selects
    the kind of API source to query; it is not a filter supported by Google.
    """
    statements = [statement.strip() for statement in analysis.statements if statement.strip()]
    if not statements:
        raise ValueError("analysis must contain at least one statement to search")
    resolved_language_code = analysis.language_code if language_code is None else language_code

    settings = Settings.from_environment()
    keys = (
        api_keys
        if api_keys is not None
        else {"google_fact_check": settings.google_fact_check_api_key}
    )
    requests = [
        ReadingRequest(
            query=statement,
            categories=[category],
            language_code=resolved_language_code,
            page_size=page_size,
            metadata={"analysis_category": analysis.category},
        )
        for statement in statements
    ]

    async def fetch_with(client: httpx.AsyncClient) -> list[ReadingResult]:
        return list(
            await asyncio.gather(
                *(read(request, api_keys=keys, http_client=client) for request in requests)
            )
        )

    if http_client is not None:
        return await fetch_with(http_client)
    async with httpx.AsyncClient() as owned_client:
        return await fetch_with(owned_client)
