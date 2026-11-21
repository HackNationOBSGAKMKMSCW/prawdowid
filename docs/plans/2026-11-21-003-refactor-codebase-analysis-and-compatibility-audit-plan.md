---
title: Codebase analysis, working-state summary and compatibility audit
type: refactor
status: completed
date: 2026-11-21
---

# Codebase analysis, working-state summary and compatibility audit

## Overview

Prawdowid is a fact-checking / text-analysis project. It is a monorepo: a Python FastAPI backend (`backend/`) and a React + Vite frontend (`frontend/`), deployed on Vercel (`vercel.json`). The backend has three loosely related parts, and none of them are connected yet:

1. A **template CRUD API** (`backend/main.py`).
2. An **LLM text analyzer** (`backend/dataPreparation/analys.py` + `container.py`).
3. An **async multi-API reader** (`backend/dataPreparation/apiReading/`) that currently has one provider, Google Fact Check.

This document records the requested analysis of what works, what is incompatible or broken, and a project summary for follow-up design. The selected implementation work is recorded in the Execution Update below.

Method: reading all backend and frontend sources, `git log`, the earlier plans (`docs/plans/...001`, `...002`), and the graphify report. I tried running the tests, but they cannot run in this environment (see C1), so "works" is based on code reading, not on a passing test run. No `docs/brainstorms/` or `docs/solutions/` exist.

## 1. Project summary

### Architecture

```
frontend (React 19, Vite 8, TS 7)  --/api/*-->  backend (FastAPI, main.py)
   pages: Home, Items, ItemDetail,               - /api/health, /api/items CRUD (in-memory)
          About, NotFound                        - NOT wired to analysis or reader

backend/dataPreparation/
  analys.py      ProxyContextAnalyzer (OpenAI-compatible LLM, "FreeLLM")
                 -> InputSanitizer -> prompt -> JSON -> pydantic validation
                 -> AnalysisDataContainer (container.py)
  apiReading/    read(ReadingRequest) -> registry -> clients -> fetch_all (asyncio.gather)
                 -> ReadingResult(items, per-source FetchOutcome)
                 clients/google_fact_check.py (only client)
  dataReader/    empty directory
backend/dataAnalysis/test.py   empty file
```

### Intended data flow (inferred from names and history)

user text -> `analys.py` (category, keywords, statements) -> category selects the reader's `Category` -> reader fetches fact checks for the extracted statements -> compare / verdict -> frontend. Only the first two boxes exist. The glue (statement -> `ReadingRequest`, category mapping, HTTP endpoints, UI) does not exist.

### Module inventory

| Module | Lines | Role | State |
|---|---|---|---|
| `backend/main.py` | 58 | FastAPI app, `/api` router, demo item CRUD | Template code |
| `dataPreparation/analys.py` | 266 | Sanitizer, LLM analyzer, CLI `__main__` | Functional, untested |
| `dataPreparation/container.py` | 67 | `AnalysisDataContainer`, `KeywordItem` | Complete |
| `apiReading/base.py` | 253 | `BaseApiClient`: retries, backoff, Retry-After, timeouts | Complete |
| `apiReading/aggregator.py` | 44 | `fetch_all` concurrent gather | Complete |
| `apiReading/reader.py` | 109 | `read()` category-driven entry | Complete |
| `apiReading/registry.py` | 32 | category -> clients map | Complete |
| `apiReading/models.py` | 95 | `Category`, `ReadingRequest`, `Item`, `FetchResult`, `ReadingResult` | Complete |
| `apiReading/exceptions.py` | 61 | typed error hierarchy | Complete |
| `apiReading/clients/google_fact_check.py` | 157 | Google Fact Check client | Complete (1 provider) |
| `tests/test_api_reading.py`, `test_reader.py` | 392 + 210 | respx-based tests of the reader | Present; cannot run here |
| `frontend/src/**` | ~130 (pages) | Router + Items demo page | Template |
| `dataReader/`, `dataAnalysis/test.py` | 0 | Placeholders | Empty |

## 2. What is working

Based on code reading. Confirm with a green test run after fixing C1.

