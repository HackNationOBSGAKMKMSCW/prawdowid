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
    outcome = {"verdict": "falsz", "error": None, "known_disinfo": None}

    async def runner(text: str) -> dict:
        calls.append(text)
        if outcome["error"]:
            raise outcome["error"]
        data = report(outcome["verdict"])
        if outcome["known_disinfo"]:
            data["claims_verdict"]["data"]["known_disinfo"] = {"matches": outcome["known_disinfo"]}
        return data

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
    # adres klienta nie trafia do panelu ani wprost, ani jako pseudonim
    assert entry["user_key"] == "anonim" and entry["user_label"] is None

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


def test_no_client_data_and_no_blocking(service):
    """Strona jest anonimowa: nie ma rejestru klientów ani blokad, kolejne sprawdzenia przechodzą."""
    client, _, calls, _ = service
    client.get("/api/check", params={"text": "Szczepionki powodują autyzm."})
    assert client.get("/api/admin/users", headers=AUTH).status_code == 404
    again = client.get("/api/check", params={"text": "Czy prąd zdrożeje?"})
    assert again.status_code == 200
    assert len(calls) == 2


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


CASE = {
    "statement": "NATO przygotowuje atak na Rosję z terytorium Polski.",
    "title": "NATO is preparing to attack Russia",
    "url": "https://euvsdisinfo.eu/report/nato-is-preparing-to-attack-russia-2",
    "reason": "Ta sama teza.",
}


def test_known_disinformation_in_a_check_raises_an_admin_alert(service):
    client, monitor, _, outcome = service
    outcome["known_disinfo"] = [CASE]
    first = client.get("/api/check", params={"text": CASE["statement"]}).json()
    client.get("/api/check", params={"text": CASE["statement"]})

    alerts = client.get(
        "/api/admin/alerts", params={"type": "rosyjska_dezinformacja"}, headers=AUTH
    ).json()["items"]
    assert len(alerts) == 1
    assert alerts[0]["count"] == 2  # każde zapytanie osobno (bez danych o kliencie)
    occurrence = alerts[0]["details"]["wystapienia"][-1]
    assert occurrence["query_id"] == first["id"].replace("-", "")
    assert occurrence["kanal"] == "web" and occurrence["request_id"]
    assert "rosyjska_dezinformacja" in monitor.store.get_query(occurrence["query_id"])["flags"]


def test_sql_injection_in_a_check_is_one_occurrence_not_two(service):
    client, monitor, _, _ = service
    response = client.get("/api/check", params={"text": "x' OR '1'='1"})
    assert response.status_code == 200  # nic nie blokujemy
    assert client.app.state.admin_worker.flush()

    alerts = monitor.store.list_alerts(alert_type="sql_injection")
    assert len(alerts) == 1 and alerts[0]["subject"] == "kanal:web"
    assert alerts[0]["count"] == 1  # middleware HTTP i monitor treści: to samo żądanie
    occurrence = alerts[0]["details"]["wystapienia"][0]
    assert set(occurrence["pola"]) == {"query.text", "tresc_wiadomosci"}
    assert occurrence["query_id"] == response.json()["id"].replace("-", "")


def test_sql_injection_in_panel_requests_uses_the_panel_channel(service):
    client, monitor, _, _ = service
    client.get("/api/admin/queries", params={"q": "x' UNION SELECT 1--"}, headers=AUTH)
    assert client.app.state.admin_worker.flush()
    alert = monitor.store.list_alerts(alert_type="sql_injection")[0]
    assert alert["subject"] == "kanal:panel"
    assert alert["details"]["wystapienia"][0]["sciezka"] == "/api/admin/queries"
