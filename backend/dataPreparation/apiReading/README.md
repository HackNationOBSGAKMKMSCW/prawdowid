# API reading clients

`apiReading` is an async library for fetching and normalizing data from several
third-party APIs. Each client shares one `fetch_data(filters)` interface;
`fetch_all` runs clients concurrently and returns per-source results/errors.
The included `ExampleAClient` and `ExampleBClient` demonstrate the extension
points and use reserved `.invalid` hosts until real APIs are selected.

```python
import asyncio

import httpx

from apiReading import ExampleAClient, ExampleBClient, fetch_all


async def collect() -> None:
    async with httpx.AsyncClient() as shared_client:
        clients = {
            ExampleAClient(client=shared_client, api_key="..."): {"category": "news"},
            ExampleBClient(client=shared_client): {"query": "election", "limit": 25},
        }
        outcomes = await fetch_all(clients)
        for outcome in outcomes:
            if outcome.error:
                print(outcome.source, outcome.error)
            else:
                print(outcome.source, outcome.result.items)


asyncio.run(collect())
```

When a client creates its own HTTP connection pool, use its async context
manager or call `await client.aclose()`. An injected `httpx.AsyncClient` remains
owned by the caller. Retries are performed by the client only for idempotent
GET requests; callers should not retry blindly on top of this behavior.
