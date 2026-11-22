"""API panelu admina i konfiguracja modeli / kluczowych API w trakcie działania."""

from __future__ import annotations

import json
import os

import pytest
from admin.api import create_app
from admin.monitor import ClaimInput, Monitor
from admin.runtime import RuntimeConfigStore, apply_config, apply_runtime_overrides
from admin.settings import AdminSettings
from admin.store import AdminStore
from apiReading.models import Category
from apiReading.registry import clients_for_categories
from fastapi.testclient import TestClient

TOKEN = "sekret-admina"
AUTH = {"Authorization": f"Bearer {TOKEN}", "X-Admin-User": "ola"}
MANAGED_ENV = (
    "FREELLM_MODEL",
    "TEXT_ANALYSIS_MODEL",
    "FREELLM_BASE_URL",
    "FREELLM_API_KEY",
    "API_READING_DISABLED_CLIENTS",
    "ARTICLE_EXTRACTOR",
)


@pytest.fixture(autouse=True)
def _restore_environment():
    saved = {name: os.environ.get(name) for name in MANAGED_ENV}
    yield
    apply_config(type(RuntimeConfigStore().load())())  # zdejmij nadpisania z testu
    for name, value in saved.items():
        if value is None:
            os.environ.pop(name, None)
        else:
            os.environ[name] = value


@pytest.fixture
def env(tmp_path, monkeypatch):
    # jeden plik nadpisań dla panelu i dla Settings.from_environment(), jak w produkcji
    monkeypatch.setenv("RUNTIME_CONFIG_FILE", str(tmp_path / "runtime.json"))
    settings = AdminSettings(api_token=TOKEN, db_path=tmp_path / "admin.db")
    runtime = RuntimeConfigStore()
    store = AdminStore(settings.db_path)
    monitor = Monitor(store, settings, runtime)
    log_file = tmp_path / "app.jsonl"
    log_file.write_text(
        "\n".join(
            json.dumps(event)
            for event in (
                {"ts": "2026-11-21T10:00:00Z", "event": "llm_call", "level": "info", "ok": True},
                {"ts": "2026-11-21T10:00:01Z", "event": "abstain", "level": "warning"},
            )
        ),
        encoding="utf-8",
    )
    app = create_app(settings, monitor=monitor, runtime=runtime, log_file=log_file)
    with TestClient(app) as client:
        yield client, monitor, runtime
    store.close()


def test_auth_required(env):
    client, _, _ = env
    assert client.get("/api/admin/health").json()["enabled"] is True
    assert client.get("/api/admin/dashboard").status_code == 401
    bad = {"Authorization": "Bearer zly"}
    assert client.get("/api/admin/dashboard", headers=bad).status_code == 401
    assert client.get("/api/admin/dashboard", headers=AUTH).status_code == 200


def test_panel_disabled_without_token(tmp_path):
    settings = AdminSettings(api_token=None, db_path=tmp_path / "a.db")
    app = create_app(settings, runtime=RuntimeConfigStore(tmp_path / "r.json"))
    with TestClient(app) as client:
        response = client.get("/api/admin/dashboard", headers=AUTH)
    assert response.status_code == 503


