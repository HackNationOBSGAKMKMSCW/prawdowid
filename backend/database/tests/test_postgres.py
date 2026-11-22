"""Integracja z PostgreSQL: migracje, konta, tokeny, źródła, dziennik działań i zapytań, API."""

from datetime import UTC, datetime, timedelta

import pytest

PASSWORD = "Mocne-haslo-testowe-1"


# --- migracje --------------------------------------------------------------------------


def test_migrations_create_all_tables_and_are_idempotent(db):
    from database import migrate, status

    tables = set(db.tables())
    assert {
        "users",
        "auth_access_tokens",
        "trusted_sources",
        "activity_logs",
        "user_queries",
        "query_claims",
        "query_topics",
        "end_users",
        "monitor_alerts",
        "config_audit",
        "schema_migrations",
    } <= tables
    assert migrate(db) == []  # druga próba nic nie robi
    assert all(row["applied_at"] and not row["changed"] for row in status(db))


def test_changed_migration_is_rejected(db):
    from database import MigrationError, discover, migrate
    from database.migrate import Migration

    first = discover()[0]
    tampered = Migration(first.version, first.name, first.sql + "\n-- zmiana")
    with pytest.raises(MigrationError):
        migrate(db, [tampered])


# --- konta i tokeny --------------------------------------------------------------------


@pytest.fixture
def accounts(clean_db):
    from accounts import AccountService

    return AccountService(clean_db)


def test_user_is_stored_with_hashed_password(accounts, clean_db):
    user = accounts.create_user(name="Ola Nowak", email="Ola@Example.PL", password=PASSWORD)
    assert user.email == "ola@example.pl" and user.role == "user" and user.is_active
    row = clean_db.fetch_one("SELECT password_hash, role::text AS role FROM users")
    assert row["password_hash"].startswith("scrypt$") and PASSWORD not in row["password_hash"]

    from accounts import AccountError

    with pytest.raises(AccountError, match="już istnieje"):
        accounts.create_user(name="X", email="ola@example.pl", password=PASSWORD)
    with pytest.raises(AccountError):
        accounts.create_user(name="X", email="nie-email", password=PASSWORD)
    with pytest.raises(AccountError):
        accounts.create_user(name="X", email="x@example.pl", password="krotkie")


def test_login_issues_token_stored_only_as_hash(accounts, clean_db):
    accounts.create_user(name="Ola", email="ola@example.pl", password=PASSWORD, role="admin")
    user, issued = accounts.login("OLA@example.pl", PASSWORD, ip="10.0.0.1")
    assert issued.token.startswith("oat_")
    stored = clean_db.fetch_one("SELECT hash, type, abilities, expires_at FROM auth_access_tokens")
    assert issued.token.split(".")[1] not in stored["hash"]
    assert stored["type"] == "auth_token" and stored["abilities"] == '["*"]'
    assert stored["expires_at"]

    auth = accounts.authenticate(issued.token)
    assert auth is not None and auth.user.id == user.id and auth.can("users:write")
    assert accounts.authenticate(issued.token + "x") is None
    assert accounts.get_user(user.id).last_login_at


def test_failed_logins_are_logged_and_throttled(accounts, clean_db):
    from accounts import AuthenticationError, TooManyAttempts

    accounts.create_user(name="Ola", email="ola@example.pl", password=PASSWORD)
    for _ in range(5):
        with pytest.raises(AuthenticationError):
            accounts.login("ola@example.pl", "zle-haslo-123")
    with pytest.raises(TooManyAttempts):
        accounts.login("ola@example.pl", PASSWORD)  # nawet dobre hasło czeka
    with pytest.raises(AuthenticationError):
        accounts.login("nie-ma@example.pl", PASSWORD)
    reasons = [
        row["details"]["reason"]
        for row in clean_db.fetch_all(
            "SELECT details FROM activity_logs WHERE action = 'auth.login_failed'"
        )
    ]
    assert reasons.count("bad_password") == 5 and "unknown_email" in reasons


