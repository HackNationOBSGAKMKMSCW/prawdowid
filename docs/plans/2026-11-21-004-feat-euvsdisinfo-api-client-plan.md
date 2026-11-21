---
title: Add EUvsDisinfo API client (bearer token from env)
type: feat
status: active
date: 2026-11-21
---

# feat: Add EUvsDisinfo API client

## Overview

Add a second child class of `BaseApiClient` that reads disinformation cases from EUvsDisinfo. It authenticates with a bearer token from the environment and reuses the existing schema (`ReadingRequest`, `Item`, `FetchResult`). The client must return fully prepared data: each `Item.payload` is a normalized, ready-to-use dict, not a raw upstream blob.

## Critical open question (verify before coding)

No public REST API documentation was found. The only machine access mentioned on https://euvsdisinfo.eu/disinformation-cases/ is an **MCP server connection, access by request form ("GET ACCESS")**. The site database has about 19.9k cases and is English only. The public list page is behind a robot check, so **do not scrape HTML**.

Before implementation, the user must supply the following from the access grant:
- Base URL and transport. Plain HTTPS JSON would fit `BaseApiClient` directly. If it is MCP (JSON-RPC over HTTP/SSE), `build_request` must emit a POST JSON-RPC call (`tools/call`), and the client needs a POST-capable `RequestSpec`. Note that `BaseApiClient._request` only retries GET.
- Search endpoint or tool name, and its parameters (query, date range, country, language, page or cursor).
- Response JSON shape (fields for title, URL, date, summary, outlets, countries, tags, disproof).
- Auth header format (assumed `Authorization: Bearer <token>`).
- Rate limits.

If these are not known, step 1 below is a short spike to capture one real response and save it as a fixture. All field names in this plan marked (assumed) must be confirmed against it.

## Existing conventions to follow

- Base class: `backend/apiReading/base.py:52-270`. Subclasses set `name`, `base_url` and `supported_categories`, and implement `build_request`, `filters_from_request` and `parse_response`.
- Reference implementation: `backend/apiReading/clients/google_fact_check.py:506-631`. It has whitelisted filters, strict types (bool rejected as int), cursor pagination via `FetchResult.next_cursor`, `ApiResponseError` on a bad shape, and a stable id via sha256.
- The key is passed in as `api_keys[client.name]`. Clients never read env vars (`reader.py:18-109`, `reading.py:27`).
- Settings: `backend/textAnalysis/settings.py:14-30` is a frozen dataclass with `from_environment()`. `.env.example` lists the keys.
- Schema: `backend/apiReading/models.py:297-391`. `Category` currently has only `FACT_CHECK`. `Item.payload` is `dict[str, Any]`.
- Auth errors: HTTP 401/403 already map to `ApiAuthError` in the base class.
- Tests use respx and pytest-asyncio (`backend/apiReading/tests/test_api_reading.py`). Ruff: line length 100, double quotes.
- No `docs/solutions/` exists, so there are no institutional learnings to apply.

## Proposed solution

### Files

- `backend/apiReading/clients/euvsdisinfo.py` (new): `EUvsDisinfoClient(BaseApiClient)`.
- `backend/apiReading/clients/__init__.py`: add it to `CLIENT_CLASSES`.
- `backend/apiReading/models.py`: reuse `Category.FACT_CHECK` (EUvsDisinfo cases are debunks of disinformation, which is fact-check material). Add a new category only if the user wants it separable. Default: no schema change, which satisfies "use existing schema".
- `backend/textAnalysis/settings.py`: add `euvsdisinfo_api_token` read from `EUVSDISINFO_API_TOKEN`.
- `backend/.env.example`: add `EUVSDISINFO_API_TOKEN=`.
- `backend/apiReading/reading.py` (about line 27): add `"euvsdisinfo": settings.euvsdisinfo_api_token` to the `api_keys` dict.
- `backend/apiReading/tests/test_euvsdisinfo.py` (new) and `backend/apiReading/tests/fixtures/euvsdisinfo_search.json` (new, a real captured response).
- Update the registry and reader tests that assert the client list or `__init__` exports, if any.

### Client design (sketch, not final code)

