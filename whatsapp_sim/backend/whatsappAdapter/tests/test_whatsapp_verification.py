"""Tryb live: bot korzysta z tej samej weryfikacji co strona (verification -> CheckResponse)."""

from types import SimpleNamespace

import pytest
from admin import AdminSettings, AdminStore, Monitor, RuntimeConfigStore
from whatsappAdapter.admin_bridge import claims_from_report
from whatsappAdapter.bot import ANALYSIS_FAILED_TEXT, URL_REFUSED_TEXT, SprawdzToBot
from whatsappAdapter.cloud_api import IncomingKind, IncomingMessage
from whatsappAdapter.pipeline import VerificationPipeline

QUESTION = "Czy we Włoszech ostatnio odbywał się strajk generalny?"
CLAIM = "We Włoszech odbył się strajk generalny."


def ok(data: dict) -> dict:
    return {"status": "ok", "data": data}


def verification_report(claims: list[dict] | None = None, manipulation: dict | None = None):
    claims = (
        claims
        if claims is not None
        else [
            {
                "claim": CLAIM,
                "verdict": "prawda",
                "explanation": "Związki zawodowe ogłosiły strajk, opisały go agencje prasowe.",
                "evidence": [
                    {
                        "quote": "Strajk generalny objął cały kraj.",
                        "publisher": "ANSA",
                        "url": "https://www.ansa.it/strajk",
                        "published_at": "2026-11-20",
                    }
                ],
            }
        ]
    )
    return {
        "evidence": ok({"statements": [c["claim"] for c in claims]}),
        "input_analysis": ok(
            {
                "manipulation": manipulation
                or {"manipulation_detected": False, "score": 5, "fragments": []},
                "dates": {"dates_consistent": True, "issues": [], "extracted": []},
            }
        ),
        "claims_verdict": ok({"verdict": "prawda", "summary": "s", "claims": claims}),
    }


class FakeJob:
    def __init__(self, report: dict, evidence_status: str = "ok") -> None:
        self._report = report
        self.cancelled = False

        async def evidence():
            return SimpleNamespace(status=evidence_status, data=report["evidence"].get("data"))

        self._evidence = evidence

    @property
    def evidence(self):
        return self._evidence()

    async def report(self) -> dict:
        return self._report

    def cancel(self) -> None:
        self.cancelled = True


def pipeline_for(report: dict, **kwargs) -> tuple[VerificationPipeline, list[str]]:
    started: list[str] = []

    def start(text: str) -> FakeJob:
        started.append(text)
        return FakeJob(report, **kwargs)

    return VerificationPipeline(start=start, check_timeout=5), started


def message(text: str) -> IncomingMessage:
    return IncomingMessage(sender="48500", message_id="wamid.1", kind=IncomingKind.TEXT, text=text)


def texts(replies: list[dict]) -> str:
    parts = []
    for reply in replies:
        if reply["type"] == "text":
            parts.append(reply["text"]["body"])
        else:
            parts.append(reply["interactive"]["body"]["text"])
    return "\n".join(parts)


async def test_bot_answers_with_the_same_result_as_the_website():
    pipeline, started = pipeline_for(verification_report())
    statuses: list[str] = []

    async def status(line: str) -> None:
        statuses.append(line)

    replies = await SprawdzToBot(pipeline).handle(message(QUESTION), status=status)

    assert started == [QUESTION]
    card, details = replies
    assert card["interactive"]["type"] == "cta_url"
    assert card["interactive"]["header"]["text"] == "Potwierdzone"
    assert card["interactive"]["action"]["parameters"]["url"] == "https://www.ansa.it/strajk"
    assert card["interactive"]["footer"]["text"] == "SprawdzTo · 1 źródło"
    body = details["text"]["body"]
    assert CLAIM in body and "✅ *Potwierdzone*" in body
    assert "Związki zawodowe ogłosiły strajk" in body
    assert "• ANSA · 2026\nhttps://www.ansa.it/strajk" in body
    assert statuses[-1] == "Porównuję twierdzenie ze źródłami i oceniam je…"


