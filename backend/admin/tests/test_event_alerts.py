"""Powiadomienia admina: rosyjska dezinformacja (EUvsDisinfo) i próby SQL injection."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from uuid import uuid4

import pytest
from admin.background import BackgroundWorker
from admin.monitor import Monitor
from admin.request_audit import SqlInjectionAuditMiddleware
from admin.runtime import RuntimeConfigStore
from admin.settings import AdminSettings
from admin.sqli import scan_request, scan_text
from admin.store import AdminStore
from admin.web import CheckJournal
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel

CASE = {
    "claim_id": "T1",
    "statement": "NATO przygotowuje atak na Rosję z terytorium Polski.",
    "reason": "Ta sama teza.",
    "case_id": "https://euvsdisinfo.eu/report/nato-is-preparing-to-attack-russia-2",
    "title": "NATO is preparing to attack Russia",
    "summary": "…",
    "disproof": "…",
    "url": "https://euvsdisinfo.eu/report/nato-is-preparing-to-attack-russia-2",
    "source": "EUvsDisinfo",
}


def report(matches: list[dict] | None = None) -> dict:
    return {
        "claims_verdict": {
            "status": "ok",
            "data": {
                "verdict": "falszywy",
                "claims": [
                    {"claim": CASE["statement"], "verdict": "falsz", "evidence": [{"url": "x"}]}
                ],
                "known_disinfo": {
                    "status": "ok",
                    "source": "EUvsDisinfo",
                    "matches": matches or [],
                    "warnings": [],
                },
            },
        }
    }


def record_check(text: str, data: dict, *, monitor: Monitor, client: str = "203.0.113.7"):
    """Sprawdzenie ze strony tą samą drogą co ``/api/check``: ``CheckJournal``."""
    journal = CheckJournal(monitor)
    request = SimpleNamespace(client=SimpleNamespace(host=client))

    async def run():
        decision = await journal.screen(request, text, query_id=uuid4().hex)
        response = SimpleNamespace(
            claims=[SimpleNamespace(text=text, verdict="false", sources=["x"])]
        )
        await journal.complete(decision.query_id, response, data)
        return decision

    return asyncio.run(run())


@pytest.fixture
def monitor(tmp_path) -> Monitor:
    store = AdminStore(tmp_path / "admin.db")
    yield Monitor(
        store,
        AdminSettings(api_token="t", db_path=tmp_path / "admin.db"),
        RuntimeConfigStore(tmp_path / "runtime.json"),
    )
    store.close()


# --- detektor SQL injection --------------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "' OR '1'='1",
        "admin' OR 1=1 --",
        '" or "a"="a',
        "1 UNION SELECT username, password FROM users",
        "1 UN/**/ION SEL/**/ECT 1,2",
        "1 UNION/**/SELECT 1,2",
        "x'; DROP TABLE users; --",
        "1; delete from api_check_results",
        "1' AND SLEEP(5)#",
        "'; WAITFOR DELAY '0:0:5'--",
        "1 and 1=1 --",
        "select table_name from information_schema.tables",
        "%27%20OR%20%271%27%3D%271",
        "%2527%2520OR%25201%253D1%2520--",
    ],
)
def test_sql_injection_is_detected(text):
    assert scan_text(text), text


@pytest.mark.parametrize(
    "text",
    [
        "NATO przygotowuje atak na Rosję z terytorium Polski.",
        "Czy to prawda, że 1=1 w matematyce?",
        "Wybierz (select) najlepszą odpowiedź z listy",
        "Rząd obniżył VAT; szkoły zamknięte od poniedziałku",
        "It's a 'great' day -- said the minister",
        "Ala ma kota, a kot ma Alę or so they say",
        "https://www.gov.pl/web/premier/wschodnia-straz-nato",
        "We must act now; create jobs and lower taxes",
        "Koncert odbył się; update kolejny wkrótce",
        "Adults need sleep (7-9 hours)",
        'Send to 0x71C7656EC7ab88b098defB751B7401B5f6d8976F "#crypto',
        "Select the best answer from the list",
        "",
    ],
)
def test_ordinary_text_is_not_flagged(text):
    assert scan_text(text) == [], text


def test_scan_request_reports_field_names_not_values():
    detection = scan_request(
        "/api/admin/auth/login",
        b"q=ok&next=%27%20or%20%271%27%3D%271",
        b'{"email": "a@b.pl", "password": "x\' OR \'1\'=\'1"}',
        "application/json",
    )
    assert detection.locations == ["query.next", "body.password"]
    assert "tautologia" in detection.patterns


# --- rosyjska dezinformacja ----------------------------------------------------------------


def test_known_disinformation_registers_one_alert_per_case(monitor):
    first = record_check(CASE["statement"], report([CASE]), monitor=monitor)
    second = record_check(CASE["statement"], report([CASE]), monitor=monitor)
    assert first and second

    alerts = monitor.store.list_alerts(alert_type="rosyjska_dezinformacja")
    assert len(alerts) == 1
    alert = alerts[0]
    assert alert["count"] == 2 and alert["severity"] == "wysoka" and alert["status"] == "otwarty"
    assert alert["title"] == "Zweryfikowana rosyjska dezinformacja: NATO is preparing to attack Russia"
    assert alert["details"]["przypadek"]["url"] == CASE["url"]
    occurrences = alert["details"]["wystapienia"]
    assert len(occurrences) == 2 and occurrences[0]["twierdzenie"] == CASE["statement"]
    assert occurrences[0]["kanal"] == "web"

    query = monitor.store.get_query(occurrences[0]["query_id"])
    assert "rosyjska_dezinformacja" in query["flags"]


def test_resolved_disinformation_alert_reopens_as_new(monitor):
    record_check(CASE["statement"], report([CASE]), monitor=monitor)
    alert = monitor.store.list_alerts(alert_type="rosyjska_dezinformacja")[0]
    monitor.set_alert_status(alert["id"], "rozwiazany")
    record_check(CASE["statement"], report([CASE]), monitor=monitor)
    alerts = monitor.store.list_alerts(alert_type="rosyjska_dezinformacja")
    assert sorted(a["status"] for a in alerts) == ["otwarty", "rozwiazany"]


def test_no_match_no_alert(monitor):
    record_check(CASE["statement"], report([]), monitor=monitor)
    assert monitor.store.list_alerts(alert_type="rosyjska_dezinformacja") == []


# --- SQL injection: kanały -----------------------------------------------------------------


def test_whatsapp_message_with_sql_injection_is_registered(monitor):
    decision = monitor.screen(user_id="+48111", text="x'; DROP TABLE users; --", channel="whatsapp")
    assert decision.allowed  # nic nie blokujemy, tylko zgłaszamy
    alert = monitor.store.list_alerts(alert_type="sql_injection")[0]
    assert alert["subject"] == "kanal:whatsapp" and alert["count"] == 1
    entry = alert["details"]["wystapienia"][0]
    assert entry["pola"] == ["tresc_wiadomosci"] and "zapytanie_doklejone" in entry["wzorce"]
    assert "DROP" not in str(alert["details"])  # wartości pól nie trafiają do alertu
    assert "sql_injection" in monitor.store.get_query(decision.query_id)["flags"]


def test_anonymous_screen_flags_but_leaves_alert_to_middleware(monitor):
    decision = monitor.screen(user_id="web", text="' OR '1'='1", anonymous=True)
    assert "sql_injection" in monitor.store.get_query(decision.query_id)["flags"]
    assert monitor.store.list_alerts(alert_type="sql_injection") == []


class Login(BaseModel):
    email: str
    password: str


def _app(reporter, worker: BackgroundWorker) -> FastAPI:
    app = FastAPI()

    @app.get("/api/check")
    def check(text: str) -> dict:
        return {"text_length": len(text)}

    @app.post("/login")
    def login(body: Login) -> dict:
        return {"email": body.email}

    app.add_middleware(SqlInjectionAuditMiddleware, reporter=reporter, worker=worker)
    return app


def test_middleware_reports_and_never_changes_the_response():
    calls = []
    worker = BackgroundWorker("test")
    client = TestClient(_app(lambda *args: calls.append(args), worker))

    clean = client.get("/api/check", params={"text": "NATO przygotowuje atak na Rosję"})
    assert clean.status_code == 200
    assert worker.flush() and calls == []

    attack = client.get(
        "/api/check",
        params={"text": "1 UNION SELECT password FROM users"},
        headers={"X-Forwarded-For": "203.0.113.7, 10.0.0.1"},
    )
    assert attack.status_code == 200 and attack.json() == {"text_length": 34}
    assert worker.flush()
    detection, method, path, ip, _request_id = calls[-1]
    assert (method, path, ip) == ("GET", "/api/check", "203.0.113.7")
    assert detection.locations == ["query.text"]

    login = client.post("/login", json={"email": "a@b.pl", "password": "' or '1'='1"})
    assert login.status_code == 200 and login.json() == {"email": "a@b.pl"}  # treść dotarła
    assert worker.flush()
    assert calls[-1][0].locations == ["body.password"]


def test_middleware_does_not_wait_for_a_slow_reporter():
    import threading
    import time

    release = threading.Event()
    worker = BackgroundWorker("test")
    client = TestClient(_app(lambda *args: release.wait(5), worker))
    started = time.perf_counter()
    response = client.get("/api/check", params={"text": "' OR '1'='1"})
    assert response.status_code == 200
    assert time.perf_counter() - started < 2  # odpowiedź nie czekała na zapis
    release.set()
    assert worker.flush()


def test_pathological_input_is_scanned_quickly():
    import time

    for payload in ("' or" + " " * 20000, "/*" * 10000, "' or (" + " " * 4000 + "'" * 4000):
        started = time.perf_counter()
        scan_text(payload)
        assert time.perf_counter() - started < 0.5, payload[:10]


def test_full_queue_drops_instead_of_blocking():
    import threading

    gate = threading.Event()
    worker = BackgroundWorker("test", maxsize=2)
    assert worker.submit(gate.wait, 5)
    accepted = [worker.submit(lambda: None) for _ in range(10)]
    assert accepted.count(True) <= 3 and worker.dropped >= 7
    gate.set()
    assert worker.flush()


def test_middleware_reporter_failure_is_swallowed():
    def broken(*args):
        raise RuntimeError("baza leży")

    worker = BackgroundWorker("test")
    client = TestClient(_app(broken, worker))
    assert client.get("/api/check", params={"text": "' OR '1'='1"}).status_code == 200
    assert worker.flush()


def test_alert_write_failure_does_not_break_screen(monitor, monkeypatch):
    def broken(**kwargs):
        raise RuntimeError("zapis alertu nieudany")

    monkeypatch.setattr(monitor, "register_sql_injection", broken)
    decision = monitor.screen(user_id="+48111", text="x'; DROP TABLE users; --", channel="whatsapp")
    assert decision.allowed and "sql_injection" in monitor.store.get_query(decision.query_id)["flags"]


def test_concurrent_detections_keep_one_alert_and_every_count(monitor):
    from concurrent.futures import ThreadPoolExecutor

    def attempt(n: int) -> None:
        monitor.register_sql_injection(
            channel="web", source=f"ip{n % 5}", patterns=["union_select"], locations=["query.q"]
        )

    with ThreadPoolExecutor(8) as pool:
        list(pool.map(attempt, range(40)))
    alerts = monitor.store.list_alerts(alert_type="sql_injection")
    assert len(alerts) == 1 and alerts[0]["count"] == 40 and alerts[0]["users"] == 5


def test_disinformation_counts_each_client_once(monitor):
    for client in ("203.0.113.7", "203.0.113.7", "198.51.100.2"):
        record_check(CASE["statement"], report([CASE]), monitor=monitor, client=client)
    alert = monitor.store.list_alerts(alert_type="rosyjska_dezinformacja")[0]
    assert alert["count"] == 3 and alert["users"] == 2


def test_same_request_reported_twice_is_one_occurrence(monitor):
    for locations in (["query.text"], ["tresc_wiadomosci"]):
        monitor.register_sql_injection(
            channel="web",
            source="ip1",
            patterns=["tautologia"],
            locations=locations,
            request_id="req-1",
        )
    monitor.register_sql_injection(
        channel="web", source="ip2", patterns=["union_select"], locations=["query.q"], request_id="req-2"
    )
    alert = monitor.store.list_alerts(alert_type="sql_injection")[0]
    assert alert["count"] == 2 and alert["users"] == 2
    first = alert["details"]["wystapienia"][1]
    assert first["request_id"] == "req-1" and first["pola"] == ["query.text", "tresc_wiadomosci"]


def test_admin_panel_registers_sql_injection_in_alerts(tmp_path):
    from admin.api import create_app

    settings = AdminSettings(api_token="t", db_path=tmp_path / "admin.db")
    runtime = RuntimeConfigStore(tmp_path / "runtime.json")
    store = AdminStore(settings.db_path)
    monitor = Monitor(store, settings, runtime)
    auth = {"Authorization": "Bearer t"}
    app = create_app(settings, monitor=monitor, runtime=runtime)
    with TestClient(app) as client:
        client.get("/api/admin/queries", params={"q": "x' UNION SELECT 1--"}, headers=auth)
        client.get("/api/admin/queries", params={"q": "x' UNION SELECT 1--"}, headers=auth)
        assert app.state.admin_worker.flush()
        alerts = client.get("/api/admin/alerts?type=sql_injection", headers=auth).json()["items"]
    store.close()
    assert len(alerts) == 1 and alerts[0]["count"] == 2
    entry = alerts[0]["details"]["wystapienia"][0]
    assert entry["sciezka"] == "/api/admin/queries" and entry["pola"] == ["query.q"]
    assert entry["zrodlo"] and entry["request_id"] and alerts[0]["users"] == 1


def test_browser_api_installs_the_middleware_inside_the_size_limit():
    from server import create_app

    calls = []

    class Store:
        async def health_check(self):
            return None

        async def close(self):
            return None

    app = create_app(store=Store(), sql_injection_reporter=lambda *a: calls.append(a))
    with TestClient(app) as client:
        client.get("/api/health", params={"x": "1; DROP TABLE users"})
        too_big = client.post(
            "/api/check/00000000-0000-0000-0000-000000000000/report",
            content=b"x" * (200 * 1024),
            headers={"content-type": "application/json"},
        )
        assert app.state.admin_worker.flush()
    assert too_big.status_code == 413  # limit rozmiaru działa przed audytem
    assert len(calls) == 1 and calls[0][2] == "/api/health"
