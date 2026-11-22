"""In-memory web for trustedSources tests: routes by Host header + path."""

from collections.abc import Callable
from typing import Any

import httpx
from articleScraping.safe_http import SafeFetcher

from trustedSources.adapters import SearchContext
from trustedSources.cache import CACHE
from trustedSources.settings import TrustedSettings

Handler = Callable[[httpx.Request], httpx.Response]


class FakeWeb:
    def __init__(self) -> None:
        self.routes: dict[tuple[str, str], Handler | httpx.Response] = {}
        self.requests: list[httpx.Request] = []

    def add(self, url: str, response: Handler | httpx.Response | str | bytes | dict, **kwargs: Any) -> None:
        parsed = httpx.URL(url)
        if isinstance(response, str | bytes):
            content_type = kwargs.pop("content_type", "text/html; charset=utf-8")
            response = httpx.Response(200, content=response, headers={"content-type": content_type})
        elif isinstance(response, dict):
            response = httpx.Response(200, json=response)
        self.routes[(parsed.host, parsed.path)] = response

    def handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        host = request.headers.get("host", request.url.host).split(":")[0]
        route = self.routes.get((host, request.url.path))
        if route is None:
            return httpx.Response(404, text="not found")
        return route(request) if callable(route) else route

    def client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=httpx.MockTransport(self.handle))

    def fetcher(self, *, public: bool = True) -> SafeFetcher:
        async def resolver(host: str, port: int) -> list[str]:
            return ["93.184.216.34" if public else "10.0.0.5"]

        return SafeFetcher(name="test", client=self.client(), resolver=resolver, timeout=2)

    def context(self, **settings: Any) -> SearchContext:
        values: dict[str, Any] = {"google_fact_check_api_key": "test-key"}
        values.update(settings)
        return SearchContext(
            http=self.client(),
            fetcher=self.fetcher(),
            cache=CACHE,
            settings=TrustedSettings(**values),
        )


def govpl_results(*results: tuple[str, str]) -> dict[str, Any]:
    return {
        "count": len(results),
        "results": [
            {
                "title": title,
                "intro": None,
                "publishDate": "2026-11-01T10:00:00Z",
                "url": url,
                "path": url.split("/")[2],
            }
            for title, url in results
        ],
    }
