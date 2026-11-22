-- Biała lista stron zaufanych (moduł trustedSources). Schemat jak w trustedSources/README.md,
-- uzupełniony o znaczniki czasu i autora ostatniej zmiany.

CREATE TABLE IF NOT EXISTS trusted_sources (
    url         text PRIMARY KEY,
    name        text NOT NULL,
    topics      text[] NOT NULL DEFAULT '{}',
    description text NOT NULL DEFAULT '',
    adapter     text,
    params      jsonb NOT NULL DEFAULT '{}',
    enabled     boolean NOT NULL DEFAULT true,
    created_at  timestamptz NOT NULL DEFAULT now(),
    updated_at  timestamptz NOT NULL DEFAULT now(),
    updated_by  integer REFERENCES users (id) ON DELETE SET NULL,
    CONSTRAINT trusted_sources_url_http CHECK (url ~* '^https?://')
);

CREATE INDEX IF NOT EXISTS trusted_sources_enabled ON trusted_sources (enabled);
