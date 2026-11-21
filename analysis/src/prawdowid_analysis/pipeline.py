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
from collections.abc import Callable, Iterable, Mapping, Sequence
from datetime import datetime
from typing import Any

from .adapters import claims_from_analysis, partition_fact_checks, reading_warnings
from .aggregate import aggregate
from .config import Settings
from .freshness import (
    RECENCY_WEIGHT,
    annotate,
    archival_warning,
    is_archival,
    iso_timestamp,
    recency_factor,
    utc_now,
)
from .llm import ChatClient, OpenAIChatClient
from .prompts import prompt_version
from .schemas import (
    ClaimVerdict,
    InputSourceOut,
    QuarantinedSource,
    ReferenceSource,
    TextVerdict,
)
from .security import detect_injection, screen_claim, screen_sources
from .sources import CORPUS_LANGUAGE, Retriever, context_excerpt, expand_query, split_source
from .verdict import assess_claim

TOP_K_CORPUS = 5
TOP_K_USER = 5
MAX_FACT_CHECKS = 5
MIN_CLAIM_WORDS = 3
CANDIDATE_FACTOR = 3  # ilu kandydatów BM25 na miejsce rozważamy przy preferencji aktualności
CLAIM_FLAG_ARCHIVAL_SOURCES = "zrodla_archiwalne"


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


def _pick(
    hits: Sequence[tuple[ReferenceSource, float]],
    k: int,
    prefer: Callable[[ReferenceSource], float] | None,
) -> list[ReferenceSource]:
    """Top-k po wyniku BM25 pomnożonym przez premię za aktualność (`prefer`)."""
    if prefer is not None:
        hits = sorted(hits, key=lambda hit: hit[1] * prefer(hit[0]), reverse=True)
    return [source for source, _ in hits[: max(k, 0)]]


def sources_for_claim(
    claim: str,
    *,
    corpus: Retriever | None,
    user_passages: list[ReferenceSource],
    user_retriever: Retriever | None,
    fact_checks: Sequence[ReferenceSource] = (),
    shared_fact_checks: Retriever | None = None,
    prefer: Callable[[ReferenceSource], float] | None = None,
) -> list[ReferenceSource]:
    """Źródła dla twierdzenia. `prefer` zwraca mnożnik ≥ 1 za aktualność: z szerszej
    listy kandydatów BM25 wybieramy te, które są i trafne, i świeże."""
    widen = CANDIDATE_FACTOR if prefer is not None else 1
    selected: dict[str, ReferenceSource] = {}
    for source in list(fact_checks)[:MAX_FACT_CHECKS]:
        selected.setdefault(source.source_id, source)
    if shared_fact_checks is not None:
        budget = MAX_FACT_CHECKS - len(selected)
        # Wymagamy co najmniej jednego wspólnego słowa (wynik > 0), nie progu BM25:
        # pula bywa mała, a wtedy IDF jest niski nawet dla trafnych wpisów.
        hits = shared_fact_checks.search(claim, k=max(budget, 0) * widen, min_score=1e-9)
        for source in _pick(hits, budget, prefer):
            selected.setdefault(source.source_id, source)
    if corpus is not None:
        hits = corpus.search(claim, k=TOP_K_CORPUS * widen)
        for passage in _pick(hits, TOP_K_CORPUS, prefer):
            selected.setdefault(passage.source_id, passage)
    if user_retriever is not None and len(user_passages) > TOP_K_USER:
        hits = user_retriever.search(claim, k=TOP_K_USER * widen, min_score=0.0)
        user_selected = _pick(hits, TOP_K_USER, prefer)
    else:
        user_selected = _user_passages_for(claim, user_passages, user_retriever)
    for passage in user_selected:
        selected.setdefault(passage.source_id, passage)
    return list(selected.values())


