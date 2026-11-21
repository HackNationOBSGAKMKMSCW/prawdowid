"""Fact-check pipelines used by the bot: the real packages or canned demo data."""

import asyncio
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol

from apiReading.models import (
    Category,
    FetchOutcome,
    FetchResult,
    Item,
    ReadingRequest,
    ReadingResult,
)
from textAnalysis.analysis import InputSanitizer
from textAnalysis.container import AnalysisDataContainer


@dataclass(frozen=True)
class CheckReport:
    """Everything the formatter needs to answer one user message."""

    analysis: AnalysisDataContainer
    results: list[ReadingResult]
    searched_full_text: bool = False
    demo: bool = False


# Called with a stage name and a count: ("searching", n) once statements are
# known; n == 0 means the whole message is searched instead.
Progress = Callable[[str, int], Awaitable[None]]


class FactCheckPipeline(Protocol):
    mode: str

    async def check(self, text: str, progress: Progress | None = None) -> CheckReport: ...


async def _report(progress: Progress | None, stage: str, count: int) -> None:
    if progress is not None:
        await progress(stage, count)


Analyze = Callable[[str], Awaitable[AnalysisDataContainer]]
ReadStatements = Callable[[AnalysisDataContainer], Awaitable[list[ReadingResult]]]
ReadFullText = Callable[[AnalysisDataContainer], Awaitable[ReadingResult]]


class LivePipeline:
    """Run ``textAnalysis`` and ``apiReading`` exactly as the main app does.

    Extracted statements are searched one by one. A message with no factual
    statements (often a plain question) is searched as a whole instead.
    """

    mode = "live"

    def __init__(
        self,
        *,
        analyze: Analyze | None = None,
        read_statements: ReadStatements | None = None,
        read_full_text: ReadFullText | None = None,
    ) -> None:
        if analyze is None or read_statements is None or read_full_text is None:
            import apiReading
            import textAnalysis

            analyze = analyze or textAnalysis.run
            read_statements = read_statements or apiReading.run
            read_full_text = read_full_text or apiReading.run_full_text
        self._analyze = analyze
        self._read_statements = read_statements
        self._read_full_text = read_full_text

    async def check(self, text: str, progress: Progress | None = None) -> CheckReport:
        analysis = await self._analyze(text)
        statements = [statement for statement in analysis.statements if statement.strip()]
        await _report(progress, "searching", len(statements))
        if statements:
            results = await self._read_statements(analysis)
            return CheckReport(analysis=analysis, results=results)
        result = await self._read_full_text(analysis)
        return CheckReport(analysis=analysis, results=[result], searched_full_text=True)


@dataclass(frozen=True)
class _DemoReview:
    rating: str
    publisher: str
    title: str
    review_date: str


@dataclass(frozen=True)
class _DemoTopic:
    slug: str
    # Every group must match; a group matches when any of its stems occurs.
    triggers: tuple[tuple[str, ...], ...]
    category: str
    statement: str
    claim: str
    claimant: str
    reviews: tuple[_DemoReview, ...]


_DEMO_SOURCE = "sprawdzto_demo"
_DEMO_TOPICS: tuple[_DemoTopic, ...] = (
    _DemoTopic(
        slug="szczepionki-autyzm",
        triggers=(("szczepion", "vaccin"), ("autyz", "autis")),
        category="Zdrowie i Medycyna",
        statement="Szczepionki powodują autyzm.",
        claim="Szczepionka MMR wywołuje autyzm u dzieci.",
        claimant="Wpisy w mediach społecznościowych",
        reviews=(
            _DemoReview(
                "Fałsz",
                "Redakcja Demo A",
                "Badania nie wykazały związku szczepionek z autyzmem",
                "2025-04-02T00:00:00Z",
            ),
            _DemoReview(
                "False",
                "Demo Fact Check B",
                "No link between MMR vaccine and autism",
                "2024-11-18T00:00:00Z",
            ),
        ),
    ),
    _DemoTopic(
        slug="5g-koronawirus",
        triggers=(("5g",), ("koronawirus", "covid", "wirus", "virus", "pandemi")),
        category="Zdrowie i Medycyna",
        statement="Sieć 5G rozprzestrzenia koronawirusa.",
        claim="Maszty 5G wywołały pandemię COVID-19.",
        claimant="Łańcuszek w komunikatorach",
        reviews=(
            _DemoReview(
                "Fałsz",
                "Redakcja Demo A",
                "Fale radiowe nie przenoszą wirusów",
                "2025-01-20T00:00:00Z",
            ),
        ),
    ),
    _DemoTopic(
        slug="wielki-mur",
        triggers=(("mur", "wall"), ("kosmos", "space", "orbit", "księżyc", "ksiezyc")),
        category="Kultura i Historia",
        statement="Wielki Mur Chiński widać gołym okiem z kosmosu.",
        claim="Wielki Mur to jedyna budowla widoczna gołym okiem z kosmosu.",
        claimant="Popularna ciekawostka",
        reviews=(
            _DemoReview(
                "Częściowo fałsz",
                "Redakcja Demo C",
                "Z niskiej orbity mur bywa widoczny tylko w idealnych warunkach",
                "2024-08-05T00:00:00Z",
            ),
        ),
    ),
    _DemoTopic(
        slug="woda-100-stopni",
        triggers=(("wod", "water"), ("wrze", "boil"), ("100",)),
        category="Nauka i Edukacja",
        statement="Woda wrze w temperaturze 100°C.",
        claim="Woda wrze w 100°C przy ciśnieniu atmosferycznym na poziomie morza.",
        claimant="Podręcznik fizyki",
        reviews=(
            _DemoReview(
                "Prawda",
                "Redakcja Demo C",
                "Tak, przy ciśnieniu ok. 1013 hPa",
                "2024-03-14T00:00:00Z",
            ),
        ),
    ),
)


