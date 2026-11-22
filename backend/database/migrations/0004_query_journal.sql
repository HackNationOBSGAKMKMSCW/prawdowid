-- Dziennik zapytań użytkowników i reguły czujności panelu admina (backend/admin).
-- Osoby piszące do serwisu (np. przez WhatsApp) są pseudonimizowane (end_users.user_key);
-- zapytanie zalogowanego konta ma dodatkowo account_id.

CREATE TABLE IF NOT EXISTS end_users (
    user_key      varchar(64) PRIMARY KEY,
    label         varchar(32),
    first_seen    timestamptz NOT NULL,
    last_seen     timestamptz NOT NULL,
    queries       integer NOT NULL DEFAULT 0,
    dangerous     integer NOT NULL DEFAULT 0,
    blocked_until timestamptz,
    block_reason  text
);

CREATE TABLE IF NOT EXISTS user_queries (
    id            varchar(32) PRIMARY KEY,
    ts            timestamptz NOT NULL,
    user_key      varchar(64) NOT NULL,
    user_label    varchar(32),
    account_id    integer REFERENCES users (id) ON DELETE SET NULL,
    channel       varchar(32),
    text          text,
    text_sha      varchar(64),
    status        varchar(32) NOT NULL,
    verdict       varchar(64),
    flags         jsonb NOT NULL DEFAULT '[]',
    safety        jsonb,
    request_id    varchar(64),
    sources_count integer,
    completed_at  timestamptz,
    error         text
);
CREATE INDEX IF NOT EXISTS user_queries_ts ON user_queries (ts DESC);
CREATE INDEX IF NOT EXISTS user_queries_user ON user_queries (user_key, ts DESC);
CREATE INDEX IF NOT EXISTS user_queries_account ON user_queries (account_id, ts DESC);

CREATE TABLE IF NOT EXISTS query_topics (
    id             varchar(32) PRIMARY KEY,
    label          text NOT NULL,
    tokens         jsonb NOT NULL,
    created_at     timestamptz NOT NULL,
    last_seen      timestamptz NOT NULL,
    gap_status     varchar(32) NOT NULL DEFAULT 'brak',
    gap_since      timestamptz,
    gap_users      integer NOT NULL DEFAULT 0,
    gap_note       text,
    gap_updated_at timestamptz
);
CREATE INDEX IF NOT EXISTS query_topics_seen ON query_topics (last_seen DESC);

CREATE TABLE IF NOT EXISTS query_claims (
    id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    query_id      varchar(32) NOT NULL REFERENCES user_queries (id) ON DELETE CASCADE,
    ts            timestamptz NOT NULL,
    user_key      varchar(64) NOT NULL,
    topic_id      varchar(32) NOT NULL REFERENCES query_topics (id) ON DELETE CASCADE,
    text          text NOT NULL,
    verdict       varchar(64),
    kind          varchar(16) NOT NULL,
    sources_count integer
);
CREATE INDEX IF NOT EXISTS query_claims_topic ON query_claims (topic_id, kind, ts);
CREATE INDEX IF NOT EXISTS query_claims_query ON query_claims (query_id);

CREATE TABLE IF NOT EXISTS monitor_alerts (
    id         varchar(32) PRIMARY KEY,
    type       varchar(64) NOT NULL,
    subject    varchar(64) NOT NULL,
    severity   varchar(16) NOT NULL,
    status     varchar(32) NOT NULL,
    title      text NOT NULL,
    count      integer NOT NULL DEFAULT 0,
    users      integer NOT NULL DEFAULT 0,
    first_seen timestamptz NOT NULL,
    last_seen  timestamptz NOT NULL,
    details    jsonb NOT NULL DEFAULT '{}',
    note       text,
    updated_at timestamptz NOT NULL
);
CREATE INDEX IF NOT EXISTS monitor_alerts_open ON monitor_alerts (type, subject, status);

CREATE TABLE IF NOT EXISTS config_audit (
    id     bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    ts     timestamptz NOT NULL,
    actor  varchar(255) NOT NULL,
    field  varchar(100) NOT NULL,
    old    jsonb,
    new    jsonb
);
