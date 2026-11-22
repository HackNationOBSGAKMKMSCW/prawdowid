import json
from datetime import UTC, datetime
from types import SimpleNamespace

import apiReading
import articleScraping
import pytest
import scripts.smoke_pipeline as smoke_pipeline
import textAnalysis
import trustedSources
from articleScraping.models import ScrapedArticle, ScrapingReport


@pytest.mark.asyncio
async def test_json_smoke_output_redacts_user_text_and_includes_articles(monkeypatch, capsys) -> None:
    user_text = "private original text https://user.example/a"
    submitted = datetime(2026, 11, 21, 9, 59, tzinfo=UTC)
    analysis = SimpleNamespace(original_text=user_text, source_text="", started_at=submitted)
    report = ScrapingReport(
        submitted_at=datetime(2026, 11, 21, 10, tzinfo=UTC),
        user_input=user_text,
        articles=[
            ScrapedArticle(
                url="https://user.example/a",
                text="user article body",
                author="Ann",
                published_at=datetime(2026, 1, 1, tzinfo=UTC),
                domain="user.example",
                source="user_text",
            ),
            ScrapedArticle(
                url="https://news.example/1",
                text="fc body",
                source="fact_check",
            ),
        ],
        sources=[],
        distinct_sites=2,
        min_sites_met=True,
        failures=[],
        finished_at=datetime(2026, 11, 21, 10, 1, tzinfo=UTC),
    )

    async def fake_analysis(text: str, **_kwargs):
        assert text == user_text
        return analysis

    async def fake_read(_analysis):
        return []

    trusted = trustedSources.TrustedSearchReport(queries=["q"], hits=[])

    async def fake_trusted(_analysis):
        return trusted

    async def fake_scrape(_analysis, _results, *, trusted=None):
        assert trusted is not None
        return report

    monkeypatch.setattr(textAnalysis, "run", fake_analysis)
    monkeypatch.setattr(apiReading, "run", fake_read)
    monkeypatch.setattr(trustedSources, "run", fake_trusted)
    monkeypatch.setattr(articleScraping, "run", fake_scrape)

    assert await smoke_pipeline.main(user_text, as_json=True, scrape=True) == 0

    output = capsys.readouterr().out
    assert user_text not in output
    payload = json.loads(output)
    assert payload["user_submitted_at"].startswith("2026-11-21T09:59")
    user_article = payload["user_link_articles"][0]
    assert user_article["url"] == "https://user.example/a"
    assert user_article["text"] == "user article body"
    assert user_article["author"] == "Ann"
    assert user_article["published_at"].startswith("2026-01-01")
    assert payload["fact_check_articles"][0]["text"] == "fc body"
    assert "user_text" not in payload


@pytest.mark.asyncio
async def test_pipeline_scrapes_by_default_and_returns_everything(monkeypatch) -> None:
    import pipeline

    analysis = SimpleNamespace()
    calls: list[str] = []

    async def fake_analysis(_text, **_kwargs):
        calls.append("analysis")
        return analysis

    async def fake_read(_analysis):
        calls.append("read")
        return ["r"]

    async def fake_trusted(_analysis):
        calls.append("trusted")
        return trustedSources.TrustedSearchReport(queries=[], hits=[])

    async def fake_scrape(_analysis, results, *, trusted=None):
        calls.append("scrape")
        assert results == ["r"]
        assert trusted is not None
        return "report"

    monkeypatch.setattr(textAnalysis, "run", fake_analysis)
    monkeypatch.setattr(apiReading, "run", fake_read)
    monkeypatch.setattr(trustedSources, "run", fake_trusted)
    monkeypatch.setattr(articleScraping, "run", fake_scrape)

    result = await pipeline.run_pipeline("x")
    assert calls[0] == "analysis"
    assert set(calls[1:]) == {"read", "trusted", "scrape"}
    assert (result.analysis, result.reading_results, result.scraping_report) == (
        analysis,
        ["r"],
        "report",
    )

    calls.clear()
    assert (await pipeline.run_pipeline("x", scrape=False)).scraping_report is None
    assert "scrape" not in calls


@pytest.mark.asyncio
async def test_bare_url_input_is_scraped_once_and_analyzed_from_article(monkeypatch) -> None:
    import pipeline

    url = "https://user.example/a"
    article = ScrapedArticle(url=url, text="article body", source="user_text")
    report = ScrapingReport(
        submitted_at=datetime(2026, 11, 21, tzinfo=UTC),
        user_input=url,
        articles=[article],
        sources=[],
        distinct_sites=1,
        min_sites_met=False,
        failures=[],
        finished_at=datetime(2026, 11, 21, tzinfo=UTC),
    )
    analyzed: list[str] = []

    async def fake_analysis(text, **_kwargs):
        analyzed.append(text)
        return SimpleNamespace(original_text=text, source_url=None)

    async def fake_read(_analysis):
        return []

    async def fake_scrape(_analysis, *_results, **_kwargs):
        return report

    async def fake_trusted(_analysis):
        return trustedSources.TrustedSearchReport(queries=[], hits=[])

    monkeypatch.setattr(textAnalysis, "run", fake_analysis)
    monkeypatch.setattr(apiReading, "run", fake_read)
    monkeypatch.setattr(trustedSources, "run", fake_trusted)
    monkeypatch.setattr(articleScraping, "run", fake_scrape)

    result = await pipeline.run_pipeline(url)
    assert analyzed == ["article body"]
    assert result.analysis.original_text == url
    assert result.analysis.source_url == url
