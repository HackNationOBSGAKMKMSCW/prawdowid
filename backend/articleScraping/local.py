"""Local article extraction: fetch the page ourselves and parse it with trafilatura.

Because this extractor fetches user-supplied URLs directly, every redirect is
validated and DNS resolution is pinned to a public address before connecting.
"""

import asyncio
import ipaddress
import socket
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from email.utils import format_datetime
from typing import Any
from urllib.parse import urljoin, urlsplit

import httpx
import trafilatura
from apiReading.exceptions import (
    ApiConnectionError,
    ApiHttpError,
    ApiResponseError,
    ApiTimeoutError,
)

from .diffbot import NotAnArticleError
from .protocols import RawArticle
from .url_validation import InvalidUrlError, validate_url

SOURCE_NAME = "local_article"
MAX_RESPONSE_BYTES = 2 * 1024 * 1024
MAX_REDIRECTS = 3
MIN_ARTICLE_CHARS = 100
_ACCEPTED_TYPES = ("text/html", "application/xhtml+xml", "text/plain")
_USER_AGENT = "Mozilla/5.0 (compatible; PrawdowidBot/1.0; +article-verification)"

Resolver = Callable[[str, int], Awaitable[list[str]]]


async def _resolve(host: str, port: int) -> list[str]:
    infos = await asyncio.get_running_loop().getaddrinfo(
        host, port, type=socket.SOCK_STREAM, proto=socket.IPPROTO_TCP
    )
    return list(dict.fromkeys(info[4][0] for info in infos))


def _is_public(address: str) -> bool:
    try:
        return ipaddress.ip_address(address.split("%", 1)[0]).is_global
    except ValueError:
        return False


class LocalArticleExtractor:
    """Implements ``ArticleExtractor`` without an external extraction service."""

    name = SOURCE_NAME

    def __init__(
        self,
        *,
        client: httpx.AsyncClient | None = None,
        timeout: float = 15.0,
        max_response_bytes: int = MAX_RESPONSE_BYTES,
        resolver: Resolver = _resolve,
    ) -> None:
        if timeout <= 0 or max_response_bytes < 1:
            raise ValueError("timeout and max_response_bytes must be positive")
        self._client = client
        self._owns_client = client is None
        self._timeout = httpx.Timeout(timeout, connect=min(5.0, timeout))
        self._max_bytes = max_response_bytes
        self._resolver = resolver

    async def aclose(self) -> None:
        """Close the HTTP client only when this extractor owns it."""

        if self._owns_client and self._client is not None:
            await self._client.aclose()
            self._client = None

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self._timeout, follow_redirects=False)
        return self._client

    async def extract(self, url: str) -> RawArticle:
        html, final_url = await self._fetch(url)
        return await asyncio.to_thread(self._parse, html, final_url)

    async def _fetch(self, url: str) -> tuple[bytes, str]:
        current = url
        for _ in range(MAX_REDIRECTS + 1):
            response, body = await self._fetch_once(current)
            if response.is_redirect:
                location = response.headers.get("location")
                if not location:
                    raise ApiHttpError(
                        self.name, "redirect without location", status_code=response.status_code
                    )
                current = urljoin(current, location)
                continue
            if response.status_code < 200 or response.status_code >= 300:
                raise ApiHttpError(
                    self.name,
                    "page returned an unsuccessful status",
                    status_code=response.status_code,
                )
            content_type = response.headers.get("content-type", "").split(";")[0].strip().lower()
            if content_type and content_type not in _ACCEPTED_TYPES:
                raise NotAnArticleError(self.name, "page is not an HTML document")
            return body, current
        raise ApiHttpError(self.name, "too many redirects")

    async def _fetch_once(self, url: str) -> tuple[httpx.Response, bytes]:
        try:
            safe_url = validate_url(url)
        except InvalidUrlError as exc:
            raise ApiConnectionError(self.name, "URL is not allowed") from exc
        parts = urlsplit(safe_url)
        host = parts.hostname or ""
        port = parts.port or (443 if parts.scheme == "https" else 80)

        try:
            addresses = await self._resolver(host, port)
        except OSError as exc:
            raise ApiConnectionError(self.name, "host could not be resolved") from exc
        if not addresses or not all(_is_public(address) for address in addresses):
            raise ApiConnectionError(self.name, "host resolves to a non-public address")

        # Pin the connection to the address validated above to prevent DNS rebinding.
        pinned = addresses[0]
        netloc_ip = f"[{pinned}]" if ":" in pinned else pinned
        if parts.port:
            netloc_ip = f"{netloc_ip}:{parts.port}"
        target = parts._replace(netloc=netloc_ip).geturl()
        extensions: dict[str, Any] = {"sni_hostname": host} if parts.scheme == "https" else {}

        client = self._get_client()
        chunks: list[bytes] = []
        total = 0
        try:
            async with client.stream(
                "GET",
                target,
                headers={
                    "Host": parts.netloc,
                    "User-Agent": _USER_AGENT,
                    "Accept": "text/html,application/xhtml+xml",
                },
                extensions=extensions,
                timeout=self._timeout,
                follow_redirects=False,
            ) as response:
                if not response.is_redirect:
                    async for chunk in response.aiter_bytes(chunk_size=64 * 1024):
                        total += len(chunk)
                        if total > self._max_bytes:
                            raise ApiResponseError(self.name, "page exceeded the size limit")
                        chunks.append(chunk)
                snapshot = httpx.Response(
                    status_code=response.status_code,
                    headers=response.headers,
                    request=response.request,
                )
        except httpx.TimeoutException as exc:
            raise ApiTimeoutError(self.name, "page request timed out") from exc
        except httpx.HTTPError as exc:
            raise ApiConnectionError(self.name, "page request failed") from exc
        return snapshot, b"".join(chunks)

    def _parse(self, html: bytes, url: str) -> RawArticle:
        document = trafilatura.bare_extraction(
            html,
            url=url,
            with_metadata=True,
            include_comments=False,
            include_tables=False,
            favor_precision=True,
        )
        text = (getattr(document, "text", None) or "").strip()
        if len(text) < MIN_ARTICLE_CHARS:
            raise NotAnArticleError(self.name, "page did not contain an article")
        return RawArticle(
            text=text,
            title=getattr(document, "title", None),
            author=getattr(document, "author", None),
            date=_to_rfc1123(getattr(document, "date", None)),
        )


def _to_rfc1123(value: str | None) -> str | None:
    """Convert Trafilatura's ISO date to the format expected by ``map_article``."""

    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return format_datetime(parsed.astimezone(UTC), usegmt=True)
