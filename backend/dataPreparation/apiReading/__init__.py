"""Async clients for fetching and normalizing data from external APIs."""

from .aggregator import fetch_all
from .base import BaseApiClient, RequestSpec
from .clients import ExampleAClient, ExampleBClient
from .exceptions import (
    ApiAuthError,
    ApiConnectionError,
    ApiHttpError,
    ApiRateLimitError,
    ApiReadingError,
    ApiResponseError,
    ApiTimeoutError,
    InvalidFiltersError,
)
from .models import FetchOutcome, FetchResult, Item

__all__ = [
    "ApiAuthError",
    "ApiConnectionError",
    "ApiHttpError",
    "ApiRateLimitError",
    "ApiReadingError",
    "ApiResponseError",
    "ApiTimeoutError",
    "BaseApiClient",
    "ExampleAClient",
    "ExampleBClient",
    "FetchOutcome",
    "FetchResult",
    "InvalidFiltersError",
    "Item",
    "RequestSpec",
    "fetch_all",
]
