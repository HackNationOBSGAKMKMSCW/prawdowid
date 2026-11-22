"""Hasła, tokeny, uprawnienia i migracje — bez bazy danych."""

import pytest
from accounts import passwords, permissions, tokens
from database import discover, placeholders, redact
from database.connection import Row


def test_password_hash_roundtrip_and_format():
    encoded = passwords.hash_password("Bardzo-dlugie-haslo-1")
    assert encoded.startswith("scrypt$32768$8$1$")
    assert "Bardzo" not in encoded
    assert passwords.verify_password("Bardzo-dlugie-haslo-1", encoded)
    assert not passwords.verify_password("Bardzo-dlugie-haslo-2", encoded)
    assert not passwords.verify_password("x", "nie-hash")
    assert not passwords.needs_rehash(encoded)
    assert passwords.needs_rehash("scrypt$1024$8$1$a$b")


def test_same_password_gets_different_salt():
    assert passwords.hash_password("Haslo-testowe-123") != passwords.hash_password(
        "Haslo-testowe-123"
    )


@pytest.mark.parametrize(
    "password",
    ["krotkie", "aaaaaaaaaaaaaa", "x" * 300, "jan.kowalski@example.pl"],
)
def test_weak_passwords_are_rejected(password):
    with pytest.raises(passwords.WeakPasswordError):
        passwords.validate(password, email="jan.kowalski@example.pl")


def test_token_compose_parse_and_hash():
    secret = tokens.new_secret()
    raw = tokens.compose(42, secret)
    assert raw.startswith("oat_")
    parsed = tokens.parse(raw)
    assert parsed is not None and parsed.token_id == 42 and parsed.secret == secret
    assert tokens.matches(secret, tokens.hash_secret(secret))
    assert not tokens.matches(secret + "x", tokens.hash_secret(secret))
    assert tokens.hash_secret(secret) != secret


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "Bearer x",
        "oat_.abc",
        "oat_bm90bnVtYmVy.sekret-wystarczajaco-dlugi",
        "oat_MQ.krotki",
        "oat_MQ.a.b",
        "abc_MQ.sekret-wystarczajaco-dlugi-123",
    ],
)
def test_malformed_tokens_are_rejected(raw):
    assert tokens.parse(raw) is None


def test_role_permissions_match_panel():
    assert permissions.allowed("admin", ["*"], "users:write")
    # analityk: panel obserwacyjny, sam odczyt
    for read in ("dashboard:read", "alerts:read", "clusters:read", "checks:read", "sources:read",
                 "security:read", "settings:read", "models:read", "export"):
        assert permissions.allowed("analyst", ["*"], read), read
    for write in ("sources:write", "alerts:write", "cases:write", "security:write",
                  "settings:write", "models:write", "users:read", "users:write", "audit:read"):
        assert not permissions.allowed("analyst", ["*"], write), write
    assert permissions.allowed("admin", ["*"], "security:write")  # blokady adresów IP
    # rola moderatora jest wyłączona: nie daje żadnych uprawnień ani wstępu do panelu
    assert "moderator" not in permissions.ROLES and "moderator" not in permissions.PANEL_ROLES
    assert not permissions.allowed("moderator", ["*"], "dashboard:read")
    assert not permissions.allowed("user", ["*"], "dashboard:read")
    # token zawęża uprawnienia roli, nigdy ich nie rozszerza
    assert not permissions.allowed("admin", ["alerts:read"], "users:write")
    assert permissions.allowed("admin", ["users:*"], "users:write")
    assert not permissions.allowed("analyst", ["users:*"], "users:write")


def test_token_abilities_cannot_exceed_role():
    assert permissions.normalize_abilities("analyst", None) == ["*"]
    assert permissions.normalize_abilities("analyst", ["alerts:read"]) == ["alerts:read"]
    with pytest.raises(ValueError):
        permissions.normalize_abilities("analyst", ["settings:write"])


def test_placeholders_translate_outside_string_literals():
    sql = "SELECT * FROM t WHERE a = ? AND b LIKE ? ESCAPE '\\' AND c = '?' AND d LIKE 'x%'"
    assert placeholders(sql) == (
        "SELECT * FROM t WHERE a = %s AND b LIKE %s ESCAPE '\\' AND c = '?' AND d LIKE 'x%%'"
    )


def test_redact_hides_password():
    assert redact("postgresql://ola:tajne@host:5432/db") == "postgresql://ola:***@host:5432/db"
    assert redact("postgresql://host/db") == "postgresql://host/db"


def test_migrations_are_ordered_and_named():
    migrations = discover()
    assert [m.version for m in migrations] == sorted(m.version for m in migrations)
    names = [m.name for m in migrations]
    assert names[:4] == ["accounts", "trusted_sources", "activity_logs", "query_journal"]
    sql = "\n".join(m.sql for m in migrations)
    for table in (
        "users",
        "auth_access_tokens",
        "trusted_sources",
        "activity_logs",
        "user_queries",
        "end_users",
        "monitor_alerts",
    ):
        assert f"CREATE TABLE IF NOT EXISTS {table} " in sql


def test_row_supports_index_and_utc_iso():
    from datetime import datetime, timedelta, timezone

    warsaw = timezone(timedelta(hours=1))
    row = Row(["a", "ts"], [1, datetime(2026, 11, 22, 13, 0, tzinfo=warsaw)])
    assert row[0] == 1 and row["a"] == 1
    assert row["ts"] == "2026-11-22T12:00:00.000Z"
