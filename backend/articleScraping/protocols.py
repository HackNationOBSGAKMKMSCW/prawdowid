"""Small collaborator interfaces used by the independently callable scrape stage."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from apiReading.models import ReadingResult
from textAnalysis.container import AnalysisDataContainer


@dataclass(frozen=True)
class CandidateLink:
    """A discovered link with its trust tier retained until quota selection."""

    url: str
    source: str


@dataclass(frozen=True)
class RawArticle:
    """Whitelisted data returned by an article extractor."""

    text: str
    title: str | None = None
    author: str | None = None
    date: str | None = None
    page_url: str | None = None
    resolved_page_url: str | None = None


class LinkSource(Protocol):
    def extract(
        self,
        analysis: AnalysisDataContainer,
        reading_results: Sequence[ReadingResult],
    ) -> list[CandidateLink]: ...


class ArticleExtractor(Protocol):
    async def extract(self, url: str) -> RawArticle: ...


class Clock(Protocol):
    def now(self) -> datetime: ...


class SystemClock:
    def now(self) -> datetime:
        from datetime import UTC

        return datetime.now(UTC)
