"""Concurrent multi-client fetch helper."""

import asyncio
from collections.abc import Mapping
from typing import Any

from .base import BaseApiClient
from .exceptions import ApiReadingError
from .models import FetchOutcome


async def fetch_all(
    requests: Mapping[BaseApiClient, dict[str, Any] | None],
    *,
    return_exceptions: bool = True,
) -> list[FetchOutcome]:
    """Fetch from each client concurrently, preserving mapping order.

    With ``return_exceptions=True``, each API failure is returned in its
    corresponding outcome. Otherwise the first failure is raised and normal
    ``asyncio.gather`` cancellation semantics apply.
    """

    clients = list(requests)
    filters = [requests[client] for client in clients]
    results = await asyncio.gather(
        *(
            client.fetch_data(client_filters)
            for client, client_filters in zip(clients, filters, strict=True)
        ),
        return_exceptions=return_exceptions,
    )

    outcomes: list[FetchOutcome] = []
    for client, result in zip(clients, results, strict=True):
        if isinstance(result, asyncio.CancelledError):
            raise result
        if isinstance(result, ApiReadingError):
            outcomes.append(FetchOutcome(source=client.name, error=result))
        elif isinstance(result, BaseException):
            raise result
        else:
            outcomes.append(FetchOutcome(source=client.name, result=result))
    return outcomes
