"""``server:app``: kontrakt endpointów dla frontendu, bez bazy i bez modeli (atrapy)."""

from __future__ import annotations

from pathlib import Path
from uuid import UUID

import api_store
import pytest
from database.migrate import discover
from fastapi.testclient import TestClient
from server import create_app


def report(verdict: str = "falsz") -> dict:
    ok = {"status": "ok"}
    return {
        "evidence": {**ok, "data": {}},
        "input_analysis": {
            **ok,
            "data": {
                "manipulation": {"manipulation_detected": False, "score": 90, "fragments": []}
            },
        },
        "claims_verdict": {
            **ok,
            "data": {
                "verdict": verdict,
                "summary": "Podsumowanie.",
                "claims": [
                    {
                        "claim": "Szczepionki powodują autyzm.",
                        "verdict": verdict,
                        "explanation": "Badania tego nie potwierdzają.",
                        "evidence": [
                            {
                                "quote": "Brak związku.",
                                "publisher": "NIZP PZH",
                                "url": "https://www.pzh.gov.pl/",
                            }
                        ],
                    }
                ],
            },
        },
    }


class FakeStore:
    def __init__(self) -> None:
        self.results: dict[UUID, str] = {}
        self.reports: dict[UUID, tuple[str, str | None]] = {}

    async def health_check(self) -> None:
        return None

    async def record_result(self, result_id: UUID, input_type: str) -> None:
        self.results[result_id] = input_type

    async def save_report(self, result_id: UUID, reason: str, comment: str | None) -> bool:
        if result_id not in self.results:
            return False
        self.reports.setdefault(result_id, (reason, comment))
        return True

    async def close(self) -> None:
        return None


@pytest.fixture
def client():
    store = FakeStore()

    async def runner(text: str) -> dict:
        return report()

    async def validator(url: str) -> str:
        if "localhost" in url:
            from api_routes import ApiFailure

            raise ApiFailure(422, "unsafe_url", "The website address is not publicly accessible.")
        return url

    app = create_app(store=store, verification_runner=runner, url_validator=validator)
    with TestClient(app) as test_client:
        yield test_client, store


def test_check_and_report_round_trip(client):
    test_client, store = client
    response = test_client.get("/api/check", params={"text": "Szczepionki powodują autyzm."})
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "result" and body["input_type"] == "text"
    assert body["claims"][0]["verdict"] == "false"
    assert body["claims"][0]["sources"][0]["publisher"] == "NIZP PZH"
    assert response.headers["cache-control"] == "no-store"

    sent = test_client.post(f"/api/check/{body['id']}/report", json={"reason": "bad_source"})
    assert sent.status_code == 204
    assert store.reports[UUID(body["id"])] == ("bad_source", None)


def test_errors_have_code_for_the_frontend(client):
    test_client, _ = client
    unsafe = test_client.get("/api/check", params={"text": "http://localhost/admin"})
    assert unsafe.status_code == 422
    assert unsafe.json()["error"]["code"] == "unsafe_url"

    mixed = test_client.get(
        "/api/check", params={"text": "https://example.org i jeszcze komentarz"}
    )
    assert mixed.json()["error"]["code"] == "invalid_url"

    missing = test_client.post(
        "/api/check/00000000-0000-0000-0000-000000000000/report", json={"reason": "other"}
    )
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "result_not_found"


def test_health(client):
    test_client, _ = client
    assert test_client.get("/api/health").json() == {"status": "ok"}


class FakeSourceTable:
    """Rows of the ``trusted_sources`` table (accounts.trusted.PostgresSourceStore)."""

    def __init__(self, rows=None, error: Exception | None = None) -> None:
        self.rows = rows or []
        self.error = error

    def load(self):
        if self.error:
            raise self.error
        return self.rows


@pytest.fixture
def source_table(monkeypatch):
    import public_sources
    from trustedSources.registry import SourceRegistry
    from trustedSources.whitelist import WhitelistEntry

    table = FakeSourceTable(
        [
            WhitelistEntry("https://demagog.org.pl/", "Demagog", ("fakty",), "Fact-checking"),
            WhitelistEntry("https://www.gov.pl/web/zdrowie", "Ministerstwo Zdrowia"),
            WhitelistEntry("https://wylaczone.example.pl/", "Wyłączone", enabled=False),
        ]
    )
    registry = SourceRegistry(store=table, refresh_seconds=0)
    monkeypatch.setattr(public_sources, "_registry", lambda: registry)
    return table