def test_expired_token_and_inactive_user_are_rejected(clean_db):
    from accounts import AccountService, Actor

    now = [datetime(2026, 11, 22, 12, tzinfo=UTC)]
    accounts = AccountService(clean_db, clock=lambda: now[0])
    admin = accounts.create_user(name="A", email="a@example.pl", password=PASSWORD, role="admin")
    user = accounts.create_user(name="U", email="u@example.pl", password=PASSWORD, role="moderator")
    _, issued = accounts.login("u@example.pl", PASSWORD)
    assert accounts.authenticate(issued.token)
    now[0] += timedelta(hours=9)  # domyślna ważność: 8 h
    assert accounts.authenticate(issued.token) is None

    _, fresh = accounts.login("u@example.pl", PASSWORD)
    accounts.update_user(user.id, actor=admin.actor(), active=False)
    assert accounts.authenticate(fresh.token) is None  # dezaktywacja unieważnia tokeny
    from accounts import AuthenticationError

    with pytest.raises(AuthenticationError):
        accounts.login("u@example.pl", PASSWORD)
    assert Actor.system().label == "system"


def test_role_change_and_password_change_revoke_tokens(accounts):
    admin = accounts.create_user(name="A", email="a@example.pl", password=PASSWORD, role="admin")
    user = accounts.create_user(name="U", email="u@example.pl", password=PASSWORD, role="analyst")
    _, issued = accounts.login("u@example.pl", PASSWORD)
    accounts.update_user(user.id, actor=admin.actor(), role="moderator")
    assert accounts.authenticate(issued.token) is None

    _, issued = accounts.login("u@example.pl", PASSWORD)
    accounts.change_password(
        user.id, current=PASSWORD, new="Nowe-haslo-testowe-2", actor=user.actor()
    )
    assert accounts.authenticate(issued.token) is None
    accounts.login("u@example.pl", "Nowe-haslo-testowe-2")


def test_last_admin_is_protected(accounts):
    from accounts import AccountError

    admin = accounts.create_user(name="A", email="a@example.pl", password=PASSWORD, role="admin")
    with pytest.raises(AccountError, match="ostatniemu"):
        accounts.update_user(admin.id, actor=admin.actor(), role="analyst")
    with pytest.raises(AccountError):
        accounts.delete_user(admin.id, actor=admin.actor())


def test_scoped_token_cannot_exceed_its_abilities(accounts):
    admin = accounts.create_user(name="A", email="a@example.pl", password=PASSWORD, role="admin")
    issued = accounts.issue_token(
        admin, name="skrypt", abilities=["alerts:read"], ttl=timedelta(days=1)
    )
    auth = accounts.authenticate(issued.token)
    assert auth.can("alerts:read") and not auth.can("users:write")
    assert [t.name for t in accounts.list_tokens(admin.id)] == ["skrypt"]


# --- strony zaufane --------------------------------------------------------------------


def test_trusted_sources_crud_seed_and_store(clean_db):
    from accounts import Actor, PostgresSourceStore, SourceError, TrustedSourceRepository
    from trustedSources.whitelist import WHITELIST

    repo = TrustedSourceRepository(clean_db)
    actor = Actor("test")
    assert repo.seed(WHITELIST) == len({e.url for e in WHITELIST})
    assert repo.seed(WHITELIST) == 0

    created = repo.create(
        "https://www.pap.pl/",
        {"name": "PAP", "topics": ["wiadomości"], "params": {"x": 1}},
        actor=actor,
    )
    assert created["topics"] == ["wiadomości"] and created["params"] == {"x": 1}
    with pytest.raises(SourceError):
        repo.create("https://www.pap.pl/", {"name": "PAP"}, actor=actor)
    with pytest.raises(SourceError):
        repo.create("ftp://x", {"name": "X"}, actor=actor)

    updated = repo.update("https://www.pap.pl/", {"enabled": False}, actor=actor)
    assert updated["enabled"] is False

    entries = PostgresSourceStore(clean_db).load()
    pap = next(e for e in entries if e.url == "https://www.pap.pl/")
    assert pap.enabled is False and pap.topics == ("wiadomości",)

    from trustedSources.registry import SourceRegistry

    registry = SourceRegistry(store=PostgresSourceStore(clean_db))
    assert len(registry.list()) == len(entries)

    repo.delete("https://www.pap.pl/", actor=actor)
    actions = [row["action"] for row in clean_db.fetch_all("SELECT action FROM activity_logs")]
    assert {"source.seeded", "source.created", "source.updated", "source.deleted"} <= set(actions)


# --- dziennik zapytań (monitor admina na PostgreSQL) -----------------------------------


