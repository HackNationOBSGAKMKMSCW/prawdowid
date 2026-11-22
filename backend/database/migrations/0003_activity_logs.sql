-- Dziennik działań w aplikacji: logowania, zmiany kont, źródeł, konfiguracji, blokady itd.
-- `actor` to migawka (email albo 'system'/'token'), więc wpis przetrwa usunięcie konta.

CREATE TABLE IF NOT EXISTS activity_logs (
    id           bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    occurred_at  timestamptz NOT NULL DEFAULT now(),
    user_id      integer REFERENCES users (id) ON DELETE SET NULL,
    actor        varchar(255) NOT NULL,
    action       varchar(100) NOT NULL,
    subject_type varchar(50),
    subject_id   varchar(255),
    details      jsonb NOT NULL DEFAULT '{}',
    ip_address   inet,
    user_agent   varchar(255)
);

CREATE INDEX IF NOT EXISTS activity_logs_occurred ON activity_logs (occurred_at DESC);
CREATE INDEX IF NOT EXISTS activity_logs_user ON activity_logs (user_id, occurred_at DESC);
CREATE INDEX IF NOT EXISTS activity_logs_action ON activity_logs (action, occurred_at DESC);
