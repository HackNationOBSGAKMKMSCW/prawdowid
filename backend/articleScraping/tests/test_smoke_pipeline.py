import json
from datetime import UTC, datetime
from types import SimpleNamespace

import apiReading
import articleScraping
import pytest
import scripts.smoke_pipeline as smoke_pipeline
import textAnalysis
from articleScraping.models import ScrapedArticle, ScrapingReport


@pytest.mark.asyncio
async def test_json_smoke_output_includes_scraping_report_but_not_original_user_text(
    monkeypatch, capsys
) -> None:
    user_text = "private original text"
    analysis = SimpleNamespace()
    report = ScrapingReport(
        started_at=datetime(2026, 11, 21, 10, tzinfo=UTC),
        user_text=user_text,
        articles=[ScrapedArticle(url="https://news.example/1", text="article body")],
        failures=[],
        finished_at=datetime(2026, 11, 21, 10, 1, tzinfo=UTC),
    )

    async def fake_analysis(text: str):
        assert text == user_text
        return analysis

    async def fake_read(_analysis):
        return []

    async def fake_scrape(_analysis, _results):
        return report

    monkeypatch.setattr(textAnalysis, "run", fake_analysis)
    monkeypatch.setattr(apiReading, "run", fake_read)
    monkeypatch.setattr(articleScraping, "run", fake_scrape)

    assert await smoke_pipeline.main(user_text, as_json=True, scrape=True) == 0

    output = capsys.readouterr().out
    assert user_text not in output
    payload = json.loads(output)
    assert payload["scraping_report"]["articles"][0]["text"] == "article body"
    assert "user_text" not in payload["scraping_report"]