def _demo_item(topic: _DemoTopic) -> Item:
    payload: dict[str, Any] = {
        "text": topic.claim,
        "claimant": topic.claimant,
        "claimReview": [
            {
                "publisher": {"name": review.publisher, "site": "example.org"},
                "title": review.title,
                "reviewDate": review.review_date,
                "url": f"https://example.org/sprawdzto-demo/{topic.slug}/{index}",
                "textualRating": review.rating,
                "languageCode": "pl",
            }
            for index, review in enumerate(topic.reviews, 1)
        ],
    }
    return Item(id=f"demo_{topic.slug}", source=_DEMO_SOURCE, payload=payload)


def _demo_result(query: str, items: list[Item], category: str) -> ReadingResult:
    now = datetime.now(UTC)
    return ReadingResult(
        request=ReadingRequest(
            query=query,
            categories=[Category.FACT_CHECK],
            language_code="pl",
            metadata={"analysis_category": category, "demo": True},
        ),
        results=[
            FetchOutcome(
                source=_DEMO_SOURCE,
                result=FetchResult(source=_DEMO_SOURCE, items=items, fetched_at=now),
            )
        ],
        items=items,
        categories_without_source=[],
        fetched_at=now,
        duration_ms=0,
    )


class DemoPipeline:
    """Offline stand-in that answers from a few built-in example topics.

    It needs no API keys or network, so the simulator can be shown anywhere.
    Every reply built from it is labelled as demo data by the formatter.
    """

    mode = "demo"

    def __init__(self, *, delay_seconds: float = 2.0) -> None:
        self.delay_seconds = delay_seconds

    async def check(self, text: str, progress: Progress | None = None) -> CheckReport:
        sanitized, warnings = InputSanitizer.sanitize(text)
        # Simulate the two slow steps of the live pipeline: analysis, then search.
        if self.delay_seconds > 0:
            await asyncio.sleep(self.delay_seconds / 2)

        lowered = sanitized.casefold()
        topics = [
            topic
            for topic in _DEMO_TOPICS
            if all(any(stem in lowered for stem in group) for group in topic.triggers)
        ]
        await _report(progress, "searching", len(topics))
        if self.delay_seconds > 0:
            await asyncio.sleep(self.delay_seconds / 2)

        category = topics[0].category if topics else "Ogólne / Inne"
        analysis = AnalysisDataContainer(
            source_text=sanitized,
            category=category,
            language_code="pl",
            confidence=0.9 if topics else 0.4,
            context_reasoning="Tryb demonstracyjny: dopasowanie do przykładowych tematów.",
            statements=[topic.statement for topic in topics],
            total_sentences=len([s for s in re.split(r"(?<=[.!?])\s+", sanitized) if s]),
            security_warnings=warnings,
        )

        if not topics:
            result = _demo_result(sanitized[:1000], [], category)
            return CheckReport(
                analysis=analysis, results=[result], searched_full_text=True, demo=True
            )
        results = [
            _demo_result(topic.statement, [_demo_item(topic)], topic.category) for topic in topics
        ]
        return CheckReport(analysis=analysis, results=results, demo=True)
