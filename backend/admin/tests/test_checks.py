"""Odczyt trafień EUvsDisinfo z raportu ``verification`` (``admin.checks``)."""

from __future__ import annotations

from admin.checks import known_disinfo_matches, monitor_enabled

MATCH = {"statement": "NATO szykuje atak.", "url": "https://euvsdisinfo.eu/report/x", "title": "X"}


def report(matches, status: str = "ok") -> dict:
    return {
        "claims_verdict": {
            "status": status,
            "data": {"verdict": "falsz", "claims": [], "known_disinfo": {"matches": matches}},
        }
    }


def test_matches_are_read_from_the_verdict():
    assert known_disinfo_matches(report([MATCH, "zły wpis"])) == [MATCH]


def test_missing_or_broken_report_has_no_matches():
    assert known_disinfo_matches({}) == []
    assert known_disinfo_matches(None) == []
    assert known_disinfo_matches({"claims_verdict": {"status": "error", "data": None}}) == []


def test_monitor_can_be_disabled(monkeypatch):
    monkeypatch.setenv("ADMIN_MONITOR", "off")
    assert not monitor_enabled()
    monkeypatch.setenv("ADMIN_MONITOR", "on")
    assert monitor_enabled()
