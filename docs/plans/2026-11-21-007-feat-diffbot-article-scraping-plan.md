---
title: "feat: Extract article content from collected links via Diffbot"
type: feat
status: active
date: 2026-11-21
---

## Execution Status

- Implementation and mocked verification are complete on `webScrapping`.
- The real-token Diffbot spike remains pending because `DIFFBOT_API_TOKEN` is not configured in this environment; `status` remains `active` until that external check is completed.
- Verification: `pytest` (104 passed, 1 live test deselected), `ruff check backend`, and `ruff format --check backend` pass.

# feat: Extract article content from collected links via Diffbot

## Enhancement Summary

**Deepened on:** 2026-11-21
**Agents used:** best-practices-researcher (Diffbot API verification, live probing), security-sentinel, architecture-strategist. No `docs/solutions/` learnings exist.

### Key corrections to the original plan
1. **`fields=` does NOT trim the response.** It only *adds* optional fields (`links`, `meta`, `quotes`, ...). `title`, `text`, `html`, `author`, `date`, `siteName`, `pageUrl`, `humanLanguage` come by default and there is no documented credit saving. Original Decision 3 is replaced: trimming happens client-side in `parse_response` (whitelist), and we send no `fields`; set `discussion=false` to skip comment extraction.
2. **Token must be a query param.** Live probes show the `Authorization` header is ignored. So token-leak controls (below) are mandatory, not optional.
3. **Error shapes are inconsistent.** Parse both `{errorCode, error}` and `{code, message}`; also defensively treat any 2xx with an error key or empty `objects` as an error. Never echo Diffbot's error string into exceptions.
4. **Rate limits:** free tier 5 calls/min (10k/month); Startup 5/s; Plus 25/s. Default `max_concurrency=1` on free tier (configurable).
5. **Architecture simplification** (see "Revised design decisions").

### New considerations
- Credit burn from user-supplied links is the main abuse vector.
- Streaming byte cap, batch deadline, and abort-batch on auth/429.
- `resolvedPageUrl` is untrusted output and must be validated.

## Update 2 (2026-11-21): Output contract, run metadata, three-stage pipeline, SOLID

This section **supersedes** earlier "Models", "Public API" and "File Layout" sections where they conflict.

### Final output structure

Backend only (no web/UI work). The scraping stage returns one envelope; `started_at` and `user_text` come first.

```python
# backend/articleScraping/models.py
class ScrapedArticle(BaseModel):
    url: str                       # link of article (requested; resolved URL kept internally only if validated)
    title: str | None              # name of article
    author: str | None             # writer
    published_at: datetime | None  # date and time of publication (parsed from Diffbot RFC 1123 `date`; fall back to None, never to `estimatedDate`)
    text: str                      # article text only (no HTML)
    truncated: bool = False

class ArticleFailure(BaseModel):   # per-link failure, safe to serialise (no token, no cause)
    url: str
    kind: str                      # e.g. InvalidUrl, NotAnArticle, RateLimited, Timeout
    status_code: int | None = None

class ScrapingReport(BaseModel):   # field order = serialised order
    started_at: datetime           # when the user submitted the text (timezone-aware UTC)
    user_text: str                 # the full, unmodified text the user wrote in the app
    articles: list[ScrapedArticle] # multiple articles
    failures: list[ArticleFailure]
    finished_at: datetime
```

Example JSON:

```json
{
  "started_at": "2026-11-21T10:15:02.123Z",
  "user_text": "<exact text typed by the user>",
  "articles": [
    {"url": "https://...", "title": "...", "author": "...",
     "published_at": "2026-11-18T08:00:00Z", "text": "...", "truncated": false}
  ],
  "failures": [],
  "finished_at": "2026-11-21T10:15:09.480Z"
}
```

Rules: `articles` contains only successfully extracted articles with non-empty `text`; `published_at` is timezone-aware (Diffbot `date` is RFC 1123 GMT; parse with `email.utils.parsedate_to_datetime`); `user_text` is the original input, **not** the trimmed/sanitised version and **not** truncated (the 1000-char truncation in `full_text.py` applies to provider queries only). Because it contains user data, it must never be logged (existing convention).

### Run metadata flows through the whole pipeline

`started_at` must be captured at the moment the user submits text, i.e. at the first stage, and carried forward:

- Add to `AnalysisDataContainer` (`backend/textAnalysis/container.py`) a `started_at: datetime | None = None` field (UTC-aware); `source_text` already holds the user text but is the *sanitised* text, so also add `original_text: str = ""` set verbatim before sanitisation. Extend `populate(...)` with both (keyword args, defaults preserve current callers/tests).
- `textAnalysis.run(text, *, started_at: datetime | None = None)` (`backend/textAnalysis/analysis.py:300`): if the caller (the app) passes the submit time, use it; otherwise stamp `datetime.now(UTC)` on entry. `original_text = text`.
- Open question (non-blocking): the app should pass its own submit timestamp when it has one; the default stamp is the fallback.

### Three stages, three functions (single responsibility, one entry point each)

| Stage | Function | Input | Output |
|---|---|---|---|
| 1. Analysis | `textAnalysis.run(text, *, started_at=None)` | user text | `AnalysisDataContainer` (now with `started_at`, `original_text`) |
| 2. API reading | `apiReading.run(analysis)` (existing, unchanged signature) | `AnalysisDataContainer` | `list[ReadingResult]` |
| 3. Web scraping | `articleScraping.run(analysis, reading_results)` | analysis + results | `ScrapingReport` |

Each stage is callable on its own; the caller (host app / `scripts/smoke_pipeline.py`) chains them: `analysis = await textAnalysis.run(text)`; `results = await apiReading.run(analysis)`; `report = await articleScraping.run(analysis, results)`. No stage imports a later stage; stage 3 depends on the *data shapes* of 1 and 2 only. No orchestrating mega-function is added (the smoke script is the only chaining code, extended to print/serialise the report).

### SOLID design for `articleScraping`

- **S - Single responsibility**: separate small modules, each with one reason to change:
  - `links.py` - `LinkExtractor` (find candidate URLs from analysis text and reading results)
  - `url_validation.py` - `validate_url` / canonicalisation
  - `diffbot.py` - `DiffbotArticleClient` (HTTP + response whitelist only)
  - `mapping.py` - Diffbot payload -> `ScrapedArticle` (date parsing, truncation, text normalisation)
  - `service.py` / `__init__.py` - `run()` orchestration and per-link failure isolation
  - (This reverses the earlier "collapse scraper.py" suggestion: orchestration, mapping and validation have different reasons to change.)
- **O - Open/closed**: link sources implement a `LinkSource` Protocol (`extract(analysis, results) -> list[CandidateLink]`) with `TextLinkSource` and `FactCheckLinkSource`; add a new source without editing existing ones. Scraper providers implement an `ArticleExtractor` Protocol (`async extract(url) -> RawArticle`); Diffbot is one implementation.
- **L - Liskov**: every `ArticleExtractor` raises only the shared `ApiReadingError` family (or returns a `RawArticle`); callers never special-case Diffbot. Resolve the `BaseApiClient.filters_from_request` smell: `DiffbotArticleClient` must not raise `NotImplementedError` in a way callers hit; it is never reached through the registry, and a test pins that. (If this still feels like an LSP violation during implementation, split a minimal `HttpApiClient` base from `BaseApiClient` instead.)
- **I - Interface segregation**: small Protocols (`LinkSource`, `ArticleExtractor`, `Clock`) rather than one fat interface; `run()` depends only on what it uses.
- **D - Dependency inversion**: `run()` takes optional injected collaborators with defaults:

```python
async def run(
    analysis: AnalysisDataContainer,
    reading_results: Sequence[ReadingResult] = (),
    *,
    extractor: ArticleExtractor | None = None,    # default: DiffbotArticleClient from Settings
    link_sources: Sequence[LinkSource] | None = None,
    clock: Clock = SystemClock(),
) -> ScrapingReport
```

  Tests inject fakes (no respx needed for orchestration tests); settings/token are read only in the default factory.

The same principles apply to the edits in stages 1 and 2: additions are additive (new optional fields/params with defaults), existing signatures and tests keep working.

### Updated file layout

