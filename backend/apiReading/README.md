# API reading package

Call the package's single entry point with the object returned by
`textAnalysis.run()`. It searches the extracted statements and returns the
results. Provider selection, requests, and response handling are internal.

```python
import asyncio

import apiReading
import textAnalysis


async def collect() -> None:
    analysis = await textAnalysis.run("A claim to verify.")
    results = await apiReading.run(analysis)
    for result in results:
        for item in result.items:
            print(item.payload.get("text"), item.payload.get("claimReview"))


asyncio.run(collect())
```

The package reads its Google API key from `GOOGLE_FACT_CHECK_API_KEY`. It owns
the network client lifecycle and returns per-source errors with each result;
callers do not need to construct requests or clients. Progress output identifies
each statement by number, shows request duration and retry delays, and avoids
printing the statement text or API key.

## Smoke test with final data

```bash
cd backend && ../.venv/bin/python -m scripts.smoke_pipeline [--json] ["text"]
RUN_LIVE_TESTS=1 .venv/bin/python -m pytest -m live -s   # opt-in live test
```