async def verify_claims(
    statements: Sequence[str],
    *,
    fact_checks: Mapping[str, Sequence[ReferenceSource]] | None = None,
    shared_fact_checks: Iterable[ReferenceSource] = (),
    extra_sources: Iterable[ReferenceSource] = (),
    corpus: Retriever | None = None,
    use_corpus: bool = True,
    client: ChatClient | None = None,
    settings: Settings | None = None,
    warnings: Sequence[str] = (),
    keywords: Sequence[str] = (),
    source_text: str = "",
    models: Mapping[str, str] | None = None,
    now: datetime | None = None,
) -> TextVerdict:
    started = time.perf_counter()
    settings = settings or Settings.from_environment()
    now = now or utc_now()
    analyzed_at = iso_timestamp(now)
    max_age = settings.max_source_age_days

    def dated(source: ReferenceSource) -> ReferenceSource:
        """Wiek i flagi aktualności względem chwili analizy."""
        return annotate(source, now, max_age)

    def prefer(source: ReferenceSource) -> float:
        return 1.0 + RECENCY_WEIGHT * recency_factor(dated(source), max_age)

    def received(source: ReferenceSource) -> ReferenceSource:
        """Źródło przekazane w zapytaniu bez znacznika pobrania: pobrane teraz."""
        return (
            source if source.fetched_at else source.model_copy(update={"fetched_at": analyzed_at})
        )

    if corpus is None and use_corpus:
        corpus = Retriever.from_directory()
    quarantined: dict[str, QuarantinedSource] = {}

    def keep(sources: Iterable[ReferenceSource]) -> list[ReferenceSource]:
        clean, rejected = screen_sources(sources)
        for item in rejected:
            quarantined.setdefault(item.source_id, item)
        return clean

    fact_checks = {k: [received(s) for s in v] for k, v in (fact_checks or {}).items()}
    extra_sources = [received(s) for s in extra_sources]
    shared_fact_checks = [received(s) for s in shared_fact_checks]
    # Wszystkie źródła z wejścia (dokumenty, nie fragmenty) – do raportu z linkami.
    inputs: dict[str, ReferenceSource] = {}
    for source in [
        *extra_sources,
        *(s for v in fact_checks.values() for s in v),
        *shared_fact_checks,
    ]:
        inputs.setdefault(source.source_id, source)

    # Źródła użytkownika sprawdzamy w całości: zatruty fragment odrzuca cały dokument.
    user_passages = [p for s in keep(extra_sources) for p in split_source(s)]
    user_retriever = Retriever(user_passages) if len(user_passages) > TOP_K_USER else None
    shared_pool = keep(shared_fact_checks)
    shared_retriever = Retriever(shared_pool) if shared_pool else None

    own_client = client is None
    chat = client or OpenAIChatClient(settings)
    semaphore = asyncio.Semaphore(settings.concurrency)
    all_sources: dict[str, ReferenceSource] = {}
    claim_warnings: list[str] = []

    async def one(index: int, statement: str) -> ClaimVerdict:
        screened = screen_claim(statement)
        claim_warnings.extend(f"T{index}: {w}" for w in screened.warnings)
        context = context_excerpt(screened.text, source_text) if source_text else None
        if context and detect_injection(context):
            claim_warnings.append(
                f"T{index}: kontekst z oryginalnego tekstu pominięto – zawiera tekst "
                "przypominający polecenia dla modelu."
            )
            context = None
        claim_sources = [
            dated(source)
            for source in keep(
                sources_for_claim(
                    expand_query(screened.text, keywords),
                    corpus=corpus if use_corpus else None,
                    user_passages=user_passages,
                    user_retriever=user_retriever,
                    fact_checks=fact_checks.get(statement, ()),
                    shared_fact_checks=shared_retriever,
                    prefer=prefer,
                )
            )
        ]
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
                context=context,
                analysis_date=now.date().isoformat(),
                max_age_days=max_age,
            )
            if any(is_archival(s) for s in claim_sources):
                result = result.model_copy(
                    update={
                        "freshness_flags": sorted(
                            {*result.freshness_flags, CLAIM_FLAG_ARCHIVAL_SOURCES}
                        )
                    }
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
    dated_inputs = [dated(s) for s in inputs.values()]
    archival_warnings: dict[str, str] = {}
    for source in [*all_sources.values(), *dated_inputs]:
        document = source.source_id.split("#", 1)[0]  # fragmenty jednego dokumentu raz
        if is_archival(source) and document not in archival_warnings:
            archival_warnings[document] = archival_warning(
                source.model_copy(update={"source_id": document}), max_age
            )
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
        input_sources=input_source_report(dated_inputs, claims, quarantined),
        warnings=[
            *warnings,
            *sorted(claim_warnings),
            *quarantine_warnings,
            *archival_warnings.values(),
        ],
        analyzed_at=analyzed_at,
        max_source_age_days=max_age,
        models={**(models or {}), "werdykt": settings.model},
        prompt_version=prompt_version(),
    )