- `backend/articleScraping/__init__.py` (exports `run`)
- `backend/articleScraping/models.py`, `protocols.py`, `links.py`, `url_validation.py`, `diffbot.py`, `mapping.py`, `service.py`, `README.md`
- `backend/articleScraping/tests/`: `test_links.py`, `test_url_validation.py`, `test_diffbot.py`, `test_mapping.py`, `test_service.py`
- edit `backend/textAnalysis/container.py` (`started_at`, `original_text`), `backend/textAnalysis/analysis.py` (`run(..., started_at=None)` populates them), `backend/textAnalysis/settings.py`, `backend/apiReading/models.py`, `backend/.env.example`, `backend/scripts/smoke_pipeline.py`, `backend/README.md`
- tests for stage-1 additions in `backend/textAnalysis/tests/test_analysis.py`

### Additional acceptance criteria

- [x] `ScrapingReport` serialises with `started_at` then `user_text` first, then `articles` (each with `url`, `title`, `author`, `published_at`, `text`), then `failures`, `finished_at`
- [x] `started_at` is timezone-aware UTC and equals the time passed to `textAnalysis.run` (or the stamp at its entry when omitted)
- [x] `user_text` equals the exact original input (verbatim, untruncated, unsanitised) and is never printed/logged
- [x] Stages run independently via three separate functions; no stage imports a later one; existing `textAnalysis`/`apiReading` tests pass unchanged
- [x] `run()` works with injected fake `ArticleExtractor`/`LinkSource`/`Clock` (no network, no settings)
- [x] `published_at` is `None` (not guessed) when Diffbot has no `date`; `author`/`title` may be `None`
- [x] A new link source or extractor can be added without modifying `service.py`

## Overview

Add a step to the backend pipeline that (1) collects website links from the two
existing sources, the text analysis (`textAnalysis`) and the API reading
(`apiReading`), (2) sends each unique link to the Diffbot Extract **Article** API,
and (3) returns only the article body plus a small set of metadata. No raw HTML,
images, sentiment, tags or other Diffbot fields are returned.

## Problem Statement / Motivation

`apiReading` currently returns fact-check claims whose `claimReview[].url` points
to the full fact-check article, but the pipeline never reads those articles. The
user's text may also contain links. To verify claims we need the article text
behind those links, not just the URL. Diffbot's Extract API does rule-free
article extraction, so we avoid writing scrapers.

## Research Summary

No brainstorm doc and no `docs/solutions/` exist, so there are no prior
learnings. Local patterns were read directly (external research agents were not
needed beyond the Diffbot docs; the docs site is an SPA, so the endpoint details
below come from Diffbot's documented v3 Article API and **must be verified
against a live call in Phase 1**).

Local conventions to follow:

- `backend/apiReading/base.py`: `BaseApiClient` supplies async httpx, retries
  (GET only; 429/502-504), concurrency semaphore and error mapping to
  `ApiReadingError` subclasses (`backend/apiReading/exceptions.py`). It
  requires `name`, an HTTPS `base_url` and a non-empty `supported_categories`
  frozenset of `Category`.
- `backend/apiReading/clients/google_fact_check.py`: reference client
  (`build_request`, `filters_from_request`, `parse_response`; items hold the raw
  API payload; stable hashed IDs).
- `backend/apiReading/registry.py`: builds category -> client from
  `CLIENT_CLASSES` in `backend/apiReading/clients/__init__.py`.
- `backend/apiReading/full_text.py` / `reading.py`: entry points take an
  `AnalysisDataContainer`, read keys via `Settings.from_environment()`
  (`backend/textAnalysis/settings.py`), print `[apiReading]` progress logs in
  Polish and never log user text.
- `backend/textAnalysis/container.py`: `AnalysisDataContainer` has `source_text`,
  `statements`, `keywords`, etc. Currently **no link field**.
- Tests: `respx` + `pytest-asyncio` under `backend/<pkg>/tests/`.
  `backend/scripts/smoke_pipeline.py` is the manual end-to-end runner.

Diffbot Article API (to verify):

- `GET https://api.diffbot.com/v3/article?token=<TOKEN>&url=<ENCODED_URL>`
- Optional params: `fields` (restrict output), `timeout` (ms), `discussion=false`,
  `paging=false`, `maxTags`.
- Response: `{"request": {...}, "objects": [{type, title, text, html, author,
  authors, date, estimatedDate, siteName, pageUrl, resolvedPageUrl,
  humanLanguage, ...}]}`; errors are `{"error": "...", "errorCode": N}`
  (HTTP 401 bad token, 429 rate limit, 404 could not download page, 500
  extraction failures; docs list 457 invalid API).
