"""Adres bazy z Vercel/Neon działa z asyncpg (api_store)."""

import ssl

from api_store import _dsn_and_ssl


def test_neon_url_drops_libpq_only_options(monkeypatch):
    monkeypatch.delenv("DATABASE_SSL_MODE", raising=False)
    dsn, ssl_option = _dsn_and_ssl(
        "postgresql://u:p@ep-x-pooler.eu-central-1.aws.neon.tech/neondb"
        "?sslmode=require&channel_binding=require"
    )
    assert dsn == "postgresql://u:p@ep-x-pooler.eu-central-1.aws.neon.tech/neondb"
    assert ssl_option == "require"


def test_default_is_verified_tls(monkeypatch):
    monkeypatch.delenv("DATABASE_SSL_MODE", raising=False)
    _, ssl_option = _dsn_and_ssl("postgresql://u:p@host/db?application_name=prawdowid")
    assert isinstance(ssl_option, ssl.SSLContext)
