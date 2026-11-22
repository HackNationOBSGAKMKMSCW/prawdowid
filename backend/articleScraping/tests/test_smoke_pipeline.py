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
async def test_json_smoke_output_includes_scraping_report_but_not_original_user_text(
    monkeypatch, capsys
) -> None:
    user_text = "private original text"
    analysis = SimpleNamespace()
    report = ScrapingReport(
        submitted_at=datetime(2026, 11, 21, 10, tzinfo=UTC),
        user_input=user_text,
        articles=[ScrapedArticle(url="https://news.example/1", text="article body")],
        sources=[],
        distinct_sites=1,
        min_sites_met=False,
        failures=[],
        finished_at=datetime(2026, 11, 21, 10, 1, tzinfo=UTC),
    )

    async def fake_analysis(text: str):
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
    assert payload["scraping_report"]["articles"][0]["text"] == "article body"
    assert "user_input" not in payload["scraping_report"]