- Auth is a query-string token, so the token appears in the request URL.

## Proposed Solution

A new package `backend/articleScraping/` that is **separate from the
fact-check search flow** (it is not a "category search by query"), but reuses
`BaseApiClient` and the existing exception hierarchy for HTTP behaviour.

```
analysis (textAnalysis) --+
                          +--> link_extractor --> unique URLs --> DiffbotArticleClient
apiReading results -------+                                        (concurrent, per-URL outcome)
                                                                        |
                                                                        v
                                                         list[ScrapedArticle | ScrapeError]
```

### Decisions

1. **Where links come from**
   - From `apiReading` results: every `claimReview[].url` in `Item.payload`
     (Google Fact Check shape; written generically so future clients with a
     `url` key can be added).
   - From text analysis: `http(s)://` URLs found in `analysis.source_text`
     with a regex. Do **not** modify the LLM analysis schema (`_ApiAnalysisSchema`);
     link detection is deterministic and avoids prompt-injection-controlled
     URLs coming from the model.
   - Deduplicate after normalisation (lowercase scheme/host, strip fragment,
     strip trailing punctuation such as `.,)`). Cap at `MAX_LINKS` (default 10).
2. **Client reuse**: `DiffbotArticleClient(BaseApiClient)` with
   `name = "diffbot_article"`, `base_url = "https://api.diffbot.com"`.
   `BaseApiClient.__init_subclass__` demands a `Category`, so add
   `Category.ARTICLE_EXTRACT` to `backend/apiReading/models.py`. The client is
   **not** added to `CLIENT_CLASSES`, so `reader.read()` never selects it and
   existing behaviour is unchanged.
3. **Output = article only + metadata.** (Superseded: `fields=` does not trim output; see Research Insights.) Map to a strict whitelist in `parse_response` so no extra fields leak.
4. **Failure isolation**: per-URL outcomes (like `FetchOutcome`); one failing
   link does not fail the batch. Pages Diffbot cannot classify as an article
   (`objects[0].type != "article"`, empty `text`) yield a typed
   `NotAnArticleError` outcome.
5. **No LLM / analysis of scraped text in this feature.** Scraped text is
   untrusted; downstream consumers must run it through `InputSanitizer` before
   any LLM use (noted in README).

### Models (`backend/articleScraping/models.py`)

```python
class ArticleMetadata(BaseModel):
    url: str                     # requested URL
    resolved_url: str | None     # after redirects (resolvedPageUrl / pageUrl)
    title: str | None
    author: str | None
    published_at: str | None     # Diffbot date string, kept as-is
    site_name: str | None
    language: str | None         # humanLanguage

class ScrapedArticle(BaseModel):
    metadata: ArticleMetadata
    text: str                    # article body only, truncated to MAX_ARTICLE_CHARS

class ScrapeOutcome(BaseModel):
    url: str
    article: ScrapedArticle | None = None
    error: ApiReadingError | None = None   # serialised like FetchOutcome

class ScrapeResult(BaseModel):
    outcomes: list[ScrapeOutcome]
    skipped_urls: list[str]      # invalid/blocked/over cap
    fetched_at: datetime
    duration_ms: int
```

### Public API

```python
# backend/articleScraping/__init__.py
async def run(
    analysis: AnalysisDataContainer,
    reading_results: list[ReadingResult] | None = None,
) -> ScrapeResult
async def scrape_urls(urls: list[str], *, api_key: str, http_client=None) -> ScrapeResult
```

`run()` = extract links -> `scrape_urls()`. Reads `DIFFBOT_API_TOKEN` through
`Settings`; missing token -> `ApiAuthError` outcomes (same convention as
`read()`), not a crash.

## File Layout

- `backend/articleScraping/__init__.py` - exports `run`, `scrape_urls`
- `backend/articleScraping/models.py` - models above
- `backend/articleScraping/links.py` - `extract_links(analysis, reading_results)`, normalisation, SSRF filter
- `backend/articleScraping/diffbot.py` - `DiffbotArticleClient`
- `backend/articleScraping/scraper.py` - `scrape_urls`, `run`, concurrency
- `backend/articleScraping/README.md`
- `backend/articleScraping/tests/test_links.py`
- `backend/articleScraping/tests/test_diffbot.py`
- `backend/articleScraping/tests/test_scraper.py`
- edit `backend/apiReading/models.py` (add `Category.ARTICLE_EXTRACT`)
- edit `backend/textAnalysis/settings.py` (add `diffbot_api_token`)
- edit `backend/.env.example` (`DIFFBOT_API_TOKEN=`)
- edit `backend/scripts/smoke_pipeline.py` (optional `--scrape` flag)
- edit `backend/README.md` (document the step)

