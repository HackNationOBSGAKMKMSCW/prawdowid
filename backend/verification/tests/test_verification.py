"""Verification flow: event order, independent assessments, article mapping, module contracts."""

import asyncio
from datetime import UTC, date, datetime
from types import SimpleNamespace

import pytest
from articleScraping.models import ScrapedArticle, ScrapingReport

from verification import Stages, run, start, stream
from verification.mapping import to_reference_sources, to_truth_sources

SUBMITTED = datetime(2026, 11, 22, 8, 30, tzinfo=UTC)
USER_INPUT = "  Szczepienia na COVID są obowiązkowe od przyszłego tygodnia!!  "
ARTICLE_TEXT = "Szczepienia przeciw COVID-19 w Polsce są dobrowolne i bezpłatne."


def scraping_report(*articles: ScrapedArticle) -> ScrapingReport:
    return ScrapingReport(
        submitted_at=SUBMITTED,
        user_input=USER_INPUT,
        articles=list(articles),
        sources=[],
        distinct_sites=len({article.site for article in articles}),
        min_sites_met=len({article.site for article in articles}) >= 2,
        failures=[],
        finished_at=datetime(2026, 11, 22, 8, 30, 5, tzinfo=UTC),
    )


ARTICLES = (
    ScrapedArticle(
        url="https://www.gov.pl/web/gis/szczepienia",
        site="gov.pl/web/gis",
        title="Szczepienia przeciw COVID-19",
        published_at=datetime(2026, 10, 1, 9, tzinfo=UTC),
        text=ARTICLE_TEXT,
        publisher="GIS",
        source="trusted_source",
    ),
    ScrapedArticle(
        url="https://demagog.org.pl/fake_news/x",
        site="demagog.org.pl",
        title=None,
        text="Nie ma obowiązku szczepień przeciw COVID-19.",
        author="Jan Kowalski",
        source="fact_check",
    ),
    ScrapedArticle(url="https://empty.example/", site="empty.example", text="   "),
)


class Recorder:
    def __init__(self, input_delay=0.0, claims_delay=0.0, input_error=None, claims_error=None):
        self.input_delay, self.claims_delay = input_delay, claims_delay
        self.input_error, self.claims_error = input_error, claims_error
        self.input_args = None
        self.claims_args = None
        self.analysis = SimpleNamespace(statements=["Szczepienia na COVID są obowiązkowe."])

    def stages(self, report=None, analyze_error=None) -> Stages:
        async def analyze(text, submitted_at):
            if analyze_error:
                raise analyze_error
            assert text == USER_INPUT and submitted_at == SUBMITTED
            return self.analysis

        async def read(analysis):
            return ["reading-result"]

        async def search_trusted(analysis):
            return "trusted-report"

        async def scrape(analysis, results, trusted, submitted_at):
            assert (results, trusted, submitted_at) == (
                ["reading-result"],
                "trusted-report",
                SUBMITTED,
            )
            return report or scraping_report(*ARTICLES)

        async def assess_input(user_input, sources, article_date):
            self.input_args = (user_input, sources, article_date)
            await asyncio.sleep(self.input_delay)
            if self.input_error:
                raise self.input_error
            return {"manipulation": {"score": 10}, "dates": {"dates_consistent": True}}

        async def assess_claims(analysis, results, sources):
            self.claims_args = (analysis, results, sources)
            await asyncio.sleep(self.claims_delay)
            if self.claims_error:
                raise self.claims_error
            return {"verdict": "falszywy", "summary": "s", "claims": []}

        return Stages(analyze, read, search_trusted, scrape, assess_input, assess_claims)


@pytest.fixture
def no_verdict_schemas(monkeypatch):
    """Fakes do not need real ReferenceSource objects."""
    monkeypatch.setattr("verification.service.to_reference_sources", lambda report: ["ref"])


async def collect(recorder: Recorder, **kwargs):
    stages = recorder.stages(**kwargs)
    return [event async for event in stream(USER_INPUT, submitted_at=SUBMITTED, stages=stages)]


async def test_events_arrive_evidence_first_then_by_finish_time(no_verdict_schemas):
    events = await collect(Recorder(input_delay=0.05))
    assert [event.part for event in events] == ["evidence", "claims_verdict", "input_analysis"]
    assert {event.status for event in events} == {"ok"}
    assert len({event.request_id for event in events}) == 1

    events = await collect(Recorder(claims_delay=0.05))
    assert [event.part for event in events] == ["evidence", "input_analysis", "claims_verdict"]

    evidence = events[0].data
    assert evidence["statements"] == ["Szczepienia na COVID są obowiązkowe."]
    assert evidence["scraping"]["user_input"] == USER_INPUT
    assert len(evidence["scraping"]["articles"]) == 3


async def test_assessments_get_unchanged_input_articles_and_submission_date(no_verdict_schemas):
    recorder = Recorder()
    await collect(recorder)
    user_input, sources, article_date = recorder.input_args
    assert user_input == USER_INPUT
    assert article_date == date(2026, 11, 22)
    assert [source["id"] for source in sources] == ["art1", "art2"]  # empty article skipped
    analysis, results, references = recorder.claims_args
    assert analysis is recorder.analysis and results == ["reading-result"]
    assert references == ["ref"]


async def test_failure_of_one_assessment_does_not_affect_the_other(no_verdict_schemas):
    events = await collect(Recorder(claims_error=RuntimeError("model down")))
    by_part = {event.part: event for event in events}
    assert by_part["input_analysis"].status == "ok"
    claims = by_part["claims_verdict"]
    assert claims.status == "error" and claims.data is None
    assert (claims.error.kind, claims.error.message) == ("RuntimeError", "model down")


