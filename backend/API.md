# Browser API

The production app is `server:app` and exposes the browser check and feedback
routes. Run commands from the repository root:

```bash
python -m pip install -r requirements.txt
PYTHONPATH=backend:analysis:analysis/src uvicorn server:app --reload --port 8000 --no-access-log
```

The app requires `DATABASE_URL`, the LLM settings used by `textAnalysis` and
`analysis/inputDataAnalysis`, and the settings required by the enabled source
providers. `DATABASE_SSL_MODE` defaults to `verify-full`; use `disable` only for
a local database. When both are present, `DATABASE_SSL_MODE` overrides the
connection URL's `sslmode` parameter. `CORS_ORIGINS` is a comma-separated list
of exact browser origins. The deployment template is [`../render.yaml`](../render.yaml).

## HTTP endpoints

| Method | Path | Description |
| --- | --- | --- |
| `GET` | `/api/check?text=...` | Run a full synchronous analysis for text or a bare website URL. |
| `POST` | `/api/check/{id}/report` | Store feedback for a returned result ID. |
| `GET` | `/api/health` | Readiness check, including PostgreSQL connectivity. |
| `GET` | `/api/trusted-sources` | Enabled trusted sources from the `trusted_sources` table (edited in the admin panel), public fields only (`id`, `name`, `url`, `trust`, `topics`, `description`). Refreshed every minute; never the code list: without the database `503 sources_unavailable`. |
| `GET` | `/api/trusted-sources/{source_id}` | One enabled trusted source (404 for unknown or disabled, 503 without the database). |
| `*` | `/api/admin/...` | Admin panel API (sign-in required), see [Admin panel](#admin-panel-apiadmin). |
| `GET` | `/docs` | Interactive OpenAPI documentation. |
| `GET` | `/redoc` | ReDoc API documentation. |
| `GET` | `/openapi.json` | OpenAPI schema. |
| `GET` | `/docs/oauth2-redirect` | Swagger UI's OAuth redirect helper. |

The cleanup job is a Render cron task, not an HTTP endpoint.

## `GET /api/check?text=...`

Request:

```http
GET /api/check?text=A%20claim%20to%20check.
```

```bash
curl --get --data-urlencode 'text=A claim to check.' http://localhost:8000/api/check
```

Use URL encoding for the `text` query parameter. The same parameter accepts a
single bare HTTP(S) URL. URL input is validated before
analysis, and the verification flow fetches it using the article scraper's
SSRF-safe fetcher. Text limits are enforced by query validation. The endpoint
waits for the full verification result and returns the frontend `result` shape.
Responses set `Cache-Control: no-store` and `Referrer-Policy: no-referrer`.

Because GET places input in the URL, don't submit secrets or highly sensitive
text; browsers, proxies, or platform logs may record request URLs. The app and
Uvicorn access logger avoid logging the query itself.
Each request runs a fresh analysis and creates a new result ID; results are not
cached.

```json
{
  "status": "result",
  "id": "opaque-uuid",
  "input_type": "text",
  "claims": [
    {
      "verdict": "false",
      "text": "A claim to check.",
      "explanation": "Explanation.",
      "sources": [
        {
          "quote": "A verified excerpt.",
          "publisher": "Example Publisher",
          "url": "https://example.org/source",
          "year": "2025"
        }
      ]
    }
  ]
}
```

Only completed results are returned as `status: "result"` in the initial API.
`clarify` and `out_of_scope` are not generated until product rules are defined.
Partial analysis failures return errors instead of being presented as a complete
result. Query strings and feedback request bodies are limited to 96 KiB. Checks
are limited to four concurrent requests per process by default, and
`CHECK_TIMEOUT_SECONDS` defaults to 360 seconds; align the frontend's
`VITE_CHECK_TIMEOUT_MS` with it.

## `POST /api/check/{id}/report`

Request:

```json
{ "reason": "bad_source", "comment": "The link is broken." }
```

Allowed reasons are `wrong_verdict`, `bad_source`, `misunderstood`, and `other`.
`comment` is optional and limited to 1000 characters. A successful request
returns `204`. The first report for a result ID is stored; retries are
idempotent. Unknown or expired IDs return `404`.

The app creates `api_check_results` and `api_check_reports` from
[`database/migrations/0005_api_feedback.sql`](database/migrations/0005_api_feedback.sql) at startup
(idempotent; `python -m database migrate` applies the same file).
It stores result IDs, input type, report reason, and optional comment—not the
submitted text or full analysis. `REPORT_RETENTION_DAYS` defaults to 180 and is
configurable up to 3650 days. A submitted report extends its result ID's expiry
so the report is retained for at least the configured interval after submission.
The Render cron service deletes expired result rows daily; foreign-key cascade
removes their reports.

## Other implemented routers

`server:app` mounts only the two read-only `GET` routes above
(`public_sources.py`). The full router below fetches remote pages and calls the
LLM, so it is not exposed on the public browser API:

| Method | Path | Description / usage |
| --- | --- | --- |
| `GET` | `/api/trusted-sources?enabled_only=false` | List trusted sources; `enabled_only=true` filters disabled entries. |
| `GET` | `/api/trusted-sources/{source_id}` | Fetch one trusted-source record. |
| `POST` | `/api/trusted-sources/{source_id}/check` | Re-detect a trusted source's type. |
| `POST` | `/api/trusted-sources/search` | Search using `{"text":"..."}` or `{"queries":["..."]}`. |

The trusted-source router is mounted by the standalone WhatsApp adapter
(`python -m whatsappAdapter`). The WhatsApp routes are also served by `server:app`:

| Method | Path | Description / usage |
| --- | --- | --- |
| `GET` | `/api/whatsapp/health` | Return simulator status and mode. |
| `POST` | `/api/whatsapp/webhook` | Accept a WhatsApp-shaped JSON webhook payload and return handled messages. |
| `POST` | `/api/whatsapp/webhook?stream=true` | Same payload, returned as NDJSON progress events. |
| `GET` | `/api/whatsapp/docs` | Interactive simulator API docs. |

`WHATSAPP_ENABLED=false` removes them from `server:app`.

## Admin panel (`/api/admin`)

`server:app` also serves the admin panel API (`admin.api.mount_admin`), so the
panel and the website share one process and one database:

- Every `GET /api/check` is written to the panel's query journal (`user_queries`,
  channel `web`) with the submitted text, the claims and verdicts, and the
  number of cited sources. The journal entry ID is the result ID without dashes,
  so `POST /api/check/{id}/report` adds the reason and comment to the same entry
  (flag `zgloszenie:<reason>`); as in the API store, only the first report for
  a result reaches the entry, and later ones leave it unchanged. Entries are deleted after the panel's retention
  period (`monitoring.retention_days`).