async def test_mixed_verdicts_and_manipulation_are_reported():
    claims = [
        {"claim": "A jest prawdą.", "verdict": "prawda", "explanation": "Tak.", "evidence": []},
        {"claim": "B jest fałszem.", "verdict": "falsz", "explanation": "Nie.", "evidence": []},
    ]
    manipulation = {
        "manipulation_detected": True,
        "score": 72,
        "fragments": [
            {
                "quote": "PILNE!!!",
                "start": 0,
                "end": 8,
                "category": "FALSE_URGENCY",
                "explanation": "Wykrzykniki mają przyspieszyć decyzję.",
                "confidence": 0.9,
            }
        ],
    }
    pipeline, _ = pipeline_for(verification_report(claims, manipulation))
    replies = await SprawdzToBot(pipeline).handle(message("PILNE!!! A jest prawdą, a B nie."))

    assert [reply["type"] for reply in replies] == ["text"]  # bez linku nie ma karty
    body = texts(replies)
    assert "*Różne oceny twierdzeń*" in body
    assert "✅ *Potwierdzone*" in body and "❌ *Fałszywe*" in body
    assert "Wskaźnik manipulacji: 72/100" in body
    assert "„PILNE!!!” — sztuczny pośpiech" in body


async def test_failed_verification_gets_a_polite_reply():
    report = verification_report()
    report["claims_verdict"] = {"status": "error", "error": {"kind": "RuntimeError"}}
    pipeline, _ = pipeline_for(report)
    replies = await SprawdzToBot(pipeline).handle(message(QUESTION))
    assert texts(replies) == ANALYSIS_FAILED_TEXT


async def test_bare_url_is_validated_like_on_the_website():
    class ApiFailure(Exception):
        code = "unsafe_url"

    async def refuse(url: str) -> str:
        raise ApiFailure(url)

    pipeline, started = pipeline_for(verification_report())
    pipeline._validate_url = refuse
    replies = await SprawdzToBot(pipeline).handle(message("http://127.0.0.1/admin"))
    assert texts(replies) == URL_REFUSED_TEXT and started == []


async def test_admin_panel_gets_website_verdicts(tmp_path):
    store = AdminStore(tmp_path / "admin.db")
    monitor = Monitor(
        store,
        AdminSettings(api_token="t", db_path=tmp_path / "admin.db"),
        RuntimeConfigStore(tmp_path / "runtime.json"),
    )
    try:
        pipeline, _ = pipeline_for(verification_report())
        report = await pipeline.check(QUESTION)
        claims, overall, sources = claims_from_report(report)
        assert [(c.text, c.verdict, c.sources_count) for c in claims] == [(CLAIM, "prawda", 1)]
        assert (overall, sources) == ("prawda", 1)

        await SprawdzToBot(pipeline, monitor=monitor).handle(message(QUESTION))
        rows, total = store.list_queries(limit=5)
        assert total == 1
        assert (rows[0]["channel"], rows[0]["verdict"]) == ("whatsapp", "prawda")
    finally:
        store.close()


@pytest.mark.parametrize("verdict", ["false", "misleading"])
def test_worst_claim_decides_the_admin_verdict(verdict):
    response = SimpleNamespace(
        claims=[
            SimpleNamespace(text="a", verdict="confirmed", sources=[]),
            SimpleNamespace(text="b", verdict=verdict, sources=[object()]),
        ]
    )
    from whatsappAdapter.pipeline import VerifiedReport

    _, overall, sources = claims_from_report(
        VerifiedReport(text="x", response=response, statements=["a", "b"])
    )
    assert overall == {"false": "falsz", "misleading": "czesciowo_potwierdzony"}[verdict]
    assert sources == 1
