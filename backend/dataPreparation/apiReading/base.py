"""Shared HTTP and lifecycle behavior for external API clients."""

import asyncio
import logging
import random
from abc import ABC, abstractmethod
from collections.abc import Mapping
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any, ClassVar
from urllib.parse import urlparse

import httpx
from pydantic import ValidationError

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
from .models import Category, FetchResult, ReadingRequest

logger = logging.getLogger(__name__)
_RETRYABLE_STATUSES = {502, 503, 504}


class RequestSpec:
    """HTTP request details produced by an API-specific client."""

    def __init__(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, Any] | None = None,
        json: Any = None,
        headers: Mapping[str, str] | None = None,
    ) -> None:
        self.method = method.upper()
        self.path = path
        self.params = dict(params) if params is not None else None
        self.json = json
        self.headers = dict(headers) if headers is not None else None


class BaseApiClient(ABC):
    """Template client that owns shared HTTP, retries, and error mapping."""

    name: ClassVar[str]
    base_url: ClassVar[str]
    supported_categories: ClassVar[frozenset[Category]]

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        if (
            not cls.__dict__.get("name")
            or not cls.__dict__.get("base_url")
            or not cls.__dict__.get("supported_categories")
            or not isinstance(cls.__dict__.get("supported_categories"), frozenset)
        ):
            raise TypeError(
                "API clients must define 'name', 'base_url', and non-empty frozenset "
                "'supported_categories'"
            )

        if not all(isinstance(category, Category) for category in cls.supported_categories):
            raise TypeError("API client supported_categories must contain Category values")

        parsed_url = urlparse(cls.base_url)
        if parsed_url.scheme != "https" or not parsed_url.netloc:
            raise TypeError("API client base_url must be an absolute HTTPS URL")

    def __init__(
        self,
        *,
        client: httpx.AsyncClient | None = None,
        api_key: str | None = None,
        timeout: float = 10.0,
        max_retries: int = 2,
        limits: httpx.Limits | None = None,
        max_concurrency: int | None = None,
        retry_backoff: float = 0.25,
    ) -> None:
        if timeout <= 0:
            raise ValueError("timeout must be greater than zero")
        if max_retries < 0:
            raise ValueError("max_retries cannot be negative")
        if retry_backoff < 0:
            raise ValueError("retry_backoff cannot be negative")
        if max_concurrency is not None and max_concurrency < 1:
            raise ValueError("max_concurrency must be at least one")

        self.api_key = api_key
        self.timeout = timeout
        self._http_timeout = httpx.Timeout(timeout, connect=min(5.0, timeout))
        self.max_retries = max_retries
        self.retry_backoff = retry_backoff
        self._limits = limits or httpx.Limits()
        self._semaphore = asyncio.Semaphore(max_concurrency) if max_concurrency else None
        self._client = client
        self._owns_client = client is None

    async def __aenter__(self) -> "BaseApiClient":
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        """Close the HTTP client only when this instance created it."""

        if self._owns_client and self._client is not None:
            await self._client.aclose()
            self._client = None

    async def fetch_data(self, filters: dict[str, Any] | None = None) -> FetchResult:
        """Fetch and normalize one page of data from this API."""

        try:
            spec = self.build_request(filters or {})
        except InvalidFiltersError:
            raise
        except (ValidationError, ValueError, TypeError) as exc:
            raise InvalidFiltersError(self.name, "invalid filters", cause=exc) from exc

        response = await self._request(spec)
        try:
            return self.parse_response(response)
        except ApiReadingError:
            raise
        except httpx.HTTPError as exc:
            raise ApiResponseError(self.name, "could not decode response", cause=exc) from exc
        except (ValidationError, ValueError, TypeError, KeyError) as exc:
            raise ApiResponseError(self.name, "invalid response payload", cause=exc) from exc

    @abstractmethod
    def build_request(self, filters: dict[str, Any]) -> RequestSpec:
        """Validate filters and map them to one HTTP request."""

    @abstractmethod
    def filters_from_request(self, request: ReadingRequest) -> dict[str, Any]:
        """Map a shared read request to this API's filter vocabulary."""

    @abstractmethod
    def parse_response(self, response: httpx.Response) -> FetchResult:
        """Convert a successful API response to the shared result model."""

    async def _request(self, spec: RequestSpec) -> httpx.Response:
        client = self._get_client()
        retryable = spec.method == "GET"
        attempt = 0

        while True:
            try:
                if self._semaphore is None:
                    response = await self._send(client, spec)
                else:
                    async with self._semaphore:
                        response = await self._send(client, spec)
            except httpx.TimeoutException as exc:
                if retryable and attempt < self.max_retries:
                    await self._sleep_before_retry(attempt)
                    attempt += 1
                    continue
                logger.warning("API request timed out: source=%s", self.name)
                raise ApiTimeoutError(self.name, "request timed out", cause=exc) from exc
            except httpx.TransportError as exc:
                if retryable and attempt < self.max_retries:
                    await self._sleep_before_retry(attempt)
                    attempt += 1
                    continue
                logger.warning("API connection failed: source=%s", self.name)
                raise ApiConnectionError(self.name, "request failed", cause=exc) from exc
            except httpx.InvalidURL as exc:
                raise ApiConnectionError(self.name, "invalid request URL", cause=exc) from exc
            except httpx.HTTPError as exc:
                raise ApiConnectionError(self.name, "request failed", cause=exc) from exc

            status = response.status_code
            if status == 429:
                retry_after = _parse_retry_after(response.headers.get("Retry-After"))
                if retryable and attempt < self.max_retries:
                    await self._sleep_before_retry(attempt, retry_after)
                    attempt += 1
                    continue
                raise ApiRateLimitError(
                    self.name,
                    "API rate limit exceeded",
                    retry_after=retry_after,
                )
            if status in _RETRYABLE_STATUSES and retryable and attempt < self.max_retries:
                await self._sleep_before_retry(attempt)
                attempt += 1
                continue
            if status in (401, 403):
                raise ApiAuthError(
                    self.name,
                    "API rejected authentication",
                    status_code=status,
                )
            if status < 200 or status >= 300:
                raise ApiHttpError(
                    self.name,
                    "API returned an unsuccessful status",
                    status_code=status,
                )
            return response

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=self._http_timeout,
                limits=self._limits,
            )
        return self._client

    async def _send(self, client: httpx.AsyncClient, spec: RequestSpec) -> httpx.Response:
        return await client.request(
            spec.method,
            f"{self.base_url.rstrip('/')}/{spec.path.lstrip('/')}",
            params=spec.params,
            json=spec.json,
            headers=spec.headers,
            timeout=self._http_timeout,
        )

    async def _sleep_before_retry(self, attempt: int, retry_after: float | None = None) -> None:
        if retry_after is not None:
            delay = min(retry_after, 60.0)
        else:
            delay = min(self.retry_backoff * (2**attempt), 30.0)
            delay += random.uniform(0, delay * 0.1)
        await asyncio.sleep(delay)


def _parse_retry_after(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        return max(0.0, float(value))
    except ValueError:
        try:
            retry_at = parsedate_to_datetime(value)
            if retry_at.tzinfo is None:
                retry_at = retry_at.replace(tzinfo=UTC)
            return max(0.0, (retry_at - datetime.now(UTC)).total_seconds())
        except (TypeError, ValueError, OverflowError):
            return None
