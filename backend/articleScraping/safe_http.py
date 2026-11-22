"""SSRF-safe GET for user- or admin-supplied URLs.

Every hop (including redirects) is validated with ``validate_url``, DNS is
resolved up front, every resolved address must be public, and the connection
is pinned to the validated address to prevent DNS rebinding. Bodies are
streamed with a hard size limit.
"""

import asyncio
import ipaddress
import socket
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass
from typing import Any
from urllib.parse import urljoin, urlsplit

import httpx
from apiReading.exceptions import (
    ApiConnectionError,
    ApiHttpError,
    ApiResponseError,
    ApiTimeoutError,
)

from .url_validation import InvalidUrlError, validate_url

DEFAULT_MAX_BYTES = 2 * 1024 * 1024
MAX_REDIRECTS = 3
USER_AGENT = "Mozilla/5.0 (compatible; PrawdowidBot/1.0; +article-verification)"

Resolver = Callable[[str, int], Awaitable[list[str]]]


async def resolve_host(host: str, port: int) -> list[str]:
    infos = await asyncio.get_running_loop().getaddrinfo(
        host, port, type=socket.SOCK_STREAM, proto=socket.IPPROTO_TCP
    )
    return list(dict.fromkeys(info[4][0] for info in infos))


def is_public_address(address: str) -> bool:
    try:
        return ipaddress.ip_address(address.split("%", 1)[0]).is_global
    except ValueError:
        return False


class UnsupportedContentError(ApiResponseError):
    """The response media type is not one the caller accepts."""


@dataclass(frozen=True)
class FetchedPage:
    body: bytes
    final_url: str
    content_type: str
    status_code: int


class SafeFetcher:
    """Fetch public web resources without following redirects into private networks."""

    def __init__(
        self,
        *,
        name: str = "safe_http",
        client: httpx.AsyncClient | None = None,
        timeout: float = 15.0,
        max_response_bytes: int = DEFAULT_MAX_BYTES,
        resolver: Resolver = resolve_host,
        user_agent: str = USER_AGENT,
    ) -> None:
        if timeout <= 0 or max_response_bytes < 1:
            raise ValueError("timeout and max_response_bytes must be positive")
        self.name = name
        self._client = client
        self._owns_client = client is None
        self._timeout = httpx.Timeout(timeout, connect=min(5.0, timeout))
        self._max_bytes = max_response_bytes
        self._resolver = resolver
        self._user_agent = user_agent

    async def aclose(self) -> None:
        if self._owns_client and self._client is not None:
            await self._client.aclose()
            self._client = None

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self._timeout, follow_redirects=False)
        return self._client

    async def get(
        self,
        url: str,
        *,
        accept: Iterable[str] | None = None,
        accept_header: str = "*/*",
        max_bytes: int | None = None,
    ) -> FetchedPage:
        """GET ``url`` following up to ``MAX_REDIRECTS`` validated redirects.

        ``accept`` lists acceptable media types (``None`` accepts anything); a
        missing Content-Type header is tolerated.
        """

        accepted = {item.lower() for item in accept} if accept is not None else None
        limit = max_bytes or self._max_bytes
        current = url
        for _ in range(MAX_REDIRECTS + 1):
            response, body = await self._fetch_once(current, accept_header, limit)
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
            if accepted is not None and content_type and content_type not in accepted:
                raise UnsupportedContentError(self.name, "unexpected content type")
            return FetchedPage(body, current, content_type, response.status_code)
        raise ApiHttpError(self.name, "too many redirects")

    async def _fetch_once(
        self, url: str, accept_header: str, limit: int
    ) -> tuple[httpx.Response, bytes]:
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
        if not addresses or not all(is_public_address(address) for address in addresses):
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
                    "User-Agent": self._user_agent,
                    "Accept": accept_header,
                },
                extensions=extensions,
                timeout=self._timeout,
                follow_redirects=False,
            ) as response:
                if not response.is_redirect:
                    async for chunk in response.aiter_bytes(chunk_size=64 * 1024):
                        total += len(chunk)
                        if total > limit:
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
