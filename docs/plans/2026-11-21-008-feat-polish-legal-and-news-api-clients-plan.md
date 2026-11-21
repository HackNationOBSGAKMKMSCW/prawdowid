---
title: Add Sejm/ISAP, EUR-Lex, dane.gov.pl and PAP API clients
type: feat
status: completed
date: 2026-11-21
---

# feat: Add Sejm/ISAP, EUR-Lex, dane.gov.pl and PAP API clients

## Overview

Add new `BaseApiClient` subclasses, built the same way as the existing Google Fact Check client (`backend/apiReading/clients/google_fact_check.py`) and the planned EUvsDisinfo client (see `2026-11-21-004`). Each client returns normalized `Item.payload` dicts. All clients plug into `CLIENT_CLASSES` and run concurrently under `reader.read`.

Sources, in priority order:

| # | Client | Upstream | Auth | Category | Priority |
|---|--------|----------|------|----------|----------|
| 1 | `SejmEliClient` | https://api.sejm.gov.pl/eli (acts: Dz.U., M.P.) | none | `LEGAL_ACT` | high |
| 2 | `SejmApiClient` | https://api.sejm.gov.pl/sejm/term{N} (processes, prints, votings) | none | `LEGISLATIVE_PROCESS` | medium |
| 3 | `EurLexClient` | EUR-Lex web service (SOAP) / Cellar SPARQL | registered user (SOAP) / none (SPARQL) | `LEGAL_ACT` | medium |
| 4 | `DaneGovClient` | https://api.dane.gov.pl (CKAN-like JSON:API) | none or API key (verify) | `OPEN_DATA` | low |
| 5 | `PapClient` | PAP scraper (kernel-sqz/pap_open-api_scraper) | none | `NEWS` | low / risky |

