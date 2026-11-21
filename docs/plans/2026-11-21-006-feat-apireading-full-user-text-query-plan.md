---
title: Add full-user-text query to apiReading (additive)
type: feat
status: completed
date: 2026-11-21
---

# feat: Add full-user-text query to apiReading (additive)

## Overview

Purely additive. Existing `apiReading.run(analysis)` (per-statement queries,
returns `list[ReadingResult]`) stays untouched. Add a NEW part that queries the
provider with the original text passed to `textAnalysis.run(text)`, which is
already stored on the container as `analysis.source_text`
(`backend/textAnalysis/container.py`).

## Proposed Solution

- `backend/apiReading/full_text.py` (new): `async def run_full_text(analysis) -> ReadingResult`
  - `text = analysis.source_text.strip()`; blank -> `ValueError("analysis must contain source text to search")`.
  - Build one `ReadingRequest(query=text[:MAX_QUERY_CHARS], categories=[Category.FACT_CHECK], language_code=analysis.language_code, page_size=10, metadata={"analysis_category": analysis.category, "truncated": len(text) > MAX_QUERY_CHARS})`.
  - Reuse `Settings.from_environment()` key handling, own an `httpx.AsyncClient`, call existing `reader.read()` once, and print redacted progress logs in the same `[apiReading]` style. Do not call `format_result` because it includes the query text.
  - Google does not document a query-length maximum; use a conservative application cap of 1,000 characters to bound the GET request URL.
- `backend/apiReading/__init__.py`: also export `run_full_text`
  (`__all__ = ["run", "run_full_text"]`).
- `backend/apiReading/README.md`: add a short section showing `apiReading.run_full_text(analysis)`.
- No changes to `reading.py`, `reader.py`, models, clients, or the smoke script
  (optional follow-up: `--full-text` flag in `scripts/smoke_pipeline.py`).

Shared helper duplication (key lookup, client lifecycle) is small; do not
refactor `run()` to share it, to keep the change additive.

## Tests

- `backend/apiReading/tests/test_full_text.py` (new), respx-mocked:
  - one request, `query == source_text`, `languageCode` and `key` params, single `ReadingResult`.
  - blank `source_text` raises `ValueError` matching "source text".
  - text over `MAX_QUERY_CHARS` is truncated and `metadata["truncated"] is True`.
  - statements present are ignored; `run()` behaviour unchanged (existing tests still pass).
  - missing API key -> auth error outcome, as in `run()`.
- `backend/apiReading/tests/test_reading.py`: update
  `test_api_reading_package_exports_only_its_entry_point` for the new `__all__`.

## Acceptance Criteria

- [x] `run()` behaviour and return type unchanged; all existing tests pass.
- [x] `run_full_text()` sends exactly one request with the user's full text.
- [x] Returns a single `ReadingResult`, per-source errors in `results`.
- [x] Blank text raises `ValueError`; over-long text truncated + flagged.
- [x] Logs never include the text or API key.
- [x] `pytest` and `ruff check` pass.

## Risks

- Long free-text queries may give poor recall from Google Fact Check; if so,
  a later step could fall back to per-statement queries.
- The entire user text is sent to a third party (statements already were
  derived from it); mention in README.

## Sources

- `backend/apiReading/reading.py` (pattern to mirror), `reader.py`, `models.py`
- `backend/textAnalysis/container.py` (`source_text`)
- `backend/apiReading/clients/google_fact_check.py` (query param handling)
