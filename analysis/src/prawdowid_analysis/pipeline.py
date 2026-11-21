"""Potok werdyktu: twierdzenia + źródła wzorcowe -> `TextVerdict` (JSON).

Punkty wejścia:
- `run(analysis, reading_results)`: wyniki `textAnalysis.run()` i `apiReading.run()`
  z backendu (adapter czyta ich pola, bez importu backendu);
- `run_text(text)`: sam tekst, dzielony na zdania (bez LLM) – do testów i CLI;
- `verify_claims(statements, ...)`: wspólny rdzeń.

Dla każdego twierdzenia model dostaje wyłącznie źródła z puli wzorcowej:
- wpisy fact-checkingowe znalezione dla tego twierdzenia (`apiReading`),
- najlepsze fragmenty korpusu wzorcowego (BM25),
- źródła podane w zapytaniu (wszystkie, a przy dużej liczbie fragmentów – najlepsze).

Logi postępu idą na stderr, żeby stdout zawierał wyłącznie JSON.
"""

import asyncio
import re
import sys
import time
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from .adapters import claims_from_analysis, reading_errors, sources_from_reading_results
from .aggregate import aggregate
from .config import Settings
from .llm import ChatClient, OpenAIChatClient
from .prompts import prompt_version
from .schemas import ClaimVerdict, QuarantinedSource, ReferenceSource, TextVerdict
from .security import screen_claim, screen_sources
from .sources import Retriever, split_source
from .verdict import assess_claim

TOP_K_CORPUS = 5
TOP_K_USER = 5
MAX_FACT_CHECKS = 5
MIN_CLAIM_WORDS = 3


def _log(message: str) -> None:
    line = f"[werdykt] {message}"
    try:
        print(line, file=sys.stderr, flush=True)
    except UnicodeEncodeError:  # konsola bez UTF-8 (np. cp1250 w Windows)
        encoding = getattr(sys.stderr, "encoding", None) or "ascii"
        print(line.encode(encoding, "replace").decode(encoding), file=sys.stderr, flush=True)


def split_sentences(text: str) -> list[str]:
    """Prosty podział tekstu na zdania (do pełnej ekstrakcji służy textAnalysis)."""
    sentences = re.split(r"(?<=[.!?])\s+", " ".join(text.split()))
    return [s for s in sentences if len(s.split()) >= MIN_CLAIM_WORDS]


def _user_passages_for(
    claim: str, passages: list[ReferenceSource], retriever: Retriever | None
) -> list[ReferenceSource]:
    if len(passages) <= TOP_K_USER or retriever is None:
        return passages[:TOP_K_USER] if retriever is None else passages
    return [p for p, _ in retriever.search(claim, k=TOP_K_USER, min_score=0.0)]


def sources_for_claim(
    claim: str,
    *,
    corpus: Retriever | None,
    user_passages: list[ReferenceSource],
    user_retriever: Retriever | None,
    fact_checks: Sequence[ReferenceSource] = (),
) -> list[ReferenceSource]:
    selected: dict[str, ReferenceSource] = {}
    for source in list(fact_checks)[:MAX_FACT_CHECKS]:
        selected.setdefault(source.source_id, source)
    if corpus is not None:
        for passage, _ in corpus.search(claim, k=TOP_K_CORPUS):
            selected.setdefault(passage.source_id, passage)
    for passage in _user_passages_for(claim, user_passages, user_retriever):
        selected.setdefault(passage.source_id, passage)
    return list(selected.values())