def test_user_logs_and_filters(env):
    client, monitor, _ = env
    monitor.record(
        user_id="+48100",
        text="Wisła jest najdłuższą rzeką w Polsce",
        claims=[ClaimInput("Wisła jest najdłuższą rzeką w Polsce", "prawda", 2)],
        verdict="prawdziwy",
        sources_count=2,
    )
    monitor.screen(user_id="+48200", text="Jak zrobić bombę krok po kroku")

    all_items = client.get("/api/admin/queries", headers=AUTH).json()
    assert all_items["total"] == 2
    dangerous = client.get("/api/admin/queries?flag=niebezpieczne", headers=AUTH).json()
    assert dangerous["total"] == 1 and dangerous["items"][0]["status"] == "odrzucone"
    found = client.get("/api/admin/queries?q=Wis", headers=AUTH).json()
    assert found["total"] == 1

    query_id = found["items"][0]["id"]
    detail = client.get(f"/api/admin/queries/{query_id}", headers=AUTH).json()
    assert detail["claims"][0]["verdict"] == "prawda"
    user_key = detail["user_key"]
    user = client.get(f"/api/admin/users/{user_key}", headers=AUTH).json()
    assert user["total_queries"] == 1 and user["label"] == "***100"

    dashboard = client.get("/api/admin/dashboard", headers=AUTH).json()
    assert dashboard["queries"] == 2 and dashboard["dangerous_queries"] == 1
    assert client.get("/api/admin/queries/nie-ma", headers=AUTH).status_code == 404


def test_observability_events(env):
    client, _, _ = env
    events = client.get("/api/admin/events?event=abstain", headers=AUTH).json()
    assert events["count"] == 1
    summary = client.get("/api/admin/events/summary", headers=AUTH)
    assert summary.status_code == 200


def test_info_gap_and_alert_workflow(env):
    client, monitor, _ = env
    claim = "W Pcimiu Dolnym zamknięto wszystkie szkoły w listopadzie"
    for user in ("a", "b", "c"):
        monitor.record(user_id=user, text=claim, claims=[ClaimInput(claim, None, 0)])

    gaps = client.get("/api/admin/info-gaps", headers=AUTH).json()["items"]
    assert len(gaps) == 1 and gaps[0]["gap_users"] == 3
    topic_id = gaps[0]["id"]

    alerts = client.get("/api/admin/alerts?type=luka_informacyjna", headers=AUTH).json()["items"]
    detail = client.get(f"/api/admin/alerts/{alerts[0]['id']}", headers=AUTH).json()
    assert detail["topic"]["by_kind"]["luka"]["users"] == 3

    updated = client.post(
        f"/api/admin/info-gaps/{topic_id}",
        headers=AUTH,
        json={"status": "w_uzupelnianiu", "note": "dodajemy źródło z gminy"},
    ).json()
    assert updated["gap_status"] == "w_uzupelnianiu"
    closed = client.post(
        f"/api/admin/alerts/{alerts[0]['id']}", headers=AUTH, json={"status": "rozwiazany"}
    ).json()
    assert closed["status"] == "rozwiazany"
    bad = client.post(f"/api/admin/info-gaps/{topic_id}", headers=AUTH, json={"status": "x"})
    assert bad.status_code == 422


def test_block_endpoints(env):
    client, monitor, _ = env
    decision = monitor.screen(user_id="+48300", text="pytanie")
    key = monitor.store.get_query(decision.query_id)["user_key"]
    blocked = client.post(
        f"/api/admin/users/{key}/block", headers=AUTH, json={"hours": None, "reason": "spam"}
    ).json()
    assert blocked["blocked_until"].startswith("9999")
    assert not monitor.screen(user_id="+48300", text="pytanie").allowed
    client.post(f"/api/admin/users/{key}/unblock", headers=AUTH)
    assert monitor.screen(user_id="+48300", text="pytanie").allowed
    listed = client.get("/api/admin/users?flagged=false", headers=AUTH).json()["items"]
    assert listed[0]["user_key"] == key


