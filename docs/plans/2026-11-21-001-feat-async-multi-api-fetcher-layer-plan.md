---
title: "feat: Async multi-API data fetcher service layer"
type: feat
status: completed
date: 2026-11-21
---

# feat: Async multi-API data fetcher service layer

## Overview

A library (not a server) under `backend/dataPreparation/apiReading/` that another developer's API imports and calls. An ABC holds shared httpx/async/error logic; one child class per third-party API holds only that API's filter mapping and response parsing. All children share `async def fetch_data(self, filters: dict) -> FetchResult`, so a caller can run many concurrently with `asyncio.gather`.

Repo is greenfield: `apiReading/` is empty, ruff config (py311, line-length 100, rules E,F,I,UP,B,SIM) is at repo root. No origin brainstorm, no `docs/solutions/`. External research skipped for libraries (httpx/pydantic are well known); the risk-prone parts (timeouts, client lifecycle, gather semantics) are addressed below.

## Proposed Solution

### Layout

```
backend/dataPreparation/apiReading/
  __init__.py          # public exports (the import surface for the other dev)
  exceptions.py
  models.py
  base.py              # BaseApiClient (ABC)
  clients/
    __init__.py
    example_a.py       # one file per external API
    example_b.py
  aggregator.py        # fetch_all helper
tests/dataPreparation/  # pytest + respx
```

### exceptions.py

```python
class ApiReadingError(Exception):
    def __init__(self, source: str, message: str, *, status_code: int | None = None,
                 cause: BaseException | None = None): ...

class ApiConnectionError(ApiReadingError): ...   # DNS, connect, network
class ApiTimeoutError(ApiReadingError): ...
class ApiHttpError(ApiReadingError): ...         # non-2xx; carries status_code
class ApiRateLimitError(ApiHttpError): ...       # 429; optional retry_after
class ApiAuthError(ApiHttpError): ...            # 401/403
class ApiResponseError(ApiReadingError): ...     # invalid JSON / schema mismatch
class InvalidFiltersError(ApiReadingError, ValueError): ...  # bad caller filters, raised before any request
```

Rule: no `httpx` or `pydantic` exception ever escapes. Always `raise ... from exc`. Never include API keys/headers in messages.

### models.py (Pydantic v2)

```python
class FetchResult(BaseModel):
    source: str
    items: list[Item]
    fetched_at: datetime
    total: int | None = None
    next_cursor: str | None = None   # pagination hint, optional

class Item(BaseModel):               # normalized common shape
    id: str
    source: str
    payload: dict[str, Any]          # raw/extra fields preserved
    # + common normalized fields, decided once real APIs are known

class FetchOutcome(BaseModel):       # for aggregator
    source: str
    result: FetchResult | None
    error: ApiReadingError | None    # arbitrary_types_allowed
```

Per-API filter typing: each child may define a `TypedDict`/Pydantic filter model and validate `filters` inside `build_request`, raising `InvalidFiltersError`. The public signature stays `filters: dict`.

### base.py: BaseApiClient(ABC)

- `name: ClassVar[str]`, `base_url: ClassVar[str]` (abstract-ish, enforced in `__init_subclass__`).
- `__init__(self, *, client: httpx.AsyncClient | None = None, api_key: str | None = None, timeout: float = 10.0, max_retries: int = 2)`.
  - If a client is injected, the caller owns it (not closed by us). Otherwise lazily create one and own it. This lets the other dev share a single pooled client and lets tests inject `respx`/`MockTransport`.
- `async __aenter__/__aexit__` and `aclose()`.
- Template method (final, not overridden):
  ```python
  async def fetch_data(self, filters: dict[str, Any] | None = None) -> FetchResult:
      spec = self.build_request(filters or {})      # abstract; validates/maps filters
      response = await self._request(spec)          # shared: retry, timeout, error mapping
      return self.parse_response(response)          # abstract; raises ApiResponseError
  ```
