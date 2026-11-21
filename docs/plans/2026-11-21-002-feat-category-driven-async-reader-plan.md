---
title: "feat: Category-driven async reader with request object in, aggregated result object out"
type: feat
status: completed
date: 2026-11-21
---

# feat: Category-driven async reader with request object in, aggregated result object out

## Overview

Replace the example clients and the dict-based `fetch_all` entry point with one public async call:

```python
result: ReadingResult = await read(request: ReadingRequest, *, api_keys=..., http_client=None)
```

The caller passes **one object** describing what to look for, including the **categories** to search. The library picks every API that serves those categories, queries them concurrently, and returns **one object** containing the original request plus the data read from every API (and per-API errors). The other developer's service never touches individual clients.

No origin brainstorm and no `docs/solutions/` exist. Local context (from the previous plan, 2026-11-21-001) is sufficient. External research skipped: the only real API (Google Fact Check) was verified against its Discovery document during the last task, and httpx/pydantic patterns are already in the repo.

## Problem Statement / Motivation

Today the caller must instantiate each client, build a `{client: filters}` dict and know each API's filter vocabulary. That leaks provider details into the caller, the example clients (`ExampleAClient`, `ExampleBClient`) are dead weight, and results do not say which request they answer.

## Proposed Solution

### Layout (changes only)

```
backend/dataPreparation/apiReading/
  __init__.py              # exports: read, ReadingRequest, ReadingResult, Category, errors
  models.py                # + Category, ReadingRequest, ReadingResult (existing models stay)
  registry.py              # NEW: category -> client classes mapping, client construction
  reader.py                # NEW: read() orchestration (replaces public use of fetch_all)
  aggregator.py            # kept as internal helper used by reader.py
  base.py                  # + supported_categories ClassVar, abstract-ish build_filters()
  clients/
    google_fact_check.py   # + supported_categories, accepts ReadingRequest
    (example_a.py, example_b.py  -> DELETED)
backend/dataPreparation/tests/
  test_api_reading.py      # remove example-client tests, repoint to Google client
  test_reader.py           # NEW: read() orchestration tests
```

### Input object

```python
class Category(StrEnum):
    FACT_CHECK = "fact_check"      # Google Fact Check; more added as APIs are added

class ReadingRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    query: str                      # what we look for (claim / topic text)
    categories: list[Category]      # which kinds of APIs to search; min 1, deduplicated
    language_code: str | None = None
    max_age_days: int | None = None
    page_size: int = 10
    metadata: dict[str, Any] = {}   # opaque caller data, echoed back untouched (e.g. record id)
```

Pydantic validates it, so a malformed object fails before any network call (`InvalidFiltersError`-style typed error; no pydantic exception leaks, per the existing rule).

### Output object

```python
class ReadingResult(BaseModel):
    request: ReadingRequest                 # exactly what was searched for
    results: list[FetchOutcome]             # one per API queried, success or typed error
    items: list[Item]                       # convenience: all items from successful APIs
    categories_without_source: list[Category]  # requested but no client registered
    fetched_at: datetime
    duration_ms: int
```

Partial failure is normal: a failing API yields a `FetchOutcome.error`, never aborts the others (existing `fetch_all` semantics). `read()` itself only raises for an invalid request or when **no** API could be selected.

### Client contract change

`BaseApiClient` gains `supported_categories: ClassVar[frozenset[Category]]` (enforced in `__init_subclass__`, like `name`/`base_url`) and an abstract `filters_from_request(request) -> dict` that maps the shared request onto that API's filters. `fetch_data(filters: dict)` stays unchanged as the low-level interface, so the template method, retry, and error mapping are untouched.

Google mapping: `query -> query`, `language_code -> language_code`, `max_age_days -> max_age_days`, `page_size -> page_size`. Fields the API does not support are ignored by that client, not errors.

### Registry and orchestration

- `registry.py`: `CLIENTS_BY_CATEGORY: dict[Category, tuple[type[BaseApiClient], ...]]`, derived from each client's `supported_categories` (a client may serve several categories; it is queried once).
- `read()` steps: validate request -> resolve client classes (dedup) -> instantiate each with the shared `httpx.AsyncClient` and its API key -> `asyncio.gather`-based fan-out via existing `fetch_all` -> assemble `ReadingResult`.
- API keys: `api_keys: Mapping[str, str]` keyed by client `name` (caller reads env; library never reads env, never logs keys). Missing key -> that source returns `ApiAuthError`-style outcome, others continue.
- HTTP client: if the caller passes `http_client`, it is reused and never closed; otherwise `read()` creates one for the call and closes it in a `finally` (no leak on cancel).
- Concurrency: unchanged; per-client `max_concurrency` and timeouts still apply; `CancelledError` propagates.

## Technical Considerations

