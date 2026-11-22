"""Full verification flow: claims -> articles -> two independent assessments.

    job = start(text, submitted_at=...)
    await job.evidence          # VerificationEvent "evidence" (claims + scraped articles)
    await job.input_analysis    # "input_analysis": inputDataAnalysis (manipulation, dates)
    await job.claims_verdict    # "claims_verdict": prawdowid_analysis (verdict per claim)

    async for event in stream(text):   # evidence first, then the assessments as they finish
        ...

Both assessments start together once the evidence is ready and never wait for each other;
a failure (or timeout) of one is reported as its own ``status="error"`` event.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import Any

import observability
from articleScraping.models import ScrapingReport
from observability.context import new_request_id

from . import _analysis
from .mapping import to_reference_sources, to_truth_sources
from .models import PartError, VerificationEvent, VerificationReport

DEFAULT_ASSESSMENT_TIMEOUT = 240.0
_MESSAGE_LIMIT = 300


@dataclass(frozen=True)
class Evidence:
    analysis: Any
    reading_results: list[Any]
    trusted: Any
    scraping: ScrapingReport


# --- default stages (real modules, imported lazily) ------------------------------------------


async def _analyze(text: str, submitted_at: datetime) -> Any:
    import textAnalysis

    return await textAnalysis.run(text, started_at=submitted_at)


async def _read(analysis: Any) -> list[Any]:
    import apiReading

    return await apiReading.run(analysis)


async def _search_trusted(analysis: Any) -> Any:
    import trustedSources

    return await trustedSources.run(analysis)


async def _scrape(
    analysis: Any, results: list[Any], trusted: Any, submitted_at: datetime
) -> ScrapingReport:
    import articleScraping

    return await articleScraping.run(analysis, results, trusted=trusted, submitted_at=submitted_at)


async def _assess_input(user_input: str, sources: list[dict[str, Any]], article_date: date) -> Any:
    module = _analysis.input_analysis()
    return await module.analyze_async(user_input, sources, article_date)


async def _assess_claims(analysis: Any, results: list[Any], sources: list[Any]) -> Any:
    # use_corpus=False: analysis/data/sources holds test examples only, not real evidence.
    pipeline = _analysis.verdict_pipeline()
    return await pipeline.run(analysis, results, extra_sources=sources, use_corpus=False)


@dataclass(frozen=True)
class Stages:
    """Injectable stage calls (tests pass fakes)."""

    analyze: Callable[[str, datetime], Awaitable[Any]] = _analyze
    read: Callable[[Any], Awaitable[list[Any]]] = _read
    search_trusted: Callable[[Any], Awaitable[Any]] = _search_trusted
    scrape: Callable[[Any, list[Any], Any, datetime], Awaitable[ScrapingReport]] = _scrape
    assess_input: Callable[[str, list[dict[str, Any]], date], Awaitable[Any]] = _assess_input
    assess_claims: Callable[[Any, list[Any], list[Any]], Awaitable[Any]] = _assess_claims


# --- job ---------------------------------------------------------------------------------------


@dataclass
class VerificationJob:
    """Running verification. Every task resolves to a ``VerificationEvent`` (never raises)."""

    request_id: str
    submitted_at: datetime
    evidence: asyncio.Task[VerificationEvent]
    input_analysis: asyncio.Task[VerificationEvent]
    claims_verdict: asyncio.Task[VerificationEvent]
    _evidence: asyncio.Task[Evidence] = field(repr=False)

    @property
    def tasks(self) -> tuple[asyncio.Task[VerificationEvent], ...]:
        return (self.evidence, self.input_analysis, self.claims_verdict)

    async def events(self) -> AsyncIterator[VerificationEvent]:
        """Evidence first, then the assessments in the order they finish."""
        yield await self.evidence
        for next_done in asyncio.as_completed((self.input_analysis, self.claims_verdict)):
            yield await next_done

    async def report(self) -> VerificationReport:
        evidence, input_analysis, claims_verdict = await asyncio.gather(*self.tasks)
        return VerificationReport(
            request_id=self.request_id,
            submitted_at=self.submitted_at,
            evidence=evidence,
            input_analysis=input_analysis,
            claims_verdict=claims_verdict,
        )

    def cancel(self) -> None:
        for task in (*self.tasks, self._evidence):
            task.cancel()


def _now() -> datetime:
    return datetime.now(UTC)


def _ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)


def _error(exc: BaseException) -> PartError:
    if isinstance(exc, TimeoutError):
        return PartError(kind="Timeout", message="Przekroczono limit czasu oceny.")
    message = str(exc).strip() or type(exc).__name__
    return PartError(kind=type(exc).__name__, message=message[:_MESSAGE_LIMIT])


def _dump(value: Any) -> dict[str, Any]:
    return value.model_dump(mode="json") if hasattr(value, "model_dump") else dict(value)


async def _collect_evidence(stages: Stages, text: str, submitted_at: datetime) -> Evidence:
    with observability.stage("verification.evidence"):
        analysis = await stages.analyze(text, submitted_at)
        results, trusted = await asyncio.gather(
            stages.read(analysis), stages.search_trusted(analysis)
        )
        results = list(results)
        scraping = await stages.scrape(analysis, results, trusted, submitted_at)
    return Evidence(analysis, results, trusted, scraping)


async def _evidence_event(
    request_id: str, evidence: asyncio.Task[Evidence], started: float
) -> VerificationEvent:
    try:
        result = await evidence
    except Exception as exc:  # noqa: BLE001 - reported as an event
        event = VerificationEvent(
            request_id=request_id,
            part="evidence",
            status="error",
            error=_error(exc),
            duration_ms=_ms(started),
            finished_at=_now(),
        )
    else:
        scraping = result.scraping
        event = VerificationEvent(
            request_id=request_id,
            part="evidence",
            status="ok",
            data={
                "statements": list(getattr(result.analysis, "statements", None) or []),
                "scraping": scraping.model_dump(mode="json"),
            },
            duration_ms=_ms(started),
            finished_at=_now(),
        )
        observability.log_event(
            "verification_evidence",
            articles=len(scraping.articles),
            distinct_sites=scraping.distinct_sites,
            min_sites_met=scraping.min_sites_met,
            duration_ms=event.duration_ms,
        )
    if event.error is not None:
        observability.log_event(
            "verification_part",
            level="warning",
            part="evidence",
            status="error",
            error=event.error.kind,
            duration_ms=event.duration_ms,
        )
    return event


async def _assessment_event(
    request_id: str,
    part: str,
    evidence: asyncio.Task[Evidence],
    call: Callable[[Evidence], Awaitable[Any]],
    timeout: float | None,
) -> VerificationEvent:
    try:
        ready = await evidence
    except Exception as exc:  # noqa: BLE001
        return VerificationEvent(
            request_id=request_id,
            part=part,  # type: ignore[arg-type]
            status="error",
            error=PartError(
                kind="evidence_failed",
                message=f"Nie zebrano materiałów ({type(exc).__name__}); ocena nie wystartowała.",
            ),
            duration_ms=0,
            finished_at=_now(),
        )
    started = time.perf_counter()
    try:
        with observability.stage(f"verification.{part}"):
            result = await asyncio.wait_for(call(ready), timeout)
        event = VerificationEvent(
            request_id=request_id,
            part=part,
            status="ok",
            data=_dump(result),  # type: ignore[arg-type]
            duration_ms=_ms(started),
            finished_at=_now(),
        )
    except Exception as exc:  # noqa: BLE001 - one assessment never breaks the other
        event = VerificationEvent(
            request_id=request_id,
            part=part,
            status="error",
            error=_error(exc),  # type: ignore[arg-type]
            duration_ms=_ms(started),
            finished_at=_now(),
        )
    observability.log_event(
        "verification_part",
        level="info" if event.status == "ok" else "warning",
        part=part,
        status=event.status,
        error=event.error.kind if event.error else None,
        duration_ms=event.duration_ms,
    )
    return event


def start(
    text: str,
    *,
    submitted_at: datetime | None = None,
    request_id: str | None = None,
    stages: Stages | None = None,
    timeout: float | None = DEFAULT_ASSESSMENT_TIMEOUT,
) -> VerificationJob:
    """Start the flow in the running event loop and return at once.

    ``submitted_at`` is when the user sent the request (defaults to now); ``timeout`` limits
    each assessment separately.
    """
    stages = stages or Stages()
    submitted_at = submitted_at or _now()
    request_id = request_id or observability.current_request_id() or new_request_id()
    started = time.perf_counter()

    evidence = asyncio.create_task(_collect_evidence(stages, text, submitted_at))

    async def assess_input(ready: Evidence) -> Any:
        return await stages.assess_input(
            ready.scraping.user_input, to_truth_sources(ready.scraping), submitted_at.date()
        )

    async def assess_claims(ready: Evidence) -> Any:
        return await stages.assess_claims(
            ready.analysis, ready.reading_results, to_reference_sources(ready.scraping)
        )

    return VerificationJob(
        request_id=request_id,
        submitted_at=submitted_at,
        evidence=asyncio.create_task(_evidence_event(request_id, evidence, started)),
        input_analysis=asyncio.create_task(
            _assessment_event(request_id, "input_analysis", evidence, assess_input, timeout)
        ),
        claims_verdict=asyncio.create_task(
            _assessment_event(request_id, "claims_verdict", evidence, assess_claims, timeout)
        ),
        _evidence=evidence,
    )


async def stream(text: str, **kwargs: Any) -> AsyncIterator[VerificationEvent]:
    """Yield each part as soon as it is ready (evidence, then assessments by finish time)."""
    job = start(text, **kwargs)
    try:
        async for event in job.events():
            yield event
    finally:
        job.cancel()  # no-op when finished; stops the work if the consumer goes away


async def run(text: str, **kwargs: Any) -> VerificationReport:
    """Wait for all three parts."""
    return await start(text, **kwargs).report()


__all__: Sequence[str] = ("Evidence", "Stages", "VerificationJob", "run", "start", "stream")