```python
# backend/apiReading/clients/euvsdisinfo.py
class EUvsDisinfoClient(BaseApiClient):
    name = "euvsdisinfo"
    base_url = "https://<confirmed-host>"       # from the access grant
    supported_categories = frozenset({Category.FACT_CHECK})
    max_page_size = 20                          # site offers 20/40/60 (assumed same in API)

    def filters_from_request(self, request): ...   # query, page_size, max_age_days -> date_from
    def build_request(self, filters): ...          # whitelist + strict types; header Authorization: Bearer <api_key>
    def parse_response(self, response): ...        # normalize each case -> Item
```

Details:
- The token goes in a **header** (`RequestSpec.headers`), never in the query string, and must not be logged. Check that the base class's retry logging does not print headers or URLs containing the token.
- A missing token is already handled by `reader.py` as an `ApiAuthError(401)` outcome. No extra handling is needed.
- `language_code` is ignored or not forwarded, because the database is English only. The client should document this and must not fail on it.
- `max_age_days` is converted to an absolute date filter, if the API supports one. Otherwise it is filtered client-side in `parse_response`.
- Pagination: map the API's page or cursor to `page_token` and `FetchResult.next_cursor` (a stringified page number if the API is page-based). One page per `fetch_data` call, as in the Google client.

### "Prepared data" normalization

`Item.id` is a stable `euvd_` plus the upstream case id, or a sha256 prefix of the case URL if no id exists. `Item.payload` is a flat, predictable dict (field names assumed, confirm against the real response):

```
title, summary, url, published_at (ISO 8601), languages_of_outlet,
countries, outlets (list of {name, url}), tags, disproof (text/url),
rating = "disinformation", source_name = "EUvsDisinfo"
```

- Missing optional fields become `None` or `[]`, never absent, so consumers can rely on the keys.
- HTML is stripped and dates are normalized to ISO strings.
- Keep a `raw` key only if the user wants raw data kept (default: no, to keep the payload small).
- Any shape violation (not a dict, the case list missing, a non-list) raises `ApiResponseError`.

## Acceptance criteria

- [ ] `EUvsDisinfoClient` subclasses `BaseApiClient` and passes the `__init_subclass__` checks.
- [ ] It is registered in `CLIENT_CLASSES`, and `read()` for `Category.FACT_CHECK` queries both Google and EUvsDisinfo concurrently.
- [ ] The token comes from `EUVSDISINFO_API_TOKEN` via `Settings`, is listed in `.env.example`, and is sent as a Bearer header.
- [ ] The token never appears in logs, errors or `FetchOutcome` dumps.
- [ ] Output uses the existing `Item` / `FetchResult` schema, with a normalized payload as above.
- [ ] A missing or invalid token yields an `ApiAuthError` outcome, and the other sources still return results (partial failure preserved).
- [ ] Invalid filters raise `InvalidFiltersError`. A malformed response raises `ApiResponseError`.
- [ ] Tests (respx): success with the fixture, empty results, pagination cursor, 401, 429 with Retry-After, malformed JSON, header presence, and token absent from the query string.
- [ ] `ruff check` and `pytest` pass.

## System-wide impact

- **Interaction graph:** `reading.run` -> `reader.read` -> `fetch_all` (gather). The new client adds one more concurrent call per statement. This doubles upstream calls per `FACT_CHECK` statement, so watch the rate limits.
- **Error propagation:** failures are isolated per client in `FetchOutcome`. The new client adds no new exception types.
- **API surface parity:** downstream consumers (analysis, frontend) that read `Item.payload` assume the Google claim shape. Check how `Item` objects are consumed after `reading.run` and make sure the differing payload shapes per `source` do not break them. This is the main integration risk.
- **Integration test:** run `reader.read` with respx mocks for both sources, where one returns 401 and the other succeeds. Expect a partial result.

## Dependencies and risks

- **Blocking:** API access, docs and a token from EUvsDisinfo (see the open question). The transport may be MCP rather than REST.
- The upstream payload may change. Mitigate with a fixture and strict shape checks.
- Terms of use for the data: check the attribution requirements, and keep `source_name` and `url` in the payload.
- Wiring is manual in `reading.py` (hardcoded keys). Optionally derive keys from a settings map, but that is out of scope.

## Sources

- https://euvsdisinfo.eu/disinformation-cases/ (database page; MCP access via request form)
- `backend/apiReading/base.py`, `backend/apiReading/clients/google_fact_check.py`, `backend/apiReading/models.py`, `backend/textAnalysis/settings.py`
- Related plan: `docs/plans/2026-11-21-001-feat-async-multi-api-fetcher-layer-plan.md`