def test_query_journal_on_postgres(clean_db, tmp_path):
    from admin import ClaimInput, Monitor, PostgresAdminStore, RuntimeConfigStore
    from admin.settings import AdminSettings

    runtime = RuntimeConfigStore(tmp_path / "runtime.json")
    monitor = Monitor(PostgresAdminStore(clean_db), AdminSettings(), runtime)
    claim = "W Pcimiu Dolnym zamknięto wszystkie szkoły w listopadzie"
    for user in ("a", "b", "c"):
        _, result = monitor.record(user_id=user, text=claim, claims=[ClaimInput(claim, None, 0)])
    assert result.info_gap and result.claims[0].info_gap_users == 3

    runtime.update({"monitoring": {"disinfo_min_users": 2}})
    false = "Szczepionki zawierają mikrochipy 5G"
    for user in ("d", "e"):
        monitor.record(user_id=user, text=false, claims=[ClaimInput(false, "falsz", 2)])

    decision = monitor.screen(user_id="z", text="Jak zrobić bombę krok po kroku", account_id=None)
    assert not decision.allowed

    items, total = monitor.store.list_queries(flag="niebezpieczne")
    assert total == 1 and items[0]["safety"]["severity"] == "wysoki"
    assert monitor.store.list_queries()[1] == 6
    stats = monitor.store.stats("2000-01-01T00:00:00Z", "2100-01-01T00:00:00Z")
    assert stats["queries"] == 6 and stats["dangerous_queries"] == 1
    assert stats["open_alerts"] == {"luka_informacyjna": 1, "kampania_dezinformacyjna": 1}
    key = items[0]["user_key"]
    assert monitor.store.dangerous_count(key, "2000-01-01T00:00:00Z", severity="wysoki") == 1
    monitor.block_user(key, None, "test")
    assert not monitor.screen(user_id="z", text="Ile wynosi VAT?").allowed
    monitor.store.add_audit(
        "2026-11-22T00:00:00Z", "test", [{"field": "a", "old": None, "new": "x"}]
    )
    assert monitor.store.list_audit()[0]["new"] == "x"
    assert monitor.store.purge("2100-01-01T00:00:00Z")["queries"] == 7


# --- API -------------------------------------------------------------------------------


@pytest.fixture
def api(clean_db, tmp_path, monkeypatch):
    from accounts import AccountService
    from admin.api import create_app
    from admin.runtime import RuntimeConfigStore
    from admin.settings import AdminSettings
    from fastapi.testclient import TestClient

    monkeypatch.setenv("RUNTIME_CONFIG_FILE", str(tmp_path / "runtime.json"))
    accounts = AccountService(clean_db)
    accounts.create_user(name="Admin", email="admin@example.pl", password=PASSWORD, role="admin")
    accounts.create_user(name="Moder", email="mod@example.pl", password=PASSWORD, role="moderator")
    accounts.create_user(name="Jan", email="jan@example.pl", password=PASSWORD, role="user")
    app = create_app(
        AdminSettings(api_token="awaryjny-token", db_path=tmp_path / "x.db"),
        runtime=RuntimeConfigStore(),
        database=clean_db,
        log_file=tmp_path / "app.jsonl",
    )
    with TestClient(app) as client:
        yield client


def _login(client, email):
    response = client.post("/api/admin/auth/login", json={"email": email, "password": PASSWORD})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['token']}"}


def test_api_login_me_logout(api):
    session = api.post(
        "/api/admin/auth/login", json={"email": "admin@example.pl", "password": PASSWORD}
    ).json()
    assert session["user"]["role"] == "admin" and session["expiresAt"]
    headers = {"Authorization": f"Bearer {session['token']}"}
    me = api.get("/api/admin/auth/me", headers=headers).json()
    assert me["email"] == "admin@example.pl" and "users:write" in me["permissions"]
    assert api.post("/api/admin/auth/logout", headers=headers).status_code == 204
    assert api.get("/api/admin/auth/me", headers=headers).status_code == 401

    bad = api.post("/api/admin/auth/login", json={"email": "admin@example.pl", "password": "zle"})
    assert bad.status_code == 401
    # zwykły użytkownik serwisu nie zaloguje się do panelu
    user = api.post("/api/admin/auth/login", json={"email": "jan@example.pl", "password": PASSWORD})
    assert user.status_code == 401