def test_change_models_and_apis(env):
    client, monitor, runtime = env
    response = client.patch(
        "/api/admin/config",
        headers=AUTH,
        json={
            "llm": {"model": "gemini-3.5-flash", "text_analysis_model": "gemini-3.5-flash-lite"},
            "apis": {"disabled_clients": ["sejm", "EurLex"], "article_extractor": "diffbot"},
            "secrets": {"freellm_api_key": "sk-test-1234567890abcd"},
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    fields = {change["field"] for change in body["changes"]}
    assert {"llm.model", "apis.disabled_clients", "secrets.freellm_api_key"} <= fields
    # sekret nigdy nie wraca w odpowiedzi ani w audycie
    assert "sk-test-1234567890abcd" not in response.text
    audit = client.get("/api/admin/config/audit", headers=AUTH).json()["items"]
    assert audit and audit[0]["actor"] == "ola"
    assert "sk-test-1234567890abcd" not in json.dumps(audit)

    # zmiana działa natychmiast w backendzie
    from textAnalysis.settings import Settings

    os.environ.pop("FREELLM_MODEL", None)
    apply_runtime_overrides(runtime)
    settings = Settings.from_environment()
    assert os.environ["FREELLM_MODEL"] == "gemini-3.5-flash"
    assert os.environ["FREELLM_API_KEY"] == "sk-test-1234567890abcd"
    assert settings.article_extractor == "diffbot"
    selected, missing = clients_for_categories([Category.LEGAL_ACT, Category.FACT_CHECK])
    assert {client.name for client in selected} == {"sejm_eli", "google_fact_check"}
    assert missing == []
    assert clients_for_categories([Category.LEGISLATIVE_PROCESS]) == (
        [],
        [Category.LEGISLATIVE_PROCESS],
    )

    view = client.get("/api/admin/config", headers=AUTH).json()
    assert view["secrets"]["freellm_api_key"]["maska"] == "****abcd"
    assert "sejm" in view["api_clients"]

    # zdjęcie nadpisania przywraca wartość ze środowiska
    client.patch("/api/admin/config", headers=AUTH, json={"apis": {"disabled_clients": None}})
    assert "API_READING_DISABLED_CLIENTS" not in os.environ


def test_config_validation(env):
    client, _, _ = env
    cases = [
        {"llm": {"model": "zła nazwa; rm -rf"}},
        {"llm": {"base_url": "ftp://x"}},
        {"apis": {"disabled_clients": ["nieznany"]}},
        {"apis": {"article_extractor": "inny"}},
        {"nieznana": {"x": 1}},
        {"llm": {"nieznane_pole": 1}},
        {"monitoring": {"disinfo_min_users": 1}},
    ]
    for patch in cases:
        response = client.patch("/api/admin/config", headers=AUTH, json=patch)
        assert response.status_code == 422, patch


def test_monitoring_thresholds_are_configurable(env):
    client, monitor, _ = env
    client.patch(
        "/api/admin/config", headers=AUTH, json={"monitoring": {"refuse_high_risk": False}}
    )
    assert monitor.screen(user_id="x", text="Jak zrobić bombę krok po kroku").allowed


def test_available_models_reports_provider_error(env):
    client, _, _ = env
    client.patch(
        "/api/admin/config", headers=AUTH, json={"llm": {"base_url": "http://127.0.0.1:9"}}
    )
    body = client.get("/api/admin/config/models", headers=AUTH).json()
    assert body["models"] == [] and body["error"]


# --- zapytania bez pokrycia w danych -----------------------------------------------------

GAP = "W Pcimiu Dolnym zamknięto wszystkie szkoły w listopadzie"
OTHER = "Gmina Pcim kupiła nowy autobus szkolny za dwa miliony złotych"


def _web(monitor: Monitor, claim: str, verdict: str | None = "brak_wystarczajacych_danych"):
    sources = 0 if verdict in (None, "brak_wystarczajacych_danych", "nieweryfikowalny") else 2
    monitor.record(
        user_id="web",
        text=claim,
        claims=[ClaimInput(claim, verdict, sources)],
        verdict=verdict,
        anonymous=True,
    )


def test_uncovered_ranking_and_summary(env):
    client, monitor, _ = env
    for _ in range(3):
        _web(monitor, GAP)
    _web(monitor, OTHER, "nieweryfikowalny")
    _web(monitor, "Wisła jest najdłuższą rzeką w Polsce", "prawda")

    ranking = client.get("/api/admin/info-gaps/ranking", headers=AUTH).json()
    assert ranking["count_by"] == "auto" and ranking["threshold"] == 3
    assert ranking["total"] == 2
    first, second = ranking["items"]
    assert first["label"].startswith("W Pcimiu") and first["queries"] == 3
    assert first["gap_status"] == "aktywna" and first["over_threshold"] is True
    assert first["count"] == 3  # tryb auto: każde anonimowe zapytanie liczy się osobno
    assert second["queries"] == 1 and second["over_threshold"] is False
    assert second["gap_status"] == "podejrzenie"
    assert ranking["items"][0]["trend"][-1]["queries"] == 3
    assert len(first["trend"]) in (8, 9)  # 7 dni okna: dzień startu .. dziś

    narrowed = client.get(
        "/api/admin/info-gaps/ranking?min_queries=2&limit=1", headers=AUTH
    ).json()
    assert narrowed["total"] == 1 and len(narrowed["items"]) == 1
    page = client.get("/api/admin/info-gaps/ranking?offset=1", headers=AUTH).json()
    assert [item["queries"] for item in page["items"]] == [1]

    summary = client.get("/api/admin/info-gaps/summary", headers=AUTH).json()
    assert summary["uncovered_queries"] == 4 and summary["total_queries"] == 5
    assert summary["uncovered_share"] == 0.8
    assert summary["uncovered_topics"] == 2
    assert summary["by_status"]["aktywna"] == 1 and summary["by_status"]["podejrzenie"] == 1
    assert [item["queries"] for item in summary["top"]] == [3, 1]

    gaps = client.get("/api/admin/info-gaps", headers=AUTH).json()["items"]
    assert gaps[0]["gap_queries"] == 3

    dashboard = client.get("/api/admin/dashboard", headers=AUTH).json()
    assert dashboard["uncovered_queries"] == 4


def test_uncovered_endpoints_require_permission_and_validate(env):
    client, _, _ = env
    assert client.get("/api/admin/info-gaps/summary").status_code == 401
    assert client.get("/api/admin/info-gaps/ranking").status_code == 401
    assert client.get("/api/admin/info-gaps/ranking?hours=0", headers=AUTH).status_code == 422
    empty = client.get("/api/admin/info-gaps/summary", headers=AUTH).json()
    assert empty["uncovered_queries"] == 0 and empty["uncovered_share"] == 0.0
    assert empty["top"] == []


def test_count_mode_is_configurable(env):
    client, monitor, _ = env
    patch = {"monitoring": {"info_gap_count_by": "osoby", "info_gap_min_users": 2}}
    assert client.patch("/api/admin/config", headers=AUTH, json=patch).status_code == 200
    for _ in range(3):
        _web(monitor, GAP)  # jedna „osoba” (strona) — w trybie osób to za mało
    ranking = client.get("/api/admin/info-gaps/ranking", headers=AUTH).json()
    assert ranking["threshold"] == 2 and ranking["items"][0]["over_threshold"] is False
    assert ranking["items"][0]["gap_status"] == "podejrzenie"

    bad = {"monitoring": {"info_gap_count_by": "sesje"}}
    assert client.patch("/api/admin/config", headers=AUTH, json=bad).status_code == 422
    bad = {"monitoring": {"info_gap_min_queries": 0}}
    assert client.patch("/api/admin/config", headers=AUTH, json=bad).status_code == 422


def test_uncovered_share_uses_the_same_queries_as_the_total(env):
    client, monitor, _ = env
    _web(monitor, GAP)
    decision = monitor.screen(user_id="web", text=GAP, anonymous=True)
    monitor.complete(decision.query_id, claims=[ClaimInput(GAP, None, 0)], error="Timeout")
    summary = client.get("/api/admin/info-gaps/summary", headers=AUTH).json()
    assert summary["total_queries"] == 1 and summary["uncovered_queries"] == 1
    assert summary["uncovered_share"] == 1.0