- Abstract: `build_request(filters) -> RequestSpec` (method, path, params, json, headers) and `parse_response(response: httpx.Response) -> FetchResult`.
- `_request`: wraps `httpx` call; maps `TimeoutException`→`ApiTimeoutError`, `TransportError`→`ApiConnectionError`, status 429/401/403/other→typed errors (`raise_for_status` mapping, honour `Retry-After`). Retries with exponential backoff + jitter only for idempotent GETs on timeouts/connect errors/502/503/504/429; capped by `max_retries`.
- Logging via `logging.getLogger(__name__)` with source name and status, no secrets.
- Timeouts: `httpx.Timeout(timeout, connect=5.0)`; `httpx.Limits` configurable.
- Optional per-instance `asyncio.Semaphore` for the API's rate limit.

### aggregator.py

```python
async def fetch_all(requests: Mapping[BaseApiClient, dict], *, return_exceptions: bool = True
                    ) -> list[FetchOutcome]
```
Uses `asyncio.TaskGroup` wrapper or `gather(return_exceptions=True)` so one failing API does not cancel the others; the caller gets per-source success/error. Preserves `CancelledError` (do not swallow).

### Concrete clients

`clients/<api>.py` each implement only `name`, `base_url`, `build_request` (filter→query-param mapping, defaults, validation, auth header) and `parse_response` (to `Item`). Actual API list is unknown: see open questions. Two stub examples are enough to prove the abstraction.

## Implementation Phases

1. **Foundation**: `exceptions.py`, `models.py`, `base.py`, add `httpx`, `pydantic`, `pytest`, `pytest-asyncio`, `respx` to `backend/requirements.txt`.
2. **Clients**: one real client per API, plus filter models.
3. **Aggregator + exports + README docstring/usage example** for the other developer.
4. **Tests/lint**: `ruff check` and `ruff format` clean.

## System-Wide Impact

- **Error propagation**: transport/HTTP/parse errors → typed `ApiReadingError` subclasses at the base layer → caller catches `ApiReadingError` (or subclasses). `fetch_all` converts to `FetchOutcome.error`. Retries live only in `_request`; callers must not also retry blindly (document it).
- **State lifecycle**: stateless apart from the HTTP client. Leak risk if the owned client is never closed → context manager plus `aclose()`; injected clients are never closed by us.
- **Event loop**: clients bind to the loop of first use; do not share a client across loops.
- **Interface parity**: all children share one signature, enforced by the base template method; a test iterates over all subclasses.
- **Security**: API keys come from constructor args (caller reads env); never log; HTTPS-only base URLs; validate filters to avoid parameter injection.

## Acceptance Criteria

- [ ] `BaseApiClient` cannot be instantiated; a subclass missing abstract members raises `TypeError`.
- [ ] Every child exposes `async fetch_data(self, filters: dict) -> FetchResult` with full type hints (mypy/pyright clean on the package).
- [ ] Each child contains only its API-specific filter and parse logic; no httpx calls or error handling duplicated.
- [ ] Timeout, connect failure, 401/403, 429, 5xx, bad JSON, and schema mismatch each raise the documented exception; no raw httpx/pydantic exceptions leak.
- [ ] Invalid filters raise `InvalidFiltersError` without a network call.
- [ ] `fetch_all` with N clients runs concurrently (total time ≈ max, not sum, shown with delayed mock transports) and one failure doesn't cancel the others.
- [ ] Injected `httpx.AsyncClient` is not closed; owned client is closed on `aclose`/context exit.
- [ ] Retries: bounded, backoff, only on retryable conditions; verified with respx.
- [ ] `ruff check` and `ruff format --check` pass.

## Dependencies & Risks

- Unknown: the actual third-party APIs, auth schemes, pagination, rate limits. Mitigation: `RequestSpec` and optional `next_cursor` keep the base generic; add pagination helper later if needed.
- Common `Item` schema is a guess until the APIs are known; keep `payload` for raw fields.
- Retry on non-idempotent calls could duplicate effects: restricted to GET by default.
- The other developer may run under FastAPI: the sharing-one-client pattern (inject at lifespan) should be documented.

## Open Questions

1. Which APIs, and what are their filters/auth/rate limits?
2. Should the normalized `Item` be uniform across APIs, or one Pydantic model per API?
3. Pagination: single page or fetch all pages?
4. Caching needed?

## Sources & References

- Repo config: `ruff.toml`; target Python 3.11 (enables `asyncio.TaskGroup`)
- httpx async client/timeouts/transport docs; respx for mocking; Pydantic v2 docs