- **Deleting examples:** remove `example_a.py`, `example_b.py`, their exports in `clients/__init__.py` and `apiReading/__init__.py`, README sections, and all example-based tests. Tests that exercised shared base behavior (retries, timeouts, error mapping, lifecycle, abstractness) must be **repointed to `GoogleFactCheckClient`** or a small test-only client defined in the test module (`tests/` only, not shipped), so coverage of `base.py` is not lost.
- **Stale graph:** `graphify-out/` references the deleted clients; re-run `/graphify --update` after implementation.
- **Typing:** keep strict mypy clean on the package; `Category` as `StrEnum` (py311+).
- **Security:** query text is sent to external providers (Google is outside the EEA); document this next to `ReadingRequest.query`. `metadata` is never sent to any API.
- **Performance:** one shared pooled client, small default pages, field masks (already in Google client); duration measured with `time.perf_counter`.

## System-Wide Impact

- **Interaction graph:** `read()` -> registry -> `BaseApiClient.fetch_data` -> `_request` (retry/error mapping) -> `parse_response`; aggregation via `fetch_all`. No callbacks/observers exist.
- **Error propagation:** transport/HTTP/parse errors become typed `ApiReadingError` at the base layer and land in `FetchOutcome.error`; `read()` adds only request-validation errors and a "no sources" error. Retries live only in `_request`; `read()` must not retry.
- **State lifecycle risks:** only the HTTP client is stateful; owned-client close in `finally` covers cancel/failure.
- **API surface parity:** `fetch_data`/`fetch_all` remain public for low-level use; document that `read()` is the primary entry point.
- **Integration test scenarios:**
  1. Request with two categories where one API succeeds and one returns 503: result has both outcomes, `items` only from the success.
  2. Request echo: `result.request` equals the input, including `metadata`.
  3. Category with no registered client: listed in `categories_without_source`, no exception when at least one other category resolved.
  4. All requested categories unresolved: typed error, no network call.
  5. Caller-supplied `http_client` stays open after `read()`; internally created one is closed even when a task is cancelled.

## Acceptance Criteria

- [x] `read(ReadingRequest) -> ReadingResult` is async and exported from `apiReading`.
- [x] Example clients, their tests, exports, and README text are gone; no implementation/test/README reference to the deleted clients remains.
- [x] Categories in the request select the APIs; each API is queried at most once and selected APIs run concurrently (verified with a synchronized mock transport).
- [x] `ReadingResult.request` echoes the input object; `metadata` round-trips unchanged and is never sent over the network.
- [x] One failing API does not hide data from the others; failures appear as typed errors per source.
- [x] Invalid request (empty query, empty/duplicate/unknown categories) raises a typed error before any HTTP call.
- [x] Shared-base behavior tests (timeouts, 401/403, 429 retry, 5xx retry, bad JSON, client ownership) still pass against a test-only client and Google client.
- [x] `ruff check`, `ruff format --check`, and `mypy --strict` pass; README shows the new usage.

## Success Metrics

- Caller integration is a single call with one object; adding a new API requires only a new client file declaring `supported_categories` and `filters_from_request`, with no changes to `read()`.

## Dependencies & Risks

- **Unknown category vocabulary.** Only `fact_check` exists today; the real category list is the caller's to define. Mitigation: `Category` is a single enum; adding values is a one-line change per API.
- **Request fields beyond `query`/`categories`** (e.g. entity, date range, URL) are assumed. Mitigation: `extra="forbid"` surfaces mismatches early; fields are easy to add.
- **Breaking change:** anything importing the example clients breaks (only this repo's tests do).
- Missing API key silently degrading to an error outcome could be missed by callers; mitigate by documenting and exposing errors in `results`.

## Open Questions (non-blocking, defaults chosen)

1. What are the real category names and which request fields does the other developer's object actually carry? Default: `Category.FACT_CHECK` plus the fields above.
2. Should `read()` fetch only the first page per API (default) or follow `next_cursor`? Default: first page; pagination left to a follow-up.
3. Should "no source for any category" raise or return an empty result? Default: raise a typed error.
4. Should `ReadingResult.items` be deduplicated across APIs? Default: no.

## Implementation Phases

1. **Models and contract:** `Category`, `ReadingRequest`, `ReadingResult` in `models.py`; `supported_categories` and `filters_from_request` in `base.py`; update `google_fact_check.py`.
2. **Registry and reader:** `registry.py`, `reader.py`, exports in `__init__.py`.
3. **Removal and test repointing:** delete example clients/tests/README text; repoint base tests; add `test_reader.py`.
4. **Docs and graph:** README usage for `read()`; run `ruff`, `mypy --strict`, `pytest`; `/graphify --update`.

## Sources & References

- Previous plan: `docs/plans/2026-11-21-001-feat-async-multi-api-fetcher-layer-plan.md`
- Existing code: `backend/dataPreparation/apiReading/base.py`, `aggregator.py`, `models.py`, `clients/google_fact_check.py`
- Tests to repoint: `backend/dataPreparation/tests/test_api_reading.py`
- Google API contract: https://developers.google.com/fact-check/tools/api/reference/rest/v1alpha1/claims/search