def input_source_report(
    inputs: Sequence[ReferenceSource],
    claims: Sequence[ClaimVerdict],
    quarantined_ids: Iterable[str],
) -> list[InputSourceOut]:
    """Każde źródło z wejścia z linkiem i informacją, co się z nim stało.

    Źródła użytkownika są dzielone na fragmenty (`ID#n`); status i powiązane
    twierdzenia liczymy dla całego dokumentu.
    """
    ids = {s.source_id for s in inputs}

    def document_id(passage_id: str) -> str | None:
        if passage_id in ids:
            return passage_id
        base = passage_id.rsplit("#", 1)[0]
        return base if base in ids else None

    shown: dict[str, list[str]] = {}
    cited: dict[str, list[str]] = {}
    for claim in claims:
        for passage_id in claim.source_ids:
            doc = document_id(passage_id)
            if doc and claim.claim_id not in shown.setdefault(doc, []):
                shown[doc].append(claim.claim_id)
        for evidence in claim.evidence:
            doc = document_id(evidence.source_id)
            if doc and evidence.quote_verified and claim.claim_id not in cited.setdefault(doc, []):
                cited[doc].append(claim.claim_id)

    rejected = set(quarantined_ids)
    report = []
    for source in inputs:
        sid = source.source_id
        if sid in rejected:
            status = "kwarantanna"
        elif cited.get(sid):
            status = "cytowane"
        elif shown.get(sid):
            status = "pokazane_modelowi"
        else:
            status = "nieuzyte"
        report.append(
            InputSourceOut(
                source_id=sid,
                kind=source.kind,
                title=source.title,
                publisher=source.publisher,
                url=source.url,
                published_at=source.published_at,
                provider=source.provider,
                rating=source.rating,
                fetched_at=source.fetched_at,
                age_days=source.age_days,
                freshness_flags=source.freshness_flags,
                status=status,
                shown_for_claims=shown.get(sid, []),
                cited_in_claims=cited.get(sid, []),
            )
        )
    return report


def language_mismatch_warnings(language_code: str | None, use_corpus: bool) -> list[str]:
    """Ostrzega, gdy język tekstu (z textAnalysis) różni się od języka korpusu.

    Wyszukiwanie BM25 dopasowuje słowa, więc tekst w innym języku zwykle nie
    znajdzie nic w polskim korpusie i dostanie „brak danych” bez innej przyczyny.
    """
    if not use_corpus or not language_code:
        return []
    primary = language_code.strip().lower().split("-")[0]
    if not primary or primary == CORPUS_LANGUAGE:
        return []
    return [
        f"Tekst jest w języku „{language_code}”, a korpus wzorcowy po polsku: wyszukiwanie "
        "w korpusie może nie znaleźć pasujących źródeł (wynik „brak danych” może wynikać "
        "z różnicy języków, a nie z braku informacji)."
    ]


def _as_result_list(reading_results: Any) -> list[Any]:
    """Przyjmuje listę wyników (`apiReading.run()`) albo pojedynczy wynik
    (`apiReading.run_full_text()`), także w postaci słownika po `model_dump()`."""
    if reading_results is None:
        return []
    if isinstance(reading_results, Mapping) or hasattr(reading_results, "request"):
        return [reading_results]
    return list(reading_results)


async def run(
    analysis: Any,
    reading_results: Any = None,
    *,
    extra_sources: Iterable[ReferenceSource] = (),
    warnings: Sequence[str] = (),
    **kwargs: Any,
) -> TextVerdict:
    """Werdykt dla wyników `textAnalysis.run()` i (opcjonalnie) `apiReading`.

    `reading_results` może pochodzić z `apiReading.run()` (lista, zapytanie na
    stwierdzenie), z `apiReading.run_full_text()` (jeden wynik dla całego tekstu)
    albo być ich połączeniem. Wpisy z zapytań niepasujących do żadnego stwierdzenia
    trafiają do wspólnej puli, z której każde twierdzenie dostaje pasujące wpisy.
    """
    claims = claims_from_analysis(analysis)
    results = _as_result_list(reading_results)
    pools = partition_fact_checks(results, claims.statements)
    language_warnings = language_mismatch_warnings(
        claims.language_code, kwargs.get("use_corpus", True)
    )
    return await verify_claims(
        claims.statements,
        fact_checks=pools.per_statement,
        shared_fact_checks=pools.shared,
        extra_sources=extra_sources,
        warnings=[*warnings, *claims.warnings, *reading_warnings(results), *language_warnings],
        keywords=claims.keywords,
        source_text=claims.source_text,
        **kwargs,
    )


async def run_text(
    text: str, *, extra_sources: Iterable[ReferenceSource] = (), **kwargs: Any
) -> TextVerdict:
    """Werdykt dla zwykłego tekstu dzielonego na zdania."""
    return await verify_claims(
        split_sentences(text), extra_sources=extra_sources, source_text=text, **kwargs
    )
