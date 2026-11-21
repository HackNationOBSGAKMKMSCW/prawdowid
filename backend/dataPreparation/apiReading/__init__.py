"""Async clients for fetching and normalizing data from external APIs."""

from .aggregator import fetch_all
from .base import BaseApiClient, RequestSpec
from .clients import GoogleFactCheckClient
from .exceptions import (
    ApiAuthError,
    ApiConnectionError,
    ApiHttpError,
    ApiRateLimitError,
    ApiReadingError,
    ApiResponseError,
    ApiTimeoutError,
    InvalidFiltersError,
    NoSourcesAvailableError,
)
from .models import Category, FetchOutcome, FetchResult, Item, ReadingRequest, ReadingResult
from .reader import read

__all__ = [
    "ApiAuthError",
    "ApiConnectionError",
    "ApiHttpError",
    "ApiRateLimitError",
    "ApiReadingError",
    "ApiResponseError",
    "ApiTimeoutError",
    "BaseApiClient",
    "Category",
    "FetchOutcome",
    "FetchResult",
    "GoogleFactCheckClient",
    "InvalidFiltersError",
    "Item",
    "NoSourcesAvailableError",
    "ReadingRequest",
    "ReadingResult",
    "RequestSpec",
    "fetch_all",
    "read",
]
