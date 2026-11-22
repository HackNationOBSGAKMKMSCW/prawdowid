"""Single end-to-end flow: text analysis -> API reading -> article scraping."""

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import apiReading
import articleScraping
import textAnalysis
import trustedSources
from apiReading.models import ReadingResult
from articleScraping.models import ScrapedArticle, ScrapingReport
from textAnalysis.container import AnalysisDataContainer
from trustedSources.models import TrustedSearchReport


@dataclass
class PipelineResult:
    """Everything produced by one run, kept together for further investigation."""

    analysis: AnalysisDataContainer
    reading_results: list[ReadingResult]
    scraping_report: ScrapingReport | None
    trusted_sources: TrustedSearchReport

    @property
    def user_submitted_at(self) -> datetime | None:
        """When the user typed/sent the text."""
        return self.analysis.started_at

    @property
    def user_text(self) -> str:
        """The whole text exactly as given by the user."""
        return self.analysis.original_text or self.analysis.source_text

    @property
    def user_link_articles(self) -> list[ScrapedArticle]:
        """Articles scraped from links the user gave (each carries its url)."""
        if self.scraping_report is None:
            return []
        return [a for a in self.scraping_report.articles if a.source == "user_text"]

    @property
    def fact_check_articles(self) -> list[ScrapedArticle]:
        """Articles scraped from links returned by the fact-check API."""
        if self.scraping_report is None:
            return []
        return [a for a in self.scraping_report.articles if a.source == "fact_check"]

    def to_dict(self) -> dict[str, Any]:
        """Final JSON-ready container: user input and time, API data, scraped articles."""
        report = self.scraping_report
        return {
            "user_submitted_at": (
                self.user_submitted_at.isoformat() if self.user_submitted_at else None
            ),
            "user_text": self.user_text,
            "user_link_articles": [a.model_dump(mode="json") for a in self.user_link_articles],
            "fact_check_articles": [a.model_dump(mode="json") for a in self.fact_check_articles],
            "trusted_sources": self.trusted_sources.model_dump(
                mode="json", exclude={"queries"}
            ),
            "scraping_failures": (
                [f.model_dump(mode="json") for f in report.failures] if report else []
            ),
            "reading_results": [r.model_dump(mode="json") for r in self.reading_results],
        }


def _is_bare_url(text: str) -> bool:
    candidate = text.strip()
    return candidate.startswith(("http://", "https://")) and not any(c.isspace() for c in candidate)


class UrlInputFetchError(RuntimeError):
    """A submitted URL could not be safely fetched and extracted."""


async def analyze_input(
    text: str,
    *,
    submitted_at: datetime | None = None,
    scrape: bool = True,
) -> AnalysisDataContainer:
    """Analyze the input, fetching a bare-URL input only once.

    The article is scraped first and its text analyzed directly; the scraping
    stage's URL cache then serves the later fact-check scrape without a refetch.
    """
    if scrape and _is_bare_url(text):
        url = text.strip()
        started_at = submitted_at or datetime.now(UTC)
        first = await articleScraping.run(AnalysisDataContainer(original_text=url))
        if first.articles:
            analysis = await textAnalysis.run(first.articles[0].text, started_at=started_at)
            analysis.original_text = text
            analysis.source_url = url
            return analysis
        raise UrlInputFetchError("Submitted URL could not be fetched safely")
    return await textAnalysis.run(text, started_at=submitted_at)


async def run_pipeline(text: str, *, scrape: bool = True) -> PipelineResult:
    """Run analysis, API and trusted-source searches, then optionally scrape evidence."""
    analysis = await analyze_input(text, scrape=scrape)
    results, trusted = await asyncio.gather(
        apiReading.run(analysis), trustedSources.run(analysis)
    )
    report = (
        await articleScraping.run(analysis, results, trusted=trusted) if scrape else None
    )
    return PipelineResult(
        analysis=analysis,
        reading_results=results,
        scraping_report=report,
        trusted_sources=trusted,
    )
