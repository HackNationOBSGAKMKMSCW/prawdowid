"""Category-driven asynchronous reader entry point."""

import time
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

import httpx
from pydantic import ValidationError

from .aggregator import fetch_all
from .base import BaseApiClient
from .exceptions import ApiAuthError, ApiReadingError, InvalidFiltersError, NoSourcesAvailableError
from .models import FetchOutcome, ReadingRequest, ReadingResult
from .registry import clients_for_categories


async def read(
    request: ReadingRequest,
    *,
    api_keys: Mapping[str, str] | None = None,
    http_client: httpx.AsyncClient | None = None,
) -> ReadingResult:
    """Fetch from all registered APIs matching ``request.categories``.

    API keys are supplied by the caller and keyed by client name. A client
    without a configured key contributes an authentication error outcome while
    other selected clients continue normally.
    """

    started_at = time.perf_counter()
    try:
        validated_request = ReadingRequest.model_validate(request)
    except (ValidationError, TypeError, ValueError) as exc:
        raise InvalidFiltersError("reader", "invalid reading request", cause=exc) from exc

    client_classes, categories_without_source = clients_for_categories(validated_request.categories)
    if not client_classes:
        raise NoSourcesAvailableError(
            "reader", "no API sources are registered for these categories"
        )

    keys = api_keys or {}
    outcomes_by_class: dict[type[BaseApiClient], FetchOutcome] = {}
    configured_classes: list[type[BaseApiClient]] = []
    for client_class in client_classes:
        api_key = keys.get(client_class.name)
        if not isinstance(api_key, str) or not api_key.strip():
            outcomes_by_class[client_class] = FetchOutcome(
                source=client_class.name,
                error=ApiAuthError(
                    client_class.name,
                    "API key is required",
                    status_code=401,
                ),
            )
        else:
            configured_classes.append(client_class)

    async def fetch_with(shared_client: httpx.AsyncClient) -> None:
        requests: dict[BaseApiClient, dict[str, Any]] = {}
        for client_class in configured_classes:
            client = client_class(
                client=shared_client,
                api_key=keys[client_class.name],
            )
            try:
                client_filters = client.filters_from_request(validated_request)
            except ApiReadingError as exc:
                outcomes_by_class[client_class] = FetchOutcome(
                    source=client_class.name,
                    error=exc,
                )
            except (ValidationError, TypeError, ValueError) as exc:
                error = InvalidFiltersError(
                    client_class.name,
                    "could not map reading request to API filters",
                    cause=exc,
                )
                outcomes_by_class[client_class] = FetchOutcome(
                    source=client_class.name,
                    error=error,
                )
            else:
                requests[client] = client_filters

        fetched_outcomes = await fetch_all(requests)
        for client, outcome in zip(requests, fetched_outcomes, strict=True):
            outcomes_by_class[type(client)] = outcome

    if configured_classes:
        if http_client is None:
            async with httpx.AsyncClient() as owned_client:
                await fetch_with(owned_client)
        else:
            await fetch_with(http_client)

    outcomes = [outcomes_by_class[client_class] for client_class in client_classes]
    items = [
        item for outcome in outcomes if outcome.result is not None for item in outcome.result.items
    ]
    return ReadingResult(
        request=validated_request,
        results=outcomes,
        items=items,
        categories_without_source=categories_without_source,
        fetched_at=datetime.now(UTC),
        duration_ms=round((time.perf_counter() - started_at) * 1000),
    )
