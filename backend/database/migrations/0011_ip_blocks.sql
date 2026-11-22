-- Blokady adresów IP po próbach prompt injection (backend/admin/client_ip.py).
-- Bez adresów w jawnej postaci: ip_key to HMAC-SHA256 adresu (IPv6: sieci /64) z solą
-- ADMIN_IP_SALT albo z monitor_meta('ip_salt'); label to maska do pokazania w panelu.
-- Trafiają tu wyłącznie adresy, z których przyszła próba prompt injection.

CREATE TABLE IF NOT EXISTS ip_blocks (
    ip_key        varchar(64) PRIMARY KEY,
    label         varchar(64) NOT NULL,
    attempts      integer NOT NULL DEFAULT 0,
    first_seen    timestamptz NOT NULL,
    last_seen     timestamptz NOT NULL,
    blocked_until timestamptz,
    blocked_at    timestamptz,
    blocked_by    varchar(255),
    reason        text,
    alert_id      varchar(32)
);
CREATE INDEX IF NOT EXISTS ip_blocks_until ON ip_blocks (blocked_until);

CREATE TABLE IF NOT EXISTS monitor_meta (
    key   varchar(64) PRIMARY KEY,
    value text NOT NULL
);