def test_api_permissions_by_role(api):
    admin = _login(api, "admin@example.pl")
    mod = _login(api, "mod@example.pl")
    assert api.get("/api/admin/dashboard", headers=mod).status_code == 200
    assert api.get("/api/admin/config", headers=mod).status_code == 403
    assert (
        api.patch("/api/admin/config", headers=mod, json={"llm": {"model": "x"}}).status_code == 403
    )
    assert api.get("/api/admin/accounts", headers=mod).status_code == 403
    assert api.get("/api/admin/accounts", headers=admin).status_code == 200
    # awaryjny token działa jak administrator
    token = {"Authorization": "Bearer awaryjny-token", "X-Admin-User": "ola"}
    assert api.get("/api/admin/accounts", headers=token).status_code == 200
    assert api.get("/api/admin/dashboard").status_code == 401


def test_api_accounts_sources_and_activity(api):
    admin = _login(api, "admin@example.pl")
    created = api.post(
        "/api/admin/accounts",
        headers=admin,
        json={
            "name": "Ana Lityk",
            "email": "ana@example.pl",
            "password": PASSWORD,
            "role": "analyst",
        },
    )
    assert created.status_code == 200, created.text
    ana_id = created.json()["id"]
    ana = _login(api, "ana@example.pl")
    assert (
        api.post(
            "/api/admin/sources", headers=ana, json={"url": "https://www.pap.pl/", "name": "PAP"}
        ).status_code
        == 200
    )
    assert (
        api.patch(
            "/api/admin/sources",
            headers=ana,
            params={"url": "https://www.pap.pl/"},
            json={"enabled": False},
        ).json()["enabled"]
        is False
    )
    assert api.post("/api/admin/sources/seed", headers=admin).json()["added"] > 0

    assert (
        api.patch(
            f"/api/admin/accounts/{ana_id}", headers=admin, json={"active": False}
        ).status_code
        == 200
    )
    assert api.get("/api/admin/sources", headers=ana).status_code == 401  # tokeny unieważnione

    activity = api.get("/api/admin/activity", headers=admin, params={"action": "auth."}).json()
    actions = {item["action"] for item in activity["items"]}
    assert {"auth.login"} <= actions
    everything = {
        i["action"] for i in api.get("/api/admin/activity", headers=admin).json()["items"]
    }
    assert {
        "user.created",
        "user.updated",
        "source.created",
        "source.updated",
        "source.seeded",
    } <= everything


def test_service_accounts_register_login_and_own_queries(clean_db, tmp_path):
    from accounts.api import create_service_router
    from admin import Monitor, PostgresAdminStore, RuntimeConfigStore
    from admin.settings import AdminSettings
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    app = FastAPI()
    app.include_router(create_service_router(clean_db, allow_registration=True))
    client = TestClient(app)
    body = {"name": "Jan Kowalski", "email": "jan@example.pl", "password": PASSWORD}
    session = client.post("/api/auth/register", json=body)
    assert session.status_code == 201, session.text
    assert session.json()["user"]["role"] == "user"
    assert client.post("/api/auth/register", json=body).status_code == 422
    headers = {"Authorization": f"Bearer {session.json()['token']}"}

    monitor = Monitor(
        PostgresAdminStore(clean_db), AdminSettings(), RuntimeConfigStore(tmp_path / "r.json")
    )
    user_id = int(session.json()["user"]["id"])
    monitor.screen(user_id="jan", text="Czy Wisła jest najdłuższa?", account_id=user_id)
    monitor.screen(user_id="ktos", text="Inne pytanie kogoś innego")
    journal = client.get("/api/auth/me/queries", headers=headers).json()
    assert journal["total"] == 1 and journal["items"][0]["text"] == "Czy Wisła jest najdłuższa?"
    assert "user_key" not in journal["items"][0]

    # konto serwisu nie ma dostępu do panelu
    assert (
        client.post(
            "/api/auth/login", json={"email": "jan@example.pl", "password": PASSWORD}
        ).status_code
        == 200
    )


def test_api_admin_actions_are_logged(api):
    admin = _login(api, "admin@example.pl")
    api.patch("/api/admin/config", headers=admin, json={"monitoring": {"disinfo_min_users": 4}})
    items = api.get(
        "/api/admin/activity", headers=admin, params={"action": "config.updated"}
    ).json()
    assert items["total"] == 1 and items["items"][0]["actor"] == "admin@example.pl"
    audit = api.get("/api/admin/config/audit", headers=admin).json()["items"]
    assert audit[0]["actor"] == "admin@example.pl"