def test_trusted_sources_come_from_the_database_table(client, source_table):
    test_client, _ = client
    listed = test_client.get("/api/trusted-sources")
    assert listed.status_code == 200
    sources = listed.json()
    assert [s["name"] for s in sources] == ["Demagog", "Ministerstwo Zdrowia"]  # bez wyłączonych
    by_name = {s["name"]: s for s in sources}
    assert by_name["Demagog"]["trust"] == "fact_checker"
    assert by_name["Ministerstwo Zdrowia"]["trust"] == "official"

    # zmiana w tabeli (np. z panelu admina) jest widoczna bez restartu
    from trustedSources.whitelist import WhitelistEntry

    source_table.rows.append(WhitelistEntry("https://konkret24.tvn24.pl/", "Konkret24"))
    assert "Konkret24" in [s["name"] for s in test_client.get("/api/trusted-sources").json()]


def test_trusted_sources_never_fall_back_to_the_code_list(client, monkeypatch):
    import public_sources

    test_client, _ = client
    monkeypatch.setattr(public_sources, "_db_registry", None)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setattr("database.database_url", lambda: None)
    for path in ("/api/trusted-sources", "/api/trusted-sources/demagog"):
        response = test_client.get(path)
        assert response.status_code == 503
        assert response.json()["error"]["code"] == "sources_unavailable"


def test_trusted_sources_report_a_database_failure(client, source_table):
    test_client, _ = client
    source_table.error = OSError("connection refused")
    response = test_client.get("/api/trusted-sources")
    assert response.status_code == 503 and "refused" not in response.text


def test_trusted_sources_are_read_only_and_public_fields_only(client, source_table):
    test_client, _ = client
    listed = test_client.get("/api/trusted-sources")
    assert listed.status_code == 200
    sources = listed.json()
    assert set(sources[0]) == {"id", "name", "url", "trust", "topics", "description"}

    one = test_client.get(f"/api/trusted-sources/{sources[0]['id']}")
    assert one.status_code == 200 and one.json()["id"] == sources[0]["id"]
    assert test_client.get("/api/trusted-sources/nie-ma-takiego").status_code == 404

    # detection and search call remote sites and the LLM: not on the public API
    assert test_client.post("/api/trusted-sources/search", json={"text": "x"}).status_code in (
        404,
        405,
    )
    assert test_client.post(f"/api/trusted-sources/{sources[0]['id']}/check").status_code in (
        404,
        405,
    )


def test_feedback_migration_is_shared_and_idempotent():
    path = Path(api_store.MIGRATION_PATH)
    assert path.is_file()
    assert any(
        m.name == "api_feedback" and m.sql == path.read_text(encoding="utf-8") for m in discover()
    )
    sql = path.read_text(encoding="utf-8")
    assert sql.count("CREATE TABLE IF NOT EXISTS") == 2
    assert "CREATE TABLE api" not in sql


def test_failed_stage_is_logged_without_the_text(caplog):
    async def failing(text: str) -> dict:
        data = report()
        data["evidence"] = {
            "status": "error",
            "error": {"kind": "AnalysisConfigurationError", "message": "Set FREELLM_API_KEY"},
        }
        return data

    app = create_app(store=FakeStore(), verification_runner=failing)
    with TestClient(app) as test_client, caplog.at_level("WARNING", logger="api_routes"):
        response = test_client.get("/api/check", params={"text": "Tajna treść wiadomości"})
    assert response.status_code == 502
    assert response.json()["error"]["code"] == "analysis_failed"
    logged = " ".join(record.getMessage() for record in caplog.records)
    assert "part=evidence kind=AnalysisConfigurationError" in logged
    assert "Tajna" not in logged


def test_whatsapp_channel_is_served_by_the_same_backend(monkeypatch):
    """Strona i symulator WhatsApp to jeden backend: /api/whatsapp/* w server:app."""
    monkeypatch.setenv("SPRAWDZTO_MODE", "demo")
    monkeypatch.setenv("ADMIN_MONITOR", "off")
    app = create_app(store=FakeStore(), verification_runner=lambda text: report())
    with TestClient(app) as test_client:
        health = test_client.get("/api/whatsapp/health")
        welcome = test_client.post(
            "/api/whatsapp/webhook",
            json={
                "object": "whatsapp_business_account",
                "entry": [
                    {
                        "changes": [
                            {
                                "field": "messages",
                                "value": {
                                    "messages": [
                                        {"from": "48500", "id": "w1", "type": "request_welcome"}
                                    ]
                                },
                            }
                        ]
                    }
                ],
            },
        )
    assert health.status_code == 200 and health.json()["mode"] == "demo"
    assert welcome.status_code == 200 and welcome.json()["messages"]


def test_whatsapp_channel_can_be_turned_off(monkeypatch):
    monkeypatch.setenv("WHATSAPP_ENABLED", "false")
    app = create_app(store=FakeStore())
    with TestClient(app) as test_client:
        assert test_client.get("/api/whatsapp/health").status_code == 404
