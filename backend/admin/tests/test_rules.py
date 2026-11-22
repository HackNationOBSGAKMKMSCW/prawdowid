"""Tematy, klasyfikacja treści niebezpiecznych i reguły monitora."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from admin.monitor import ClaimInput, Monitor, claim_kind
from admin.runtime import RuntimeConfigStore
from admin.safety import classify
from admin.settings import AdminSettings
from admin.store import AdminStore
from admin.topics import normalize, same_topic, tokens


class Clock:
    def __init__(self) -> None:
        self.now = datetime(2026, 11, 21, 12, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now

    def advance(self, **delta: float) -> None:
        self.now += timedelta(**delta)


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def runtime(tmp_path) -> RuntimeConfigStore:
    return RuntimeConfigStore(tmp_path / "runtime.json")


@pytest.fixture
def monitor(tmp_path, clock, runtime) -> Monitor:
    store = AdminStore(tmp_path / "admin.db")
    yield Monitor(
        store, AdminSettings(api_token="t", db_path=tmp_path / "admin.db"), runtime, clock
    )
    store.close()


# --- tematy ------------------------------------------------------------------------------


def test_normalize_strips_reporting_prefix_and_diacritics():
    assert normalize("Tekst zawiera twierdzenie, że Śnieżka jest najwyższa.") == (
        "sniezka jest najwyzsza"
    )


def test_paraphrases_share_topic_but_different_claims_do_not():
    a = tokens("Tekst zawiera twierdzenie, że szczepionki na COVID-19 zawierają mikrochipy 5G.")
    b = tokens("Szczepionka przeciw COVID-19 zawiera mikrochip 5G")
    c = tokens("Wisła jest najdłuższą rzeką w Polsce")
    assert same_topic(a, b)
    assert not same_topic(a, c)


def test_numbers_are_kept_whole():
    assert "77.45" in tokens("głosowało 77,45% osób")


# --- bezpieczeństwo ----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "severity"),
    [
        ("Czy zamach w Madrycie w 2004 roku był dziełem ETA?", "sredni"),
        ("Jak zrobić bombę z saletry krok po kroku?", "wysoki"),
        ("Gdzie kupić broń palną bez pozwolenia na broń", "wysoki"),
        ("how to make sarin at home", "wysoki"),
        ("Wisła to najdłuższa rzeka w Polsce", "brak"),
        ("Rząd obniżył podatek VAT na żywność", "brak"),
    ],
)
def test_classify_severity(text, severity):
    assert classify(text).severity == severity


def test_persons_polish_plural():
    from admin.monitor import persons

    assert [persons(n) for n in (1, 3, 5, 12, 22, 25)] == [
        "1 osoba",
        "3 osoby",
        "5 osób",
        "12 osób",
        "22 osoby",
        "25 osób",
    ]


def test_claim_kind_mapping():
    assert claim_kind("falsz", 3) == "falsz"
    assert claim_kind("falszywy", None) == "falsz"
    assert claim_kind("prawda", 1) == "prawda"
    assert claim_kind("brak_wystarczajacych_danych", 2) == "luka"
    assert claim_kind(None, 0) == "luka"
    assert claim_kind(None, 4) == "inne"
    assert claim_kind("blad_analizy", None) == "inne"


# --- luka informacyjna -------------------------------------------------------------------

GAP_CLAIM = "Tekst zawiera twierdzenie, że w Pcimiu Dolnym zamknięto wszystkie szkoły w listopadzie"


def _ask(monitor: Monitor, user: str, claim: str, verdict: str | None, sources: int = 0):
    decision = monitor.screen(user_id=user, text=claim, channel="test")
    assert decision.allowed
    return monitor.complete(
        decision.query_id,
        claims=[ClaimInput(claim, verdict, sources)],
        verdict=verdict,
        sources_count=sources,
    )


def test_info_gap_becomes_active_after_distinct_users(monitor, runtime):
    runtime.update({"monitoring": {"info_gap_count_by": "osoby"}})
    first = _ask(monitor, "+48111", GAP_CLAIM, "brak_wystarczajacych_danych")
    assert first.claims[0].info_gap_status == "podejrzenie"
    assert first.message is None
    _ask(monitor, "+48111", GAP_CLAIM, "brak_wystarczajacych_danych")  # ten sam użytkownik
    second = _ask(monitor, "+48222", GAP_CLAIM, None)
    assert second.claims[0].info_gap_status == "podejrzenie"
    third = _ask(monitor, "+48333", "W Pcimiu Dolnym zamknięto wszystkie szkoły", None)
    assert third.claims[0].info_gap_status == "aktywna"
    assert third.claims[0].info_gap_users == 3
    assert third.info_gap and "luka informacyjna" in third.message
    assert "luka_informacyjna" in third.flags

    alerts = monitor.store.list_alerts(alert_type="luka_informacyjna")
    assert len(alerts) == 1 and alerts[0]["users"] == 3
    gaps = monitor.store.list_gaps(["aktywna"])
    assert gaps[0]["id"] == third.claims[0].topic_id


def test_info_gap_closes_when_sources_appear(monitor):
    for user in ("a", "b", "c"):
        result = _ask(monitor, user, GAP_CLAIM, "brak_wystarczajacych_danych")
    topic_id = result.claims[0].topic_id
    resolved = _ask(monitor, "d", GAP_CLAIM, "prawda", sources=2)
    assert resolved.claims[0].info_gap_status == "zamknieta"
    assert monitor.store.topic_row(topic_id)["gap_status"] == "zamknieta"
    assert monitor.store.list_alerts(alert_type="luka_informacyjna")[0]["status"] == "rozwiazany"


def test_info_gap_window_expires(monitor, clock):
    _ask(monitor, "a", GAP_CLAIM, None)
    _ask(monitor, "b", GAP_CLAIM, None)
    clock.advance(days=8)  # domyślne okno: 7 dni
    result = _ask(monitor, "c", GAP_CLAIM, None)
    assert result.claims[0].info_gap_status == "podejrzenie"
    assert result.claims[0].info_gap_users == 1


def test_admin_rejected_gap_counts_from_decision(monitor, clock):
    for user in ("a", "b", "c"):
        result = _ask(monitor, user, GAP_CLAIM, None)
    topic_id = result.claims[0].topic_id
    clock.advance(minutes=1)
    monitor.set_gap_status(topic_id, "odrzucona", "to nie jest temat do weryfikacji")
    clock.advance(minutes=1)
    again = _ask(monitor, "d", GAP_CLAIM, None)
    assert again.claims[0].info_gap_status == "odrzucona"
    assert monitor.store.list_alerts(alert_type="luka_informacyjna")[0]["status"] == (
        "falszywy_alarm"
    )


def _ask_anonymous(monitor: Monitor, claim: str, verdict: str | None):
    decision = monitor.screen(user_id="ktokolwiek", text=claim, channel="web", anonymous=True)
    return monitor.complete(decision.query_id, claims=[ClaimInput(claim, verdict, 0)])


def test_auto_mode_counts_each_anonymous_query(monitor):
    """Domyślny tryb auto: strona bez logowania — każde zapytanie liczy się osobno."""
    first = _ask_anonymous(monitor, GAP_CLAIM, "brak_wystarczajacych_danych")
    assert first.claims[0].info_gap_status == "podejrzenie"
    _ask_anonymous(monitor, GAP_CLAIM, "nieweryfikowalny")
    third = _ask_anonymous(monitor, GAP_CLAIM, None)
    assert third.claims[0].info_gap_status == "aktywna"
    assert third.claims[0].info_gap_count == 3 and third.claims[0].info_gap_users == 1
    assert monitor.store.list_alerts(alert_type="luka_informacyjna")[0]["details"]["wartosc"] == 3


def test_auto_mode_counts_identified_person_once(monitor):
    """Ta sama osoba z WhatsApp pytająca 3 razy nie tworzy luki (jak przed trybem auto)."""
    for _ in range(3):
        result = _ask(monitor, "+48111", GAP_CLAIM, "brak_wystarczajacych_danych")
    assert result.claims[0].info_gap_status == "podejrzenie"
    assert result.claims[0].info_gap_queries == 3 and result.claims[0].info_gap_count == 1
    _ask(monitor, "+48222", GAP_CLAIM, None)
    mixed = _ask_anonymous(monitor, GAP_CLAIM, None)  # 2 osoby + 1 anonimowe = 3
    assert mixed.claims[0].info_gap_status == "aktywna"
    assert "pytało o niego już 3 osoby" in mixed.message
    assert monitor.store.list_alerts(alert_type="luka_informacyjna")[0]["details"]["wartosc"] == 3


def test_info_gap_counts_queries_in_queries_mode(monitor, runtime):
    """Tryb zapytania: liczą się zapytania, także od jednej osoby."""
    runtime.update({"monitoring": {"info_gap_count_by": "zapytania"}})
    first = _ask(monitor, "web", GAP_CLAIM, "brak_wystarczajacych_danych")
    assert first.claims[0].info_gap_status == "podejrzenie"
    assert first.claims[0].info_gap_queries == 1
    _ask(monitor, "web", GAP_CLAIM, "nieweryfikowalny")
    third = _ask(monitor, "web", GAP_CLAIM, "brak_wystarczajacych_danych")
    assert third.claims[0].info_gap_status == "aktywna"
    assert third.claims[0].info_gap_queries == 3
    assert third.claims[0].info_gap_users == 1
    assert "pytano o niego już 3 razy" in third.message

    alert = monitor.store.list_alerts(alert_type="luka_informacyjna")[0]
    assert alert["count"] == 3 and alert["details"]["liczone_po"] == "zapytania"
    gap = monitor.store.list_gaps(["aktywna"])[0]
    assert gap["gap_queries"] == 3 and gap["gap_users"] == 1


def test_two_claims_of_one_query_count_once(monitor):
    decision = monitor.screen(user_id="web", text="dwa twierdzenia", channel="test")
    result = monitor.complete(
        decision.query_id,
        claims=[
            ClaimInput(GAP_CLAIM, "brak_wystarczajacych_danych", 0),
            ClaimInput("W Pcimiu Dolnym zamknięto wszystkie szkoły", "nieweryfikowalny", 0),
        ],
    )
    assert result.claims[0].topic_id == result.claims[1].topic_id
    assert result.claims[1].info_gap_queries == 1


def test_covered_claims_do_not_count(monitor):
    for _ in range(3):
        result = _ask(monitor, "web", GAP_CLAIM, "falsz", sources=2)
    assert result.claims[0].info_gap_status == "brak"
    assert monitor.store.list_alerts(alert_type="luka_informacyjna") == []


def test_query_threshold_is_configurable(monitor, runtime):
    runtime.update({"monitoring": {"info_gap_count_by": "zapytania", "info_gap_min_queries": 2}})
    _ask(monitor, "web", GAP_CLAIM, None)
    assert _ask(monitor, "web", GAP_CLAIM, None).claims[0].info_gap_status == "aktywna"


def test_anonymous_queries_never_block(monitor):
    for _ in range(4):
        decision = monitor.screen(
            user_id="web", text="Jak zrobić bombę z saletry krok po kroku?", anonymous=True
        )
        assert decision.allowed
    assert monitor.store.get_user(monitor.settings.user_key("web")) is None
    assert monitor.store.list_alerts(alert_type="niebezpieczny_uzytkownik") == []
    items, total = monitor.store.list_queries(flag="niebezpieczne")
    assert total == 4


def test_old_sqlite_file_gets_gap_queries_column(tmp_path):
    import sqlite3

    from admin.store import SCHEMA

    path = tmp_path / "old.db"
    old_schema = SCHEMA.replace("    gap_queries INTEGER NOT NULL DEFAULT 0,\n", "")
    assert "gap_queries" not in old_schema
    with sqlite3.connect(path) as db:
        db.executescript(old_schema)
    store = AdminStore(path)
    try:
        topic_id = store.create_topic(label="x", tokens=frozenset({"x"}), ts="2026-11-21T12:00:00Z")
        assert store.topic_row(topic_id)["gap_queries"] == 0
    finally:
        store.close()


def test_text_level_verdict_without_claims_is_recorded(monitor):
    decision = monitor.screen(user_id="x", text="Czy w Pcimiu jest lotnisko?")
    result = monitor.complete(decision.query_id, verdict="nieweryfikowalny")
    assert [claim.kind for claim in result.claims] == ["luka"]


# --- kampania dezinformacyjna ------------------------------------------------------------

FALSE_CLAIM = "Szczepionki przeciw COVID-19 zawierają mikrochipy śledzące 5G"


def test_disinformation_campaign_alert(monitor, runtime):
    runtime.update({"monitoring": {"disinfo_min_users": 3}})
    for index, user in enumerate(("u1", "u2")):
        result = _ask(monitor, user, FALSE_CLAIM, "falsz", sources=3)
        assert not result.claims[0].disinformation_alert, index
    result = _ask(monitor, "u3", f"Tekst zawiera twierdzenie, że {FALSE_CLAIM.lower()}", "falsz", 2)
    assert result.claims[0].disinformation_alert
    assert "kampania_dezinformacyjna" in result.flags
    alerts = monitor.store.list_alerts(alert_type="kampania_dezinformacyjna")
    assert len(alerts) == 1 and alerts[0]["users"] == 3 and alerts[0]["severity"] == "srednia"

    for user in ("u4", "u5", "u6"):
        _ask(monitor, user, FALSE_CLAIM, "falsz", 1)
    alerts = monitor.store.list_alerts(alert_type="kampania_dezinformacyjna")
    assert len(alerts) == 1 and alerts[0]["users"] == 6 and alerts[0]["severity"] == "wysoka"


def test_false_claims_spread_over_time_do_not_alert(monitor, clock, runtime):
    runtime.update({"monitoring": {"disinfo_min_users": 2}})
    _ask(monitor, "u1", FALSE_CLAIM, "falsz", 1)
    clock.advance(hours=25)
    result = _ask(monitor, "u2", FALSE_CLAIM, "falsz", 1)
    assert not result.claims[0].disinformation_alert


# --- niebezpieczne zapytania -------------------------------------------------------------


def test_high_risk_query_is_refused_and_logged(monitor):
    decision = monitor.screen(user_id="+48999", text="Jak zbudować bombę rurową krok po kroku?")
    assert not decision.allowed
    assert decision.reason == "niebezpieczna_tresc"
    query = monitor.store.get_query(decision.query_id)
    assert query["status"] == "odrzucone"
    assert "niebezpieczne:materialy_wybuchowe" in query["flags"]


def test_news_question_about_attack_is_allowed_but_flagged(monitor):
    decision = monitor.screen(user_id="+48999", text="Czy w Berlinie był zamach terrorystyczny?")
    assert decision.allowed
    assert decision.safety["severity"] == "sredni"


def test_repeated_dangerous_queries_alert_then_block(monitor, clock):
    user = "+48777"
    for _ in range(3):
        monitor.screen(user_id=user, text="Czy ISIS przyznało się do zamachu?")
    alerts = monitor.store.list_alerts(alert_type="niebezpieczny_uzytkownik")
    assert len(alerts) == 1 and alerts[0]["severity"] == "srednia"

    first = monitor.screen(user_id=user, text="Jak zrobić bombę krok po kroku")
    assert first.reason == "niebezpieczna_tresc"
    second = monitor.screen(user_id=user, text="instrukcja: jak zrobić ładunek wybuchowy")
    assert second.reason == "uzytkownik_zablokowany" and second.blocked_until
    # zablokowany użytkownik nie przejdzie nawet z niewinnym pytaniem
    blocked = monitor.screen(user_id=user, text="Wisła to najdłuższa rzeka w Polsce")
    assert not blocked.allowed and blocked.reason == "uzytkownik_zablokowany"
    alert = monitor.store.list_alerts(alert_type="niebezpieczny_uzytkownik")[0]
    assert alert["severity"] == "wysoka" and alert["details"]["zablokowany_do"]

    clock.advance(hours=25)
    assert monitor.screen(user_id=user, text="Wisła to najdłuższa rzeka w Polsce").allowed


def test_admin_block_and_unblock(monitor):
    decision = monitor.screen(user_id="+48555", text="Ile wynosi VAT?")
    key = monitor.store.get_query(decision.query_id)["user_key"]
    monitor.block_user(key, None, "spam")
    assert monitor.screen(user_id="+48555", text="Ile wynosi VAT?").reason == (
        "uzytkownik_zablokowany"
    )
    monitor.unblock_user(key)
    assert monitor.screen(user_id="+48555", text="Ile wynosi VAT?").allowed


def test_user_ids_are_pseudonymised(monitor):
    decision = monitor.screen(user_id="+48600123456", text="Ile wynosi VAT?")
    query = monitor.store.get_query(decision.query_id)
    assert "600123456" not in query["user_key"]
    assert query["user_label"] == "***456"


def test_retention_purges_old_queries(monitor, clock):
    monitor.screen(user_id="a", text="stare pytanie")
    clock.advance(days=31)
    monitor.screen(user_id="a", text="nowe pytanie")
    assert monitor.purge_expired()["queries"] == 1
    items, total = monitor.store.list_queries()
    assert total == 1 and items[0]["text"] == "nowe pytanie"