- **Async API reading layer** is the most mature part.
  - `BaseApiClient` handles timeouts, retries (GET only), exponential backoff capped at 30s, `Retry-After` parsing (capped at 60s), and typed errors for auth, rate limit, HTTP, response and connection failures.
  - `fetch_all` gives per-client failure isolation, and order is preserved.
  - `read()` validates the request, maps categories to clients, reports `categories_without_source`, turns missing API keys into per-source `ApiAuthError` outcomes, shares one `httpx.AsyncClient`, and returns timing.
  - The Google client maps provider-neutral fields (query, language, max age, page size capped at 20) and requests a trimmed field set.
- **Prompt-injection defense in the analyzer.** The input is length-limited (15,000 chars) and stripped of control characters. Regex heuristics flag known injection phrases in Polish and English. The input is wrapped in `<untrusted_text>` with closing-tag neutralization. A canary token is checked in the output. The output schema has length limits, and the category is checked against an allow-list with a fallback to "Ogólne / Inne" at confidence 0.
- **`AnalysisDataContainer`**: a typed result object with `is_safe`, `is_confident`, `keyword_terms`, `to_dict`.
- **FastAPI demo API** (`/api/health`, `/api/items` CRUD) works as a template, in memory only.
- **Frontend scaffold**: routing, a typed `api.ts` wrapper, a Vite proxy to `127.0.0.1:8000`.
- **Deployment config**: Vercel multi-service config with rewrites.
- **Tooling**: ruff, prettier, oxlint, editorconfig.

## 3. Compatibility and correctness problems

### Blockers

| # | Problem | Evidence | Impact |
|---|---|---|---|
| C1 | **Dependencies missing or not installed.** `.venv` contains only pip. System Python 3.14.4 lacks `httpx`, so test collection fails. | `python3 -m pytest` -> `ModuleNotFoundError: httpx`; `.venv/lib/*/site-packages` has only pip | Tests cannot run; nothing can be verified |
| C2 | **`requirements.txt` is incomplete.** `analys.py` imports `openai` and `python-dotenv`; neither is listed. The file is also unpinned (fastapi, uvicorn, httpx, pydantic>=2, pytest, pytest-asyncio, respx). | `analys.py:5-6` vs `requirements.txt` | `analys.py` crashes with ImportError on a clean install, and the Vercel deploy would break if it imports it |
| C3 | **Python 3.14 compatibility is unverified.** The only interpreter present is 3.14.4. `reader.py` uses `datetime.UTC` (3.11+), and `StrEnum` and `X \| None` syntax need 3.11+. There is no pinned Python version (`.python-version`, `pyproject`). | `models.py`, `reader.py` | Wheels for some dependencies (pydantic-core, openai) may lag on 3.14; Vercel's runtime may differ |
| C4 | **Dual-mode import hack in `analys.py`.** `try: from .container ... except ImportError: from container ...` is there only so `python analys.py` works. `dataPreparation` has no `__init__.py`, so it is a namespace package. | `analys.py:9-12`; `ls dataPreparation` | Import behavior depends on how it is launched; this is fragile and can mask real ImportErrors |

### Functional and design problems