ISAP (https://isap.sejm.gov.pl) has no separate API. Its data is served by the Sejm ELI API (`links` in responses point to `isap.nsf/DocDetails.xsp`). So ISAP is covered by client 1. Do not scrape the ISAP HTML.

## Findings from research

- **Sejm API**: confirmed keyless JSON. `GET /sejm/term10/processes?limit=1` returns items with `ELI`, `title`, `documentDate`, `processStartDate`, `passed`, `links` (isap, eli, eli-api). `GET /eli/acts/DU/2024` returns `{count, items:[{address, displayAddress, title, publisher, pos, status, promulgation, announcementDate, changeDate, textHTML, textPDF}]}`. Docs: https://api.sejm.gov.pl/API_pl.html. The ELI API has publisher/year listings, `/eli/acts/{publisher}/{year}/{pos}` details, `/text.html` and `/text.pdf`, and `/eli/acts/search` (verify the exact query parameters, such as `title`, `keyword`, `dateFrom`, `dateTo`, `publisher`, `limit`, `offset`).
- **PAP**: the repo is not an API. It is a FastAPI app that scrapes pap.pl on demand (multithreaded, endpoints like `/api`, `/api/en/world`). It has to be self-hosted, depends on pap.pl HTML (fragile), and there are terms-of-use and copyright questions. There is no search by text, only section listings.
- **EUR-Lex**: the page https://eur-lex.europa.eu/content/help/data-reuse/webservice.html describes a SOAP web service that needs a registered account (username and password, WS access request). Expert-query syntax is used for search. The user's pasted lines (~5) were not visible, so the exact EUR-Lex link is assumed. Alternative with no credentials: the Publications Office Cellar SPARQL endpoint (https://publications.europa.eu/webapi/rdf/sparql). **Decision needed.**
- **dane.gov.pl**: https://dane.gov.pl/pl, with an API under https://api.dane.gov.pl (docs at https://api.dane.gov.pl/doc). It is a catalogue of datasets and resources (metadata), not claim-level content. Useful for linking to statistics, less so for fact checking.
- Repo constraints (from the 004 plan and code): clients never read env vars. Keys come in via `api_keys[client.name]`. Wiring is manual in `backend/apiReading/reading.py:46-50`. `Category` currently has `FACT_CHECK` and `ARTICLE_EXTRACT` only (`models.py:12-16`). `BaseApiClient._request` retries GET only. `RequestSpec` supports `json` and `headers`. A SOAP call would need POST support (see risks). Ruff: line length 100, double quotes. Tests use respx and pytest-asyncio. `docs/solutions/` does not exist.
- The user said "the same as demagog right now". No Demagog client exists in the code. It only appears in tests (`test_reading.py`, `whatsapp_sim/.../test_whatsapp_bot.py`). Treat Google Fact Check (which carries Demagog-sourced claims) as the reference pattern.

## Phase 0 decisions and confirmed parameters

- Added `LEGAL_ACT`, `LEGISLATIVE_PROCESS`, `OPEN_DATA`, and `NEWS` categories. The category-driven `reader.read` selects clients by requested category; the existing higher-level `reading.run` continues to request only `FACT_CHECK` because it has no category-selection contract.
- Sejm ELI search uses `GET /eli/acts/search` with `title`, `dateFrom`, `limit`, and `offset`. `dateFrom` and exact direct lookup `GET /eli/acts/{publisher}/{year}/{position}` were confirmed live. References such as `Dz.U. z 2024 r. poz. 1984` resolve to direct lookup. Sejm ELI and Sejm process search are keyless; the process client uses term 10 as its default.
- EUR-Lex uses the public Cellar SPARQL endpoint with GET query parameters and `application/sparql-results+json`; live responses confirmed `cdm:resource_legal_id_celex`, `cdm:work_title`, `cdm:work_date_document`, and `cdm:work_has_resource-type`. User text is escaped as a SPARQL literal. The registered SOAP service remains deferred.
- dane.gov.pl uses keyless `GET /datasets` with `q`, `page`, and `per_page`; live responses confirmed JSON:API dataset rows, `links.next`, and `meta.count`.
- PAP is deferred from this implementation: the referenced project is a self-hosted scraper rather than a public API, and the licensing/terms question remains unresolved. `NEWS` is reserved without a registered source until that decision is revisited. No PAP scraper or configuration was added.
- No credentials or new settings are required for the four implemented clients. Existing Google Fact Check key handling remains unchanged.

## Open questions (resolve before or during phase 0)

1. **Categories.** Default: add `LEGAL_ACT`, `LEGISLATIVE_PROCESS`, `OPEN_DATA`, `NEWS` to `Category`. Does the reader's registry/aggregator work for categories beyond `FACT_CHECK`, and how does the pipeline (`reading.run`) pick categories? It currently requests only `FACT_CHECK`. Check `reader.py`, `registry.py`, `aggregator.py`, `full_text.py`, and `reading.py` before choosing. Alternative: keep everything under `FACT_CHECK` (no schema change), which is wrong semantically because laws are not fact checks.
2. **How statements map to legal searches.** Statements are free text claims. ELI search is keyword based, so we need a keyword/phrase extraction step (or a reference extractor for patterns like "ustawa z dnia", "Dz.U. 2024 poz. 1984"). Default: pass the statement through `ReadingRequest.query` and let the client truncate it. Add an optional regex-based act-reference extractor that does a direct lookup by `publisher/year/pos` (high precision, cheap).
3. **EUR-Lex transport:** SOAP with credentials, or SPARQL without? Default: SPARQL (no account, plain HTTP, fits `RequestSpec`), defer SOAP.
4. **PAP:** include at all? Default: defer to the last phase, behind the self-hosted URL setting `PAP_API_BASE_URL`, disabled if not set. Confirm licensing with the user.
5. **dane.gov.pl:** is an API key needed? Verify with https://api.dane.gov.pl/doc.

## Proposed solution

### Files

New:
- `backend/apiReading/clients/sejm_eli.py` — `SejmEliClient`
- `backend/apiReading/clients/sejm.py` — `SejmApiClient`
- `backend/apiReading/clients/eurlex.py` — `EurLexClient`
- `backend/apiReading/clients/dane_gov.py` — `DaneGovClient`
- `backend/apiReading/clients/pap.py` — `PapClient`
- `backend/apiReading/clients/_polish_legal.py` — shared helpers (act-reference regex, `Dz.U.` / `M.P.` parsing, ELI id building, HTML stripping, date normalization)
- `backend/apiReading/tests/test_sejm_eli.py`, `test_sejm.py`, `test_eurlex.py`, `test_dane_gov.py`, `test_pap.py`
- `backend/apiReading/tests/fixtures/{sejm_eli_search,sejm_eli_act,sejm_processes,eurlex_sparql,dane_gov_search,pap_list}.json` (real captured responses)

Changed:
- `backend/apiReading/models.py`: extend `Category` (see open question 1).
- `backend/apiReading/clients/__init__.py`: extend `CLIENT_CLASSES` and `__all__`.
- `backend/textAnalysis/settings.py`: optional `eurlex_username`, `eurlex_password` (only if SOAP), `dane_gov_api_key`, `pap_api_base_url`.
- `backend/.env.example`: add the matching variables.
- `backend/apiReading/reading.py:46-50`: build `api_keys` from all non-empty settings. Keyless clients need `api_key` to be optional. Check how `base.py` and `reader.py:18-109` treat a missing key. Today a missing key leads to `ApiAuthError`. Add a class flag such as `requires_api_key: ClassVar[bool] = True` in `base.py`, set to `False` for Sejm, ELI and SPARQL, and honor it in `reader.py`.
- Registry/reader tests that assert the client list.

### Client sketches (not final code)

```python
# backend/apiReading/clients/sejm_eli.py
class SejmEliClient(BaseApiClient):
    name = "sejm_eli"
    base_url = "https://api.sejm.gov.pl"
    supported_categories = frozenset({Category.LEGAL_ACT})
    requires_api_key = False
    max_page_size = 20

    def filters_from_request(self, request): ...  # query, max_age_days -> dateFrom, page_size
    def build_request(self, filters): ...         # GET /eli/acts/search, or /eli/acts/{pub}/{year}/{pos} if a reference was found
    def parse_response(self, response): ...       # {count, items[]} -> Items, next_cursor = offset
```

Payload (flat, keys always present; missing optional values are `None` or `[]`):

```
title, act_type, publisher ("DU"/"MP"), year, position, eli_id,
display_address ("Dz.U. 2024 poz. 1984"), status ("obowiązujący"/...),
promulgation_date, announcement_date, change_date (ISO 8601),
url_isap, url_text_html, url_text_pdf, source_name = "Sejm ELI / ISAP"
```

`Item.id` = `eli_<publisher>_<year>_<pos>`. Any shape violation raises `ApiResponseError`.

`SejmApiClient`: term is a filter (default: latest term, read from `/sejm/term` once and cached, or a config constant `10`). Payload: `title, number, print_numbers, process_start_date, passed, document_type, urls`. Lower priority because it answers "what happened with bill X".

`EurLexClient` (SPARQL variant): POST/GET a query to the Cellar endpoint with a text filter on titles (CELEX, title, date, type, in-force flag). Payload: `celex, title, doc_type, date, in_force, url_eurlex`. Escape user text in the query. Never interpolate raw input into SPARQL (injection).

`DaneGovClient`: search datasets (`/1.4/search?q=...` or the current version, verify). Payload: `title, notes, institution, url, modified, resources_count`.

`PapClient`: GET `{PAP_API_BASE_URL}/api` and filter by keyword client-side. Payload: `title, lead, url, published_at, section`. Requires `ARTICLE_EXTRACT` flow (Diffbot, plan 007) as an alternative for full text.

## Implementation phases

### Phase 0: Spike and decisions (0.5 day)
- Capture real responses for each upstream and save them as fixtures. Confirm the ELI search parameters, dane.gov.pl docs and EUR-Lex choice.
- Settle open questions 1-5. Read `reader.py`, `registry.py`, `aggregator.py` for category handling.
- Deliverable: updated plan section with confirmed parameters. **Completed** (see Phase 0 decisions above); PAP was deferred as planned pending licensing review.

### Phase 1: Foundation (0.5 day)
- Extend `Category`, add the `requires_api_key` flag, and let `reader.read` run keyless clients. Keep settings and `.env.example` unchanged while all implemented sources are keyless; retain the existing fact-check-only higher-level flow.
- Success: key-required clients retain authentication outcomes, keyless clients run without a key, and the Google client remains unchanged. **Completed**; settings and `.env.example` needed no changes because the implemented clients require no credentials.

### Phase 2: Sejm ELI + ISAP client (1 day)
- `_polish_legal.py` helpers, `SejmEliClient`, fixtures, tests.
- Success: a text query and a "Dz.U. 2024 poz. 1984" reference both yield normalized Items. **Completed**.

### Phase 3: Sejm legislative process client (0.5 day) — Completed

### Phase 4: EUR-Lex via SPARQL (1 day) — Completed

### Phase 5: dane.gov.pl (0.5 day) — Completed

### Phase 6: PAP (0.5 day, optional, gated on decision) — Deferred pending licensing/terms review

## Acceptance criteria

- [x] Each implemented client subclasses `BaseApiClient` and passes `__init_subclass__` checks.
- [x] Keyless clients work with no entry in `api_keys`. Keyed clients still return `ApiAuthError` outcomes without a key.
- [x] Clients never read env vars. No secrets are added to URLs or logs.
- [x] Output uses `Item` / `FetchResult`, with the flat payload shapes above and stable `Item.id`s.
- [x] Whitelisted, strictly typed filters (bool rejected as int). Invalid filters raise `InvalidFiltersError`. Malformed responses raise `ApiResponseError`.
- [x] Pagination maps to `page_token` / `next_cursor`, one page per `fetch_data` call.
- [x] One failing source does not block the others (partial results preserved).
- [x] Tests (respx): fixture success, empty result, pagination, unknown-act 404, 429 with Retry-After, malformed JSON, and URL secret checks.
- [x] `ruff check backend` and formatting checks pass; all `backend/apiReading/tests` pass. Repository-wide pytest remains blocked by pre-existing `articleScraping.local` import and `InputSanitizer` test/implementation mismatch.

## System-wide impact

- **Interaction graph:** `reading.run` -> `reader.read` -> `fetch_all` (gather) per statement. Each new client adds one concurrent call per statement per matching category. The number of calls per statement grows from 1 to up to 5. Watch rate limits and total latency (cap with the existing timeout).
- **Error propagation:** per-client isolation in `FetchOutcome`. No new exception types.
- **State lifecycle:** read-only, no persistence. The only state is the cached current term number (Sejm), which should have a safe fallback.
- **API surface parity:** downstream consumers of `Item.payload` (analysis, frontend, whatsapp_sim) assume the fact-check shape. Audit them, and make sure that per-source and per-category payloads do not break them. This is the main integration risk.
- **Integration tests:** (1) `read()` with respx mocks for Google plus Sejm ELI, one returning 500, expect a partial result. (2) A statement containing "Dz.U. 2024 poz. 1984" resolves to the direct lookup. (3) Keyless client with an empty `api_keys`.

## Risks and mitigation

- Pasted EUR-Lex lines were not visible, so the exact endpoint is an assumption (Phase 0 resolves it).
- Free-text statements give noisy keyword search results. Mitigate with the reference extractor and relevance ordering from upstream.
- PAP scraper fragility and copyright. Keep it optional and off by default.
- Polish legal text is large. Return metadata and links only, and fetch full text via the existing `full_text.py`/article flow if needed (verify its fit).
- Terms of use and attribution: keep `source_name` and `url` in every payload.

## Sources

- https://api.sejm.gov.pl/API_pl.html (checked live: `/sejm/term10/processes`, `/eli/acts/DU/2024`)
- https://isap.sejm.gov.pl/isap.nsf/home.xsp
- https://github.com/kernel-sqz/pap_open-api_scraper
- https://eur-lex.europa.eu/content/help/data-reuse/webservice.html
- https://dane.gov.pl/pl , https://api.dane.gov.pl/doc
- `backend/apiReading/base.py`, `clients/google_fact_check.py`, `models.py`, `reader.py`, `reading.py`, `backend/textAnalysis/settings.py`
- Related plans: `2026-11-21-001-...`, `2026-11-21-004-feat-euvsdisinfo-api-client-plan.md`, `2026-11-21-007-feat-diffbot-article-scraping-plan.md`