async def test_assessment_timeout_is_reported(no_verdict_schemas):
    job = start(
        USER_INPUT, submitted_at=SUBMITTED, stages=Recorder(input_delay=1).stages(), timeout=0.05
    )
    event = await job.input_analysis
    assert event.status == "error" and event.error.kind == "Timeout"
    assert (await job.claims_verdict).status == "ok"


async def test_evidence_failure_fails_both_assessments(no_verdict_schemas):
    recorder = Recorder()
    events = await collect(recorder, analyze_error=ValueError("no statements"))
    assert [event.status for event in events] == ["error"] * 3
    assert events[0].error.kind == "ValueError"
    assert {event.error.kind for event in events[1:]} == {"evidence_failed"}
    assert recorder.input_args is None and recorder.claims_args is None


async def test_job_parts_can_be_awaited_separately_and_report_collects_all(no_verdict_schemas):
    job = start(USER_INPUT, submitted_at=SUBMITTED, stages=Recorder().stages(), request_id="r1")
    claims = await job.claims_verdict
    assert claims.part == "claims_verdict" and claims.request_id == "r1"
    report = await job.report()
    assert report.request_id == "r1" and report.submitted_at == SUBMITTED
    assert report.input_analysis.data["manipulation"]["score"] == 10

    report = await run(USER_INPUT, submitted_at=SUBMITTED, stages=Recorder().stages())
    assert report.evidence.status == report.claims_verdict.status == "ok"


# --- mapping and contracts with the real analysis/ modules ------------------------------------


def test_articles_map_to_input_analysis_truth_sources():
    models = pytest.importorskip("inputDataAnalysis.models")
    sources = [
        models.TruthSource.model_validate(s) for s in to_truth_sources(scraping_report(*ARTICLES))
    ]
    assert [(s.id, s.url, s.published_at) for s in sources] == [
        ("art1", ARTICLES[0].url, date(2026, 10, 1)),
        ("art2", ARTICLES[1].url, None),
    ]
    assert sources[0].content == ARTICLE_TEXT and sources[0].title == ARTICLES[0].title
    assert to_truth_sources(scraping_report()) == []


def test_articles_map_to_verdict_reference_sources():
    pytest.importorskip("prawdowid_analysis.schemas")
    sources = to_reference_sources(scraping_report(*ARTICLES))
    first, second = sources
    assert (first.source_id, first.kind, first.publisher, first.published_at) == (
        "art1",
        "korpus",
        "GIS",
        "2026-10-01",
    )
    assert first.fetched_at == "2026-11-22T08:30:05+00:00"
    assert (second.title, second.publisher, second.url) == ("", "demagog.org.pl", ARTICLES[1].url)


async def test_contract_with_real_input_data_analysis():
    module = pytest.importorskip("inputDataAnalysis")
    models = pytest.importorskip("inputDataAnalysis.models")
    seen = {}

    async def fake_call(system, user, schema):
        seen.setdefault("user", user)
        if schema is models.LLMManipulationResponse:
            return models.LLMManipulationResponse(fragments=[])
        return models.LLMDatesResponse(
            article_date_in_text="", text_category="other", recency_framing=0.0, dates=[]
        )

    async def assess_input(user_input, sources, article_date):
        return await module.analyze_async(user_input, sources, article_date, call=fake_call)

    stages = Recorder().stages()
    stages = Stages(**{**stages.__dict__, "assess_input": assess_input})
    job = start(USER_INPUT, submitted_at=SUBMITTED, stages=stages)
    event = await job.input_analysis
    job.cancel()
    assert event.status == "ok", event.error
    assert event.data["manipulation"]["manipulation_detected"] is False
    assert 'id="art1"' in seen["user"] and "2026-11-22" in seen["user"]


async def test_contract_with_real_verdict_pipeline(monkeypatch):
    pytest.importorskip("prawdowid_analysis.pipeline")
    from prawdowid_analysis.llm import LLMReply

    from verification import service

    answer = {
        "claim_interpretation": "Czy szczepienia na COVID są obowiązkowe.",
        "verdict": "falsz",
        "confidence": "wysoka",
        "reasoning_steps": ["[art1] mówi, że szczepienia są dobrowolne."],
        "evidence": [
            {
                "source_id": "art1",
                "quote": "Szczepienia przeciw COVID-19 w Polsce są dobrowolne",
                "stance": "zaprzecza",
                "explanation": "Dobrowolne, nie obowiązkowe",
            }
        ],
        "sources_reviewed": [{"source_id": "art1", "relevant": True, "why": "Temat"}],
        "conflicts": [],
        "missing_information": [],
        "explanation": "Źródło [art1] podaje, że szczepienia są dobrowolne.",
    }

    class Client:
        model = "atrapa"

        async def complete(self, messages):
            import json

            return LLMReply(content=json.dumps(answer, ensure_ascii=False), model="atrapa")

    async def assess_claims(analysis, results, sources):
        pipeline = service._analysis.verdict_pipeline()
        return await pipeline.run(
            analysis, [], extra_sources=sources, use_corpus=False, client=Client()
        )

    stages = Recorder().stages(report=scraping_report(ARTICLES[0]))
    stages = Stages(**{**stages.__dict__, "assess_claims": assess_claims})
    job = start(USER_INPUT, submitted_at=SUBMITTED, stages=stages)
    event = await job.claims_verdict
    job.cancel()
    assert event.status == "ok", event.error
    claim = event.data["claims"][0]
    assert claim["verdict"] == "falsz"
    assert claim["evidence"][0]["url"] == ARTICLES[0].url
