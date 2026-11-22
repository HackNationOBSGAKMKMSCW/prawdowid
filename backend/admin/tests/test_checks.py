"""Most strona -> monitor: raport ``verification`` zamieniony na twierdzenia z werdyktem."""

from __future__ import annotations

import pytest
from admin.checks import claims_from_report, record_check
from admin.monitor import Monitor
from admin.runtime import RuntimeConfigStore
from admin.settings import AdminSettings
from admin.store import AdminStore

GAP = "W Pcimiu Dolnym zamknięto wszystkie szkoły w listopadzie"


def report(*claims: tuple[str, str, int], verdict: str = "brak_danych", status: str = "ok"):
    return {
        "evidence": {"status": "ok", "data": {"statements": [c[0] for c in claims]}},
        "claims_verdict": {
            "status": status,
            "data": {
                "verdict": verdict,
                "summary": "…",
                "claims": [
                    {
                        "claim_id": f"T{i}",
                        "claim": text,
                        "verdict": claim_verdict,
                        "evidence": [{"url": f"https://x/{n}"} for n in range(sources)],
                    }
                    for i, (text, claim_verdict, sources) in enumerate(claims, 1)
                ],
            }
            if status == "ok"
            else None,
        },
    }


@pytest.fixture
def monitor(tmp_path) -> Monitor:
    store = AdminStore(tmp_path / "admin.db")
    yield Monitor(
        store,
        AdminSettings(api_token="t", db_path=tmp_path / "admin.db"),
        RuntimeConfigStore(tmp_path / "runtime.json"),
    )
    store.close()


def test_claims_from_report_maps_verdicts_and_sources():
    claims, verdict, sources = claims_from_report(
        report(
            (GAP, "brak_wystarczajacych_danych", 0),
            ("Wisła jest najdłuższą rzeką w Polsce", "prawda", 2),
            ("Coś", "blad_analizy", 0),
        )
    )
    assert [(c.text, c.verdict, c.sources_count) for c in claims] == [
        (GAP, "brak_wystarczajacych_danych", 0),
        ("Wisła jest najdłuższą rzeką w Polsce", "prawda", 2),
        ("Coś", "blad_analizy", 0),
    ]
    assert verdict == "brak_danych" and sources == 2


def test_failed_verdict_is_not_counted():
    assert claims_from_report(report(status="error")) == ([], None, None)
    assert claims_from_report({}) == ([], None, None)


def test_record_check_counts_uncovered_queries(monitor):
    for _ in range(3):
        result = record_check(GAP, report((GAP, "nieweryfikowalny", 0)), monitor=monitor)
    assert result.claims[0].kind == "luka"
    assert result.claims[0].info_gap_status == "aktywna"
    assert result.claims[0].info_gap_queries == 3

    query = monitor.store.list_queries(limit=1)[0][0]
    assert query["channel"] == "web" and query["status"] == "zakonczone"
    assert monitor.store.list_alerts(alert_type="luka_informacyjna")[0]["count"] == 3


def test_blad_analizy_is_not_a_gap(monitor):
    for _ in range(3):
        result = record_check(GAP, report((GAP, "blad_analizy", 0)), monitor=monitor)
    assert result.claims[0].kind == "inne"
    assert monitor.store.list_alerts(alert_type="luka_informacyjna") == []


def test_monitor_can_be_disabled(monkeypatch):
    monkeypatch.setenv("ADMIN_MONITOR", "off")
    assert record_check(GAP, report((GAP, "nieweryfikowalny", 0))) is None