async def verify_claims(
    statements: Sequence[str],
    *,
    fact_checks: Mapping[str, Sequence[ReferenceSource]] | None = None,
    extra_sources: Iterable[ReferenceSource] = (),
    corpus: Retriever | None = None,
    use_corpus: bool = True,
    client: ChatClient | None = None,
    settings: Settings | None = None,
    warnings: Sequence[str] = (),
) -> TextVerdict:
    started = time.perf_counter()
    settings = settings or Settings.from_environment()
    if corpus is None and use_corpus:
        corpus = Retriever.from_directory()
    quarantined: dict[str, QuarantinedSource] = {}

    def keep(sources: Iterable[ReferenceSource]) -> list[ReferenceSource]:
        clean, rejected = screen_sources(sources)
        for item in rejected:
            quarantined.setdefault(item.source_id, item)
        return clean

    # Źródła użytkownika sprawdzamy w całości: zatruty fragment odrzuca cały dokument.
    user_passages = [p for s in keep(extra_sources) for p in split_source(s)]
    user_retriever = Retriever(user_passages) if len(user_passages) > TOP_K_USER else None
    fact_checks = fact_checks or {}

    own_client = client is None
    chat = client or OpenAIChatClient(settings)
    semaphore = asyncio.Semaphore(settings.concurrency)
    all_sources: dict[str, ReferenceSource] = {}
    claim_warnings: list[str] = []

    async def one(index: int, statement: str) -> ClaimVerdict:
        screened = screen_claim(statement)
        claim_warnings.extend(f"T{index}: {w}" for w in screened.warnings)
        claim_sources = keep(
            sources_for_claim(
                screened.text,
                corpus=corpus if use_corpus else None,
                user_passages=user_passages,
                user_retriever=user_retriever,
                fact_checks=fact_checks.get(statement, ()),
            )
        )
        for source in claim_sources:
            all_sources.setdefault(source.source_id, source)
        async with semaphore:
            t0 = time.perf_counter()
            _log(f"Twierdzenie {index}/{len(statements)}: źródeł {len(claim_sources)}, ocena...")
            result = await assess_claim(
                f"T{index}",
                screened.text,
                claim_sources,
                chat,
                security_warnings=screened.warnings,
            )
            _log(
                f"Twierdzenie {index}/{len(statements)}: {result.verdict} "
                f"({time.perf_counter() - t0:.1f}s)"
            )
            return result

    try:
        claims = list(await asyncio.gather(*(one(i, s) for i, s in enumerate(statements, 1))))
    finally:
        if own_client and hasattr(chat, "aclose"):
            await chat.aclose()

    verdict, summary = aggregate(claims)
    quarantine_warnings = [
        f"Źródło [{q.source_id}] pominięto (kwarantanna): {', '.join(q.reasons)}."
        for q in quarantined.values()
    ]
    _log(
        f"Gotowe: {verdict} ({time.perf_counter() - started:.1f}s); "
        f"źródeł w kwarantannie: {len(quarantined)}"
    )
    return TextVerdict(
        verdict=verdict,
        summary=summary,
        claims=claims,
        sources=list(all_sources.values()),
        quarantined_sources=list(quarantined.values()),
        warnings=[*warnings, *sorted(claim_warnings), *quarantine_warnings],
        prompt_version=prompt_version(),
    )


async def run(
    analysis: Any,
    reading_results: Iterable[Any] | None = None,
    *,
    extra_sources: Iterable[ReferenceSource] = (),
    **kwargs: Any,
) -> TextVerdict:
    """Werdykt dla wyników `textAnalysis.run()` (+ opcjonalnie `apiReading.run()`)."""
    claims = claims_from_analysis(analysis)
    results = list(reading_results or [])
    warnings = [*claims.warnings, *reading_errors(results)]
    return await verify_claims(
        claims.statements,
        fact_checks=sources_from_reading_results(results),
        extra_sources=extra_sources,
        warnings=warnings,
        **kwargs,
    )


async def run_text(
    text: str, *, extra_sources: Iterable[ReferenceSource] = (), **kwargs: Any
) -> TextVerdict:
    """Werdykt dla zwykłego tekstu dzielonego na zdania."""
    return await verify_claims(split_sentences(text), extra_sources=extra_sources, **kwargs)