## Research Insights (deepening)

### Verified Diffbot facts (source: https://www.diffbot.com/docs/article, /authentication, /rate-limits, /credits, /extract/errors/*)
- `GET https://api.diffbot.com/v3/article?token=&url=`; optional `timeout` (ms, default 30000), `discussion=false`, `paging` (default false), `maxTags`, `naturalLanguage`. Max request duration 180s.
- Only one object returned; use `objects[0]`, require `type == "article"` and non-empty `text`.
- `date` is RFC 1123 string; `author` / `date` may be absent; `resolvedPageUrl` only present after redirects; `siteName` falls back to root domain; `humanLanguage` is ISO 639-1.
- 404 = target site could not be downloaded (not our fault, do not retry); 429 = per-second plan limit (wait >= 1s); 500 variants = target throttling or internal error. 1 credit/page, 2 with Diffbot proxy; whether failed calls are billed is **unverified** (assume yes).
- Responses are sometimes cached by Diffbot (possibly stale).

### Revised design decisions (supersede earlier ones where they conflict)
- **Keep `BaseApiClient` reuse**, but treat `Category.ARTICLE_EXTRACT` as internal/non-searchable: document it, implement `filters_from_request` to raise `NotImplementedError`, and add tests: `clients_for_categories([ARTICLE_EXTRACT]) == ([], [ARTICLE_EXTRACT])`, `read()` with it raises `NoSourcesAvailableError`, and `CLIENTS_BY_CATEGORY[FACT_CHECK]` is unchanged. (Alternative if this feels hacky: relax `__init_subclass__`; rejected as more churn.)
- **Trim in `parse_response`**: build `Item.payload` from a whitelist (title, text, author, date, siteName, pageUrl, resolvedPageUrl, humanLanguage) so raw HTML never travels further; `scraper.py` maps it to `ScrapedArticle`.
- **One outcome type**: reuse `FetchOutcome` style or keep `ScrapeOutcome`, but represent invalid/unsafe URLs as outcomes with an `InvalidUrlError` (drop the separate `skipped_urls`). `NotAnArticleError` becomes a subclass of `ApiResponseError`.
- **Collapse** `scraper.py` into `__init__.py` unless it grows; defer `--scrape` smoke flag and success-metric timing (not testable with respx).
- **Share one client instance** across URLs so `max_concurrency` (semaphore is per instance) is effective.
- Add `truncated: bool` to `ScrapedArticle` (was mentioned in prose but missing from the model).
- Settings: store token as secret-safe value; `Settings` lives in `textAnalysis/settings.py` per existing convention (note the coupling). Existing `InputSanitizer` in `backend/textAnalysis/analysis.py` is the sanitizer downstream consumers should use on scraped text.

