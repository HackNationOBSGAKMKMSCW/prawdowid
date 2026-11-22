-- Identyfikatory wyników z GET /api/check i zgłoszenia błędów z POST /api/check/{id}/report
-- (server.py, api_store.py). Bez treści sprawdzanej wiadomości i bez pełnego wyniku analizy.
-- Plik jest idempotentny: wykonuje go też api_store.PostgresStore.initialize() przy starcie API.

CREATE TABLE IF NOT EXISTS api_check_results (
    id         uuid PRIMARY KEY,
    input_type varchar(8) NOT NULL CHECK (input_type IN ('text', 'url')),
    created_at timestamptz NOT NULL DEFAULT now(),
    expires_at timestamptz NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_api_check_results_expires ON api_check_results (expires_at);

-- Jedno zgłoszenie na wynik (ON CONFLICT (result_id) DO NOTHING w api_store.save_report).
CREATE TABLE IF NOT EXISTS api_check_reports (
    result_id  uuid PRIMARY KEY REFERENCES api_check_results (id) ON DELETE CASCADE,
    reason     varchar(32) NOT NULL
        CHECK (reason IN ('wrong_verdict', 'bad_source', 'misunderstood', 'other')),
    comment    text CHECK (comment IS NULL OR char_length(comment) <= 1000),
    created_at timestamptz NOT NULL DEFAULT now()
);