| # | Problem | Evidence |
|---|---|---|
| F1 | **Nothing is integrated.** `main.py` does not import the analyzer or the reader. There is no `/api/analyze` or `/api/check` endpoint, and the frontend has no UI for either. | `main.py` |
| F2 | **Bug in `DELETE /api/test/{item_id}`.** The path parameter is `item_id`, but the function argument is `element: int`. FastAPI treats `element` as a required query parameter, so the path value is ignored. Leftover debug route. | `main.py:53-55` |
| F3 | **Blocking sync call inside an async-oriented stack.** `ProxyContextAnalyzer` uses the sync `OpenAI` client. If called from an async FastAPI handler it blocks the event loop; the reader side is fully async. | `analys.py:114`, `reader.py` |
| F4 | **Analyzer coupling and hardcoding.** The default `FREELLM_BASE_URL` is a private Tailscale-range IP (`http://100.115.139.118:3001/v1`), unreachable from Vercel or other machines. `model="auto"` is non-standard. `run_analysis` builds a new client on every call. No timeout, retry or error handling is set on the LLM call. | `analys.py:96-101, 232` |
| F14 | **Analyzer error handling is incomplete.** `model_validate_json` raises pydantic `ValidationError` on malformed or oversized LLM output, which is not caught. The sanitizer raises `ValueError`, which is only caught in the CLI. | `analys.py:211` |
| F15 | **Security heuristic limits.** Only the first matching pattern gets a warning (`break`). The pattern list is easy to bypass. A warning does not block the call; the text is still sent to the LLM. The canary leak check only looks at reasoning and statements, not at keywords. | `analys.py:65-69, 150-157` |
| F5 | **Category vocabularies do not match.** The analyzer's categories are Polish topic labels (Technologia, Zdrowie, Prawo...). The reader's `Category` enum has one value, `FACT_CHECK`, which is a source *type*, not a topic. No mapping exists between them. | `analys.py:84`, `models.py:15` |
| F6 | **Only one provider.** The "multi-API" reader has one client. Registry and aggregation are exercised only with a single source. | `clients/__init__.py` |
| F7 | **API keys are only supplied by the caller.** `read()` takes `api_keys`, but nothing loads them from the environment. The analyzer loads `.env` (`load_dotenv`) and the reader does not. Names are inconsistent (`FREELLM_API_KEY` vs a per-client key dict). | `reader.py:23`, `analys.py:16` |
| F8 | **Language gap.** The analyzer is Polish-centric (prompts, categories, regex), while Google Fact Check supports `language_code`. The analyzer does not detect or output language, so the reader cannot choose it. | n/a |
| F9 | **Items store is global mutable state.** The `items` list and the `max(id)+1` id scheme are not safe across multiple workers or serverless instances, and data is lost on restart. | `main.py:15` |
| F10 | **Dead and placeholder files.** `dataAnalysis/test.py` is empty (tracked) and `dataPreparation/dataReader/` is an empty untracked directory (git ignores empty dirs). Naming is inconsistent: `dataPreparation` vs `dataAnalysis` vs `dataReader`, Polish/English mixing, and `analys.py` is misspelled. | tree |
| F11 | **No tests for the analyzer or the API.** Only the reader has tests. No test for `main.py` and none for `InputSanitizer`, which is the security-critical part. | `tests/` |
| F12 | **`pytest.ini` is minimal.** `asyncio_default_fixture_loop_scope` is set but not `asyncio_mode`, and there is no `testpaths` or `pythonpath`. pytest printed an "Unknown config option" warning for `asyncio_default_fixture_loop_scope`, which is consistent with `pytest-asyncio` not being installed. Test imports depend on the cwd. | `pytest.ini` |
| F13 | **Repo hygiene.** `graphify-out/` (51 tracked files, including cache JSON) is tracked in git and changes on every run. `.idea/` is untracked. | `git status` |

### Frontend and deployment compatibility

| # | Problem | Evidence |
|---|---|---|
| D1 | **Frontend versions exist but peer compatibility is unchecked.** `npm view` confirms react 19.3.1, react-router-dom 7.18.6, vite 8.3.6, typescript 7.0.2, @vitejs/plugin-react 6.1.2 and oxlint 1.90.0 are published. Not yet checked: that `npm install` and `npm run build` succeed together (plugin-react 6 with vite 8 and TS 7). `package-lock.json` is present. | `package.json` |
| D2 | **Frontend is template-only.** The Items page calls the demo API; there is no analyzer UI. `api.ts` has no types for analysis or reader results. | `src/pages/*` |
| D3 | **Vercel config is unverified for the backend.** `entrypoint: "main:app"` with root `backend/` means the `dataPreparation` imports must resolve from `backend/`. The analyzer's fallback import, its private-IP LLM URL, and the missing `openai` dependency would all fail there. | `vercel.json` |
| D4 | **No CORS configuration** in FastAPI. This is fine with the Vite proxy and Vercel rewrites, but it breaks if the frontend is ever served from a different origin. | `main.py` |
| D5 | **Secrets handling.** `.env` is loaded but there is no `.env.example`. The Google API key and the FreeLLM key have no documented setup. | n/a |

## 4. Proposed next steps (ordered)

The work below is optional follow-up after you decide on the design.

### Phase 1: make it run (fixes C1-C4, F12)

