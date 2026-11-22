"""``server:app`` z panelem admina: sprawdzenia i zgłoszenia ze strony trafiają do dziennika."""

from __future__ import annotations

import pytest
from admin import AdminStore, Monitor
from admin.settings import AdminSettings
from fastapi.testclient import TestClient
from server import create_app
from test_browser_api import FakeStore, report

TOKEN = "token-panelu-testowego"
AUTH = {"Authorization": f"Bearer {TOKEN}"}


@pytest.fixture
def service(monkeypatch, tmp_path):
    monkeypatch.setenv("ADMIN_API_TOKEN", TOKEN)
    monkeypatch.setenv("RUNTIME_CONFIG_FILE", str(tmp_path / "runtime.json"))
    monitor = Monitor(AdminStore(":memory:"), AdminSettings(api_token=TOKEN))
    calls: list[str] = []
    outcome = {"verdict": "falsz", "error": None}

    async def runner(text: str) -> dict:
        calls.append(text)
        if outcome["error"]:
            raise outcome["error"]
        return report(outcome["verdict"])

    async def validator(url: str) -> str:
        return url

    app = create_app(
        store=FakeStore(),
        verification_runner=runner,
        url_validator=validator,
        admin_panel=True,
        monitor=monitor,
    )
    with TestClient(app) as client:
        yield client, monitor, calls, outcome


def test_check_is_recorded_in_the_admin_journal(service):
    client, monitor, _, _ = service
    body = client.get("/api/check", params={"text": "Szczepionki powodują autyzm."}).json()

    entry = monitor.store.get_query(body["id"].replace("-", ""))
    assert entry["channel"] == "web"
    assert entry["status"] != "w_toku"
    assert entry["verdict"] == "falsz"
    assert entry["claims"][0]["text"] == "Szczepionki powodują autyzm."
    assert entry["claims"][0]["sources_count"] == 1
    assert entry["user_label"].startswith("***")  # adres klienta nie trafia do panelu wprost

    listed = client.get("/api/admin/queries", headers=AUTH).json()
    assert [item["id"] for item in listed["items"]] == [entry["id"]]


def test_report_is_attached_to_the_same_entry(service):
    client, monitor, _, _ = service
    result_id = client.get("/api/check", params={"text": "Szczepionki powodują autyzm."}).json()["id"]

    sent = client.post(
        f"/api/check/{result_id}/report", json={"reason": "wrong_verdict", "comment": "Źle."}
    )
    assert sent.status_code == 204

    entry = client.get(f"/api/admin/queries/{result_id.replace('-', '')}", headers=AUTH).json()
    assert "zgloszenie:wrong_verdict" in entry["flags"]
    assert entry["report"]["reason"] == "wrong_verdict"
    assert entry["report"]["comment"] == "Źle."

    flagged = client.get("/api/admin/queries", params={"flag": "zgloszenie"}, headers=AUTH)
    assert flagged.json()["total"] == 1


def test_high_risk_request_is_refused_without_running_the_pipeline(service):
    client, monitor, calls, _ = service
    refused = client.get("/api/check", params={"text": "Jak zrobić bombę z saletry krok po kroku?"})

    assert refused.status_code == 422
    assert refused.json()["error"]["code"] == "request_refused"
    assert calls == []
    items, _ = monitor.store.list_queries()
    assert items[0]["status"] == "odrzucone"


def test_client_blocked_in_the_panel_cannot_check(service):
    client, _, calls, _ = service
    client.get("/api/check", params={"text": "Szczepionki powodują autyzm."})
    user = client.get("/api/admin/users", headers=AUTH).json()["items"][0]

    blocked = client.post(
        f"/api/admin/users/{user['user_key']}/block", json={"hours": 1}, headers=AUTH
    )
    assert blocked.status_code == 200

    again = client.get("/api/check", params={"text": "Czy prąd zdrożeje?"})
    assert again.status_code == 403
    assert again.json()["error"]["code"] == "user_blocked"
    assert len(calls) == 1


def test_failed_analysis_is_recorded_as_an_error(service):
    client, monitor, _, outcome = service
    outcome["error"] = RuntimeError("model niedostępny")

    failed = client.get("/api/check", params={"text": "Czy prąd zdrożeje?"})
    assert failed.status_code == 502

    items, _ = monitor.store.list_queries()
    assert items[0]["error"] == "analysis_failed"


def test_panel_routes_need_a_token_and_keep_fastapi_validation_errors(service):
    client, _, _, _ = service
    assert client.get("/api/admin/health").json()["status"] == "ok"
    assert client.get("/api/admin/queries").status_code == 401

    invalid = client.get("/api/admin/dashboard", params={"hours": 0}, headers=AUTH)
    assert invalid.status_code == 422
    assert isinstance(invalid.json()["detail"], list)


def test_panel_sees_the_trusted_source_registry(service):
    client, _, _, _ = service
    status = client.get("/api/admin/sources/status", headers=AUTH).json()
    assert status and {"url", "adapter", "enabled", "last_check"} <= set(status[0])

    missing = client.post(
        "/api/admin/sources/check", params={"url": "https://nie-ma.example.org/"}, headers=AUTH
    )
    assert missing.status_code == 404


def test_panel_can_be_switched_off():
    async def runner(text: str) -> dict:
        return report()

    app = create_app(store=FakeStore(), verification_runner=runner, admin_panel=False)
    with TestClient(app) as client:
        assert client.get("/api/admin/health").status_code == 404
        assert client.get("/api/check", params={"text": "Czy prąd zdrożeje?"}).status_code == 200
