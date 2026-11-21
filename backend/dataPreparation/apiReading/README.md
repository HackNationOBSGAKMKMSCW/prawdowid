# API reading

`apiReading` is an async library for reading from third-party APIs by category.
The primary entry point accepts one `ReadingRequest`, selects matching
providers, queries them concurrently, and returns a `ReadingResult` with
per-provider outcomes and a combined item list.

```python
import asyncio

from apiReading import Category, ReadingRequest, read


async def collect() -> None:
    result = await read(
        ReadingRequest(
            query="claim text",
            categories=[Category.FACT_CHECK],
            language_code="pl",
            metadata={"record_id": 42},
        ),
        api_keys={"google_fact_check": "..."},
    )

    for outcome in result.results:
        if outcome.error:
            print(outcome.source, outcome.error)
    for item in result.items:
        print(item.payload.get("text"), item.payload.get("claimReview"))


asyncio.run(collect())
```

`metadata` is opaque caller data: it is echoed in `result.request` and never
sent to a provider. The query text is sent to Google's Fact Check Tools API,
which is outside the EEA per the project classification. `read()` requires
Google's API key in the `api_keys` mapping.

`read()` creates and closes a pooled `httpx.AsyncClient` for the call. A caller
can supply a shared client instead; it remains caller-owned and is never closed
by the library. Missing API keys and individual provider failures appear as
typed errors in `result.results`. Categories without a registered provider are
listed in `result.categories_without_source`; if none of the requested
categories has a provider, `read()` raises `NoSourcesAvailableError`.

The low-level `GoogleFactCheckClient.fetch_data(filters)` and `fetch_all(...)`
interfaces remain available for provider-specific use. They perform one page
per request; use the returned `next_cursor` as `page_token` to fetch another
page. Retries are bounded and handled by each client, so callers should not
retry blindly on top of this behavior.