- [x] Install the dependencies; record the Python version in `.python-version`.
- [x] Add `openai` and `python-dotenv` to `backend/requirements.txt`; split development dependencies into `requirements-dev.txt`.
- [x] Add `__init__.py` to `dataPreparation/`, remove the fallback import, rename `analys.py` to `analysis.py`, and make the module CLI async.
- [x] Configure pytest discovery, import paths, and asyncio mode in `pytest.ini`.
- [x] Run the existing reader tests and record the baseline result (38 passed).

### Phase 2: decide the contract (fixes F5, F7, F8)

- [x] Define the pipeline: analyzer statements -> `ReadingRequest.query`.
- [x] Keep analyzer topic labels as analysis metadata; `Category.FACT_CHECK` selects the source capability.
- [x] Add a detected language field to `AnalysisDataContainer` and pass it as `language_code`.
- [x] Centralize environment configuration in `Settings` with `.env.example`.

### Phase 3: integrate (fixes F1-F4, F9, F10)

- [x] Make the analyzer async (`AsyncOpenAI`) with timeout, retry, and handled `ValidationError`.
- [x] Add independent `POST /api/analyze` and `POST /api/check` endpoints; the latter accepts the analysis object.
- [x] Remove the demo item routes and debug route.
- [x] Remove the empty tracked `dataAnalysis/test.py` placeholder and rename `analys.py` to `analysis.py`.
- [ ] Add a second provider (deferred: no second API source was specified).

### Phase 4: frontend and deploy (fixes D1-D5)

- [ ] Verify `npm install && npm run build && npm run lint`.
- [ ] Replace the Items pages with an analyze/check page and typed API calls.
- [ ] Verify `vercel.json` with the real backend imports and environment variables.

### Phase 5: tests and hygiene (fixes F11, F13)

- [x] Add tests for `InputSanitizer`, `_validate_output_security`, async `ProxyContextAnalyzer` (mock OpenAI), and API endpoints.
- [x] Add an integration test: mocked analyzer -> real reader -> respx API response.
- [x] Add `graphify-out/` and `.idea/` to `.gitignore` and untrack generated graph data.

## Acceptance criteria

- [x] `pytest` runs green from the repo root on a fresh clone following documented steps.
- [x] `python -c "import main"` works from `backend/` after installing backend requirements.
- [x] Every remaining item in section 3 is fixed or explicitly deferred with a reason in the Execution Update.
- [x] One end-to-end path (text -> analysis object -> fact checks -> JSON) is covered across the two independent API endpoints.

## Execution Update

Executed on 2026-11-21 on branch `feat/independent-analysis-reading-api`. The user selected Phases 1, 2, 3, and 5 and clarified that this should remain an independently usable backend component with two operations: analyze text, then fetch API data using the resulting analysis object. Phase 4 (frontend and deployment) was not selected.

The analysis result now carries its topic category and detected language. `run_analysis()` returns that object; `run_api_reading()` accepts it and searches each extracted statement, preserving the topic label as metadata and passing the language to the provider. The HTTP endpoints expose those operations separately at `/api/analyze` and `/api/check`.

The second-provider item remains deferred because no additional API source was specified. Existing analyzer heuristic limitations (F15) and frontend/deployment findings (D1-D5) remain outside the selected implementation scope; Vercel and cross-origin behavior were not validated. These are deliberate scope decisions, not claims that those items were fixed.

Verification: 49 backend tests pass; `ruff check backend`, `ruff format --check backend`, and `python -c "import main"` from `backend/` pass. Python 3.14 dependency installation succeeded in the existing virtual environment.

## Dependencies and risks

- Python 3.14 wheel availability for pydantic-core and openai (C3).
- The FreeLLM endpoint is private; a hosted or configurable LLM is needed for deployment.
- A Google Fact Check API key is required; coverage of Polish claims is limited, so results may often be empty.
- LLM-extracted "statements" may not be good search queries. The quality of the mapping needs evaluation.

## Sources and references

- `backend/main.py:53`, `backend/dataPreparation/analys.py:9,84,96,211`, `backend/dataPreparation/apiReading/reader.py`, `models.py:15`
- `docs/plans/2026-11-21-001-feat-async-multi-api-fetcher-layer-plan.md`
- `docs/plans/2026-11-21-002-feat-category-driven-async-reader-plan.md`
- `graphify-out/GRAPH_REPORT.md` (core abstractions: `BaseApiClient`, `ReadingRequest`, `read()`, `GoogleFactCheckClient`)