- The same rules as for the WhatsApp bot apply: information gaps, possible
  disinformation campaigns and repeated dangerous queries raise alerts. A request
  for weapon or explosive instructions is refused (`422 request_refused`) and a
  client blocked in the panel gets `403 user_blocked`, both before the pipeline runs.
- A website client is known to the panel only by a pseudonym (HMAC of the client
  IP address, `ADMIN_USER_SALT`); the panel shows the last characters of the
  address. Behind a reverse proxy, run uvicorn with `--proxy-headers
  --forwarded-allow-ips=<proxy address>`, otherwise all clients share the proxy's
  address and a block would stop everyone.
- Model, API-key and threshold changes made in the panel apply to `/api/check`
  immediately; trusted-site changes reload the search registry.
- The panel itself (`admin_panel/frontend`) calls `/api/admin` on the same
  origin. The browser CORS policy above (`GET`/`POST`, no `Authorization`) is
  meant for the website, so serve the panel from the same domain or a proxy.

Journal failures never break a check: the entry is skipped and a warning is
logged. `ADMIN_PANEL=off` disables the panel routes and the journal.
Endpoint list: `backend/admin/README.md` and `/docs`.

## Error responses

Errors use a sanitized body and never include request bodies or provider
exceptions:

```json
{
  "error": { "code": "analysis_timeout", "message": "The analysis exceeded its time limit." },
  "request_id": "..."
}
```

The server rejects query strings and request bodies larger than 96 KiB before
validation.
Concurrent checks are bounded per API process; configure a gateway/per-client
rate limit before exposing the unauthenticated, provider-backed check endpoint
to public launch traffic.

| Status | Codes |
| --- | --- |
| `403` | `user_blocked` |
| `404` | `result_not_found` |
| `413` | `request_too_large` |
| `422` | `invalid_request`, `invalid_url`, `unsafe_url`, `url_unavailable`, `request_refused` |
| `502` | `analysis_failed`, `invalid_analysis_result` |
| `503` | `analysis_busy`, `storage_unavailable` |
| `504` | `analysis_timeout` |

`X-Request-ID` is returned for correlation. Submitted text, comments, full URLs,
credentials, and raw analysis results are not written to standard request logs
(the admin panel's query journal stores the text and report comments in the
database, see above).
Provider output logs counts and timings rather than claim text or search terms.

## Local tests

The API contract and store tests use fake analysis stages and an in-memory store;
they do not connect to PostgreSQL or external providers:

```bash
python -m pytest backend/tests/test_browser_api.py
```

To exercise a live local request, configure the existing database connection
and provider environment variables, then start the server as shown above. The
app applies the feedback schema at startup; it does not create a database
instance.
