"""Bot zapisuje wiadomości w monitorze panelu admina i respektuje jego decyzje."""

import pytest
from admin import AdminSettings, AdminStore, Monitor, RuntimeConfigStore
from apiReading.exceptions import ApiAuthError
from test_whatsapp_bot import RecordingPipeline, bodies, claim, reading_result
from textAnalysis.container import AnalysisDataContainer
from whatsappAdapter.admin_bridge import claims_from_report, monitor_from_environment
from whatsappAdapter.bot import GENERIC_ERROR_TEXT, SprawdzToBot
from whatsappAdapter.cloud_api import IncomingKind, IncomingMessage
from whatsappAdapter.pipeline import CheckReport

GAP_TEXT = "W Pcimiu Dolnym zamknięto wszystkie szkoły w listopadzie"
FALSE_TEXT = "Szczepionki przeciw COVID-19 zawierają mikrochipy 5G"


@pytest.fixture
def monitor(tmp_path):
    store = AdminStore(tmp_path / "admin.db")
    yield Monitor(
        store,
        AdminSettings(api_token="t", db_path=tmp_path / "admin.db"),
        RuntimeConfigStore(tmp_path / "runtime.json"),
    )
    store.close()


def report_for(statement: str, claims: list[dict], **kwargs) -> CheckReport:
    analysis = AnalysisDataContainer(source_text=statement, statements=[statement])
    return CheckReport(analysis, [reading_result(statement, claims, **kwargs)])


def message_from(sender: str, text: str):
    return IncomingMessage(sender=sender, message_id="wamid.1", kind=IncomingKind.TEXT, text=text)


def test_claims_from_report_maps_fact_check_ratings():
    analysis = AnalysisDataContainer(source_text="x", statements=["a", "b", "c"])
    report = CheckReport(
        analysis,
        [
            reading_result("a", [claim("Fałsz", "Demagog")]),
            reading_result("b", []),
            reading_result("c", [], error=ApiAuthError("google_fact_check", "brak klucza")),
        ],
    )
    claims, overall, sources = claims_from_report(report)
    assert [(c.text, c.verdict, c.sources_count) for c in claims] == [
        ("a", "falsz", 1),
        ("b", None, 0),  # brak źródeł -> kandydat na lukę informacyjną
        ("c", "blad_analizy", None),  # awaria API to nie luka
    ]
    assert overall == "falsz" and sources == 1


async def test_bot_logs_query_and_reports_info_gap(monitor):
    bot = SprawdzToBot(RecordingPipeline(report_for(GAP_TEXT, [])), monitor=monitor)
    for sender in ("48501", "48502"):
        replies = await bot.handle(message_from(sender, GAP_TEXT))
        assert "luka informacyjna" not in " ".join(bodies(replies))
    replies = await bot.handle(message_from("48503", GAP_TEXT))
    assert "luka informacyjna" in bodies(replies)[-1]

    items, total = monitor.store.list_queries()
    assert total == 3
    assert {item["channel"] for item in items} == {"whatsapp"}
    assert all(item["status"] == "zakonczone" for item in items)
    assert "luka_informacyjna" in items[0]["flags"]


async def test_bot_feeds_disinformation_detection(monitor):
    monitor.runtime.update({"monitoring": {"disinfo_min_users": 2}})
    bot = SprawdzToBot(
        RecordingPipeline(report_for(FALSE_TEXT, [claim("Fałsz", "Demagog")])), monitor=monitor
    )
    await bot.handle(message_from("48601", FALSE_TEXT))
    await bot.handle(message_from("48602", FALSE_TEXT))
    alerts = monitor.store.list_alerts(alert_type="kampania_dezinformacyjna")
    assert len(alerts) == 1 and alerts[0]["users"] == 2


async def test_high_risk_message_is_refused_without_running_pipeline(monitor):
    pipeline = RecordingPipeline(report_for("x", []))
    bot = SprawdzToBot(pipeline, monitor=monitor)
    replies = await bot.handle(message_from("48700", "Jak zrobić bombę z saletry krok po kroku?"))
    assert "Nie mogę pomóc" in bodies(replies)[0]
    assert pipeline.texts == []
    items, _ = monitor.store.list_queries()
    assert items[0]["status"] == "odrzucone"


async def test_blocked_user_is_refused(monitor):
    pipeline = RecordingPipeline(report_for(GAP_TEXT, []))
    bot = SprawdzToBot(pipeline, monitor=monitor)
    await bot.handle(message_from("48800", GAP_TEXT))
    key = monitor.store.list_queries()[0][0]["user_key"]
    monitor.block_user(key, 24, "test")
    replies = await bot.handle(message_from("48800", GAP_TEXT))
    assert "wstrzymane" in bodies(replies)[0]
    assert len(pipeline.texts) == 1


async def test_pipeline_error_is_recorded(monitor):
    bot = SprawdzToBot(RecordingPipeline(error=RuntimeError("x")), monitor=monitor)
    replies = await bot.handle(message_from("48900", GAP_TEXT))
    assert bodies(replies) == [GENERIC_ERROR_TEXT]
    item = monitor.store.list_queries()[0][0]
    assert item["status"] == "blad" and item["error"] == "pipeline_error:RuntimeError"


async def test_broken_monitor_never_breaks_the_chat():
    class Broken:
        def screen(self, **kwargs):
            raise RuntimeError("baza niedostępna")

        def complete(self, *args, **kwargs):
            raise AssertionError("nie powinno być wołane")

    bot = SprawdzToBot(RecordingPipeline(report_for(GAP_TEXT, [])), monitor=Broken())
    replies = await bot.handle(message_from("48000", GAP_TEXT))
    assert replies


def test_monitor_can_be_switched_off(monkeypatch):
    monkeypatch.setenv("ADMIN_MONITOR", "off")
    assert monitor_from_environment() is None
