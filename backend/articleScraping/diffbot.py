"""Diffbot Article API adapter with response and credential-leak boundaries."""

import logging
from datetime import UTC, datetime
from typing import Any, ClassVar

import httpx
from apiReading.base import BaseApiClient, RequestSpec
from apiReading.exceptions import (
    ApiAuthError,
    ApiConnectionError,
    ApiHttpError,
    ApiRateLimitError,
    ApiReadingError,
    ApiResponseError,
    ApiTimeoutError,
)
from apiReading.models import Category, FetchResult, Item, ReadingRequest

from .protocols import RawArticle

logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

DIFFBOT_URL = "https://api.diffbot.com/v3/article"
MAX_RESPONSE_BYTES = 2 * 1024 * 1024
_ALLOWED_FIELDS = (
    "title",
    "text",
    "author",
    "date",
    "siteName",
    "pageUrl",
    "resolvedPageUrl",
    "humanLanguage",
)


class NotAnArticleError(ApiResponseError):
    """Diffbot did not identify a non-empty article body."""


class DiffbotArticleClient(BaseApiClient):
    """Extract article text without retaining HTML or leaking the query token."""

    name = "diffbot_article"
    base_url = "https://api.diffbot.com"
    supported_categories: ClassVar[frozenset[Category]] = frozenset({Category.ARTICLE_EXTRACT})

    def __init__(self, *, max_response_bytes: int = MAX_RESPONSE_BYTES, **kwargs: Any) -> None:
        kwargs.setdefault("max_retries", 1)
        kwargs.setdefault("max_concurrency", 1)
        kwargs.setdefault("timeout", 30.0)
        if max_response_bytes < 1:
            raise ValueError("max_response_bytes must be positive")
        self.max_response_bytes = max_response_bytes
        super().__init__(**kwargs)

    def __repr__(self) -> str:
        key_state = "[redacted]" if self.api_key else None
        return f"DiffbotArticleClient(api_key={key_state!r})"

    def filters_from_request(self, request: ReadingRequest) -> dict[str, Any]:
        raise NotImplementedError("Diffbot article extraction is not a category search")

    def build_request(self, filters: dict[str, Any]) -> RequestSpec:
        url = filters.get("url")
        if not isinstance(url, str) or not url:
            raise ValueError("a non-empty article URL is required")
        if not self.api_key:
            raise ApiAuthError(self.name, "Diffbot API token is not configured")
        return RequestSpec(
            "GET",
            "/v3/article",
            params={
                "token": self.api_key,
                "url": url,
                "discussion": "false",
                "timeout": max(1, int(self.timeout * 1000) - 1000),
            },
        )

    async def _send(self, client: httpx.AsyncClient, spec: RequestSpec) -> httpx.Response:
        url = f"{self.base_url.rstrip('/')}/{spec.path.lstrip('/')}"
        chunks: list[bytes] = []
        total = 0
        async with client.stream(
            spec.method,
            url,
            params=spec.params,
            json=spec.json,
            headers=spec.headers,
            timeout=self._http_timeout,
            follow_redirects=False,
        ) as response:
            async for chunk in response.aiter_bytes(chunk_size=64 * 1024):
                total += len(chunk)
                if total > self.max_response_bytes:
                    raise ApiResponseError(self.name, "response exceeded the size limit")
                chunks.append(chunk)
            return httpx.Response(
                status_code=response.status_code,
                headers=response.headers,
                content=b"".join(chunks),
                request=response.request,
                extensions=response.extensions,
            )

    def parse_response(self, response: httpx.Response) -> FetchResult:
        payload = response.json()
        if not isinstance(payload, dict):
            raise ApiResponseError(self.name, "expected an article response object")
        if "error" in payload or "errorCode" in payload or "code" in payload:
            error_code = payload.get("errorCode", payload.get("code"))
            if error_code in {401, 403, "401", "403"}:
                raise ApiAuthError(
                    self.name,
                    "Diffbot rejected authentication",
                    status_code=int(error_code),
                )
            if error_code == 429 or error_code == "429":
                raise ApiRateLimitError(self.name, "Diffbot rate limit exceeded")
            raise ApiResponseError(self.name, "Diffbot could not extract the article")

        objects = payload.get("objects")
        if not isinstance(objects, list) or not objects or not isinstance(objects[0], dict):
            raise ApiResponseError(self.name, "Diffbot returned no article object")
        item = objects[0]
        if (
            item.get("type") != "article"
            or not isinstance(item.get("text"), str)
            or not item["text"].strip()
        ):
            raise NotAnArticleError(self.name, "page did not contain an article")
        whitelisted = {
            field: item[field] for field in _ALLOWED_FIELDS if isinstance(item.get(field), str)
        }
        return FetchResult(
            source=self.name,
            items=[Item(id="article", source=self.name, payload=whitelisted)],
            fetched_at=datetime.now(UTC),
        )

    async def fetch_data(self, filters: dict[str, Any] | None = None) -> FetchResult:
        try:
            return await super().fetch_data(filters)
        except ApiReadingError as exc:
            if isinstance(exc, ApiRateLimitError):
                safe_error = ApiRateLimitError(
                    self.name, "Diffbot rate limit exceeded", retry_after=exc.retry_after
                )
            elif isinstance(exc, ApiAuthError):
                safe_error = ApiAuthError(
                    self.name, "Diffbot rejected authentication", status_code=exc.status_code
                )
            elif isinstance(exc, ApiTimeoutError):
                safe_error = ApiTimeoutError(
                    self.name, "Diffbot request timed out", status_code=exc.status_code
                )
            elif isinstance(exc, ApiConnectionError):
                safe_error = ApiConnectionError(
                    self.name, "Diffbot connection failed", status_code=exc.status_code
                )
            elif isinstance(exc, NotAnArticleError):
                safe_error = NotAnArticleError(self.name, "page did not contain an article")
            elif isinstance(exc, ApiHttpError):
                safe_error = ApiHttpError(
                    self.name,
                    "Diffbot returned an unsuccessful status",
                    status_code=exc.status_code,
                )
            else:
                safe_error = ApiResponseError(self.name, "Diffbot response could not be processed")
        # Raise after leaving the handler: ``from None`` hides formatting, but
        # raising inside it would still retain the credential-bearing context.
        raise safe_error from None

    async def extract(self, url: str) -> RawArticle:
        result = await self.fetch_data({"url": url})
        item = result.items[0]
        payload = item.payload
        return RawArticle(
            text=payload["text"],
            title=payload.get("title"),
            author=payload.get("author"),
            date=payload.get("date"),
            page_url=payload.get("pageUrl"),
            resolved_page_url=payload.get("resolvedPageUrl"),
        )