### Security requirements (P0/P1 from review)
- **Token leakage:** httpx exceptions carry the request URL with `token=`. In the Diffbot client wrap `fetch_data`/`_request` errors: set `cause=None`, `raise ... from None`; define a client `__repr__` that redacts the key; set `logging.getLogger("httpx")`/`httpcore` to WARNING (httpx logs full URLs at INFO); never serialise `cause`. Tests: force `ConnectError`/`TimeoutException` and assert token absent from `str`, `repr`, `traceback.format_exception`, `caplog`, `capfd` and `model_dump`.
- **URL validation (`validate_url`, table-driven tests):** catch `ValueError` from `urlsplit`; reject control chars/whitespace/backslash, length > 2048, non-http(s), any userinfo (`@`), ports other than 80/443, single-label and `localhost`/`.local`/`.internal`/`.lan` hosts; strip trailing dot; reject IP literals outright (covers decimal/hex/octal forms and IPv4-mapped IPv6) ; canonicalise host via IDNA and dedupe on the canonical form; drop fragment and default port; balance parentheses before stripping trailing punctuation. Pass URL only via `params={"url": ...}` (test with a URL containing `&token=x`, `#`, `%`). Note: Diffbot fetches the page, so this protects credits and hygiene more than our network.
- **Credit-burn controls:** trust tiers: fact-check `claimReview.url` first, then user-text links under a smaller cap; default `MAX_LINKS` 5 (user-text sub-cap 2); `ARTICLE_SCRAPING_ENABLED` kill switch; short-TTL in-memory cache of normalised URL including negative results; cap regex input length and match count before dedupe; `max_retries` for this client = 1 (retry only 429/502-504; never 404/500); abort the remaining batch on first `ApiAuthError` or exhausted 429; per-batch deadline via `asyncio.timeout`.
- **Response size:** stream with a byte cap (e.g. 2 MB) via a `_send` override; use only `objects[0]`; truncate `text` (50k chars), title (300), author (200).
- **Untrusted output:** normalise text (NFKC, strip control/zero-width/bidi chars); mark `ScrapedArticle` as untrusted; validate `resolvedPageUrl` with `validate_url` before exposing; add provenance `source: "user_text" | "fact_check"` to each outcome; fixture containing "ignore previous instructions" must pass through as inert data. Downstream: scraped text only in delimited data blocks, never in system prompts.
- Ensure `follow_redirects=False` on our httpx client (pin in a test).

### Phase 1 spike additions
Confirm with a real token: whether failed calls consume credits, actual HTTP status for extraction failures, whether any 200-with-error occurs, and cost of multi-page articles.

## Technical Considerations

- **Security (high-risk: external API + user-supplied URLs):**
  - Diffbot fetches the URL from its servers, so classic SSRF against our
    network is not the risk, but still reject non-`http(s)` schemes, URLs with
    credentials (`user:pass@`), `localhost`, and IP-literal private/loopback
    ranges before spending credits.
  - Token is a query parameter: never log the request URL or `repr` httpx
    errors (existing code logs only `self.name`; keep it so). Make sure
    `ApiReadingError.cause` is not printed anywhere. Redact `token=` in any
    debug output.
  - Scraped text is untrusted content (prompt-injection vector) - do not feed to
    the LLM unsanitised.
  - Log URL hosts only, not full URLs/paths, to match the "never log user
    text" convention.
- **Cost/rate limits:** Diffbot bills credits per extraction. Enforce
  `MAX_LINKS`, dedupe, and `max_concurrency` (default 3) via the base
  semaphore. 429 handling comes from `BaseApiClient` (honours `Retry-After`).
  Check the plan's rate limit in Phase 1 and tune the default.
- **Timeouts:** Diffbot can take 10-30 s on slow pages. Use `timeout=30` on the
  client and pass Diffbot's own `timeout` (ms) slightly lower.
- **Size:** truncate `text` to `MAX_ARTICLE_CHARS` (default 50_000) and flag
  `truncated` in metadata if cut.
- **Retries:** extraction is GET, so base retries apply; do not retry 404
  (could not download) or 5xx extraction failures beyond base rules, since
  each retry may cost credits.
- **Polish log style:** `[articleScraping] ...` progress messages matching
  existing prints.

## System-Wide Impact

- **Interaction graph:** `run()` -> `extract_links` -> `scrape_urls` ->
  `DiffbotArticleClient.fetch_data` -> `BaseApiClient._request`. No callbacks
  or side effects outside HTTP.
- **Error propagation:** Diffbot's JSON `error`/`errorCode` can arrive with
  HTTP 200 on some paths; `parse_response` must map them to `ApiHttpError`/
  `ApiAuthError`/`ApiResponseError`. Per-URL errors are captured in
  `ScrapeOutcome`, never raised from `run()` except for programming errors.
- **State lifecycle:** stateless; no persistence. Partial failure just yields
  a mix of articles and errors.
- **API surface parity:** `Category` gains a member; `registry.py` builds
  `CLIENTS_BY_CATEGORY` over all categories, so `ARTICLE_EXTRACT` maps to an
  empty tuple and `read()` on it would raise `NoSourcesAvailableError` - add a
  test pinning this.
- **Integration scenarios:** see Testing.

## Acceptance Criteria

- [ ] `extract_links` returns de-duplicated, normalised http(s) URLs from
      `source_text` and from `claimReview[].url` in reading results, capped at `MAX_LINKS`
- [ ] Invalid/unsafe URLs (non-http, credentials, localhost/private IPs) are
      returned in `skipped_urls` and never sent to Diffbot
- [ ] `DiffbotArticleClient` calls `GET /v3/article` with `token`, `url`, `discussion=false`
- [ ] Output contains only `text` + `ArticleMetadata`; no HTML or other Diffbot fields
- [ ] Missing token yields `ApiAuthError` outcomes, not an exception
- [ ] One failing URL (404, 429 after retries, non-article page, timeout) does
      not affect others
- [ ] Token never appears in logs, exceptions' `str()`, or serialised results
- [ ] Existing `apiReading` and `textAnalysis` tests still pass; `reader.read()`
      behaviour unchanged
- [ ] Token absent from exception chain, repr, `caplog`, `capfd` and serialised results
- [ ] Response read with byte cap; batch has an overall deadline; auth/429 aborts remaining batch
- [ ] Table-driven `validate_url` tests cover IP forms, userinfo, IDN, ports; `resolvedPageUrl` validated
- [ ] Per-request link caps, kill switch and URL cache in place
- [ ] `CLIENTS_BY_CATEGORY[FACT_CHECK]` unchanged; `read()` with `ARTICLE_EXTRACT` raises `NoSourcesAvailableError`
- [ ] `ruff check` and `pytest` pass

## Testing (respx, no real network)

- `test_links.py`: URL regex with trailing punctuation, dedupe by normalisation,
  fragment stripping, cap, unsafe URL rejection, payload with missing/None
  `claimReview`.
- `test_diffbot.py`: request params (token, url, fields); parse a happy-path
  fixture; empty `objects`; `type != article`; 200-with-`errorCode`; 401 ->
  `ApiAuthError`; 429 with `Retry-After`; 404; timeout; assert token not in
  `str(error)` or `model_dump`.
- `test_scraper.py`: mixed batch (one success, one 404, one non-article) returns
  three outcomes in input order; concurrency limit respected; missing token.
- Integration scenario: fact-check `ReadingResult` fixture -> `run()` -> articles
  list, end to end with mocked Diffbot.
- Optional live smoke via `scripts/smoke_pipeline.py --scrape` (requires real
  `DIFFBOT_API_TOKEN`; not run in CI).

## Implementation Phases

1. **Spike (small):** one real Diffbot call to confirm endpoint, `fields`
   syntax, error shape, rate limit and credit cost; save sanitised fixtures
   to `backend/articleScraping/tests/fixtures/`.
2. **Foundation:** models, settings/env, `Category.ARTICLE_EXTRACT`,
   `links.py` + tests.
3. **Client:** `diffbot.py` + tests.
4. **Orchestration:** `scraper.py`, `__init__.py`, smoke flag, READMEs.

## Dependencies & Risks

- Needs a Diffbot account/token (free trial has limited credits).
  Mitigation: tests fully mocked.
- Docs verified via https://www.diffbot.com/docs/ pages and live probes; Phase 1 spike still needed to confirm billing of failed calls.
- Paywalled or JS-heavy pages may return empty text -> reported as
  `NotAnArticleError`, not retried.
- Fact-check publisher URLs are the main link source; if the user's text has
  no URLs and there are no fact-check results, `run()` returns an empty result.
- Open question (non-blocking): should links found only in `source_text` be
  trusted equally to publisher URLs from fact-check APIs? Plan treats both
  the same, with the same safety filter.

## Success Metrics

- For a fact-check result set, >= 80% of article-type URLs yield non-empty text.
- Zero token leaks in log/serialisation tests.
- Batch of 10 URLs completes within ~35 s at concurrency 3.

## Sources & References

- Diffbot docs: https://docs.diffbot.com/ (Extract API -> Article, Errors, Rate Limits, Credits)
- Base client: `backend/apiReading/base.py`
- Reference client: `backend/apiReading/clients/google_fact_check.py`
- Registry: `backend/apiReading/registry.py`
- Settings: `backend/textAnalysis/settings.py`
- Earlier plans: `docs/plans/2026-11-21-001-feat-async-multi-api-fetcher-layer-plan.md`,
  `docs/plans/2026-11-21-006-feat-apireading-full-user-text-query-plan.md`
