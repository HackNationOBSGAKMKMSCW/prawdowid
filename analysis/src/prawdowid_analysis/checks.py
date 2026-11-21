"""Kontrola deterministyczna odpowiedzi modelu i budowa wyniku `ClaimVerdict`.

Model nie ma ostatniego słowa. Kod egzekwuje reguły promptu, których złamania nie
da się wykluczyć samą instrukcją:

- dowód musi wskazywać istniejące źródło, a cytat musi w nim występować dosłownie
  (R7); w wyniku zapisujemy dokładny fragment źródła;
- "prawda" wymaga co najmniej jednego zweryfikowanego dowodu "potwierdza",
  "falsz" co najmniej jednego zweryfikowanego dowodu "zaprzecza" (R4, R5);
- "prawda" przy zweryfikowanym dowodzie "zaprzecza" to nierozstrzygnięta
  sprzeczność (R10);
- werdykt bez pokrycia jest obniżany do "brak_wystarczajacych_danych";
- "brak_wystarczajacych_danych" zawsze ma listę braków (R6);
- rozstrzygnięcie oparte wyłącznie na wpisach fact-checkingowych ma najwyżej
  pewność "srednia" (R13);
- każde źródło pokazane modelowi ma ocenę w `sources_reviewed` (R8);
- rozstrzygnięcie oparte wyłącznie na materiale archiwalnym dostaje flagę
  `werdykt_na_materiale_archiwalnym` i najwyżej pewność "srednia" (R11).

Każda zmiana względem odpowiedzi modelu trafia do `adjustments`.
"""

import re
from collections.abc import Sequence

from .freshness import is_archival
from .quotes import verify_quote
from .schemas import (
    VERDICT_LABELS_PL,
    ClaimVerdict,
    Confidence,
    EvidenceOut,
    ModelVerdict,
    ReferenceSource,
    SourceReviewOut,
)

NO_DATA = "brak_wystarczajacych_danych"
FLAG_VERDICT_ON_ARCHIVAL = "werdykt_na_materiale_archiwalnym"


def _evidence(
    parsed: ModelVerdict, by_id: dict[str, ReferenceSource], adjustments: list[str]
) -> list[EvidenceOut]:
    result = []
    for item in parsed.evidence:
        source = by_id.get(item.source_id)
        exact = verify_quote(item.quote, source.text) if source else None
        if source is None:
            adjustments.append(
                f"Dowód odwołuje się do źródła [{item.source_id}], którego nie było w danych; "
                "nie został uznany."
            )
        elif exact is None:
            adjustments.append(
                f"Cytat przypisany źródłu [{item.source_id}] nie występuje w nim dosłownie; "
                "nie został uznany za dowód."
            )
        result.append(
            EvidenceOut(
                source_id=item.source_id,
                quote=exact or item.quote,
                stance=item.stance,
                explanation=item.explanation,
                quote_verified=exact is not None,
                source_title=source.title if source else "",
                publisher=source.publisher if source else "",
                url=source.url if source else None,
                published_at=source.published_at if source else None,
                fetched_at=source.fetched_at if source else None,
                age_days=source.age_days if source else None,
                freshness_flags=list(source.freshness_flags) if source else [],
            )
        )
    return result


def _reviews(
    parsed: ModelVerdict, by_id: dict[str, ReferenceSource], adjustments: list[str]
) -> list[SourceReviewOut]:
    reviews: dict[str, SourceReviewOut] = {}
    for review in parsed.sources_reviewed:
        if review.source_id in by_id and review.source_id not in reviews:
            reviews[review.source_id] = SourceReviewOut(**review.model_dump())
    missing = [source_id for source_id in by_id if source_id not in reviews]
    for source_id in missing:
        reviews[source_id] = SourceReviewOut(
            source_id=source_id,
            relevant=False,
            why="Model nie ocenił tego źródła (wpis uzupełniony automatycznie).",
        )
    if missing:
        adjustments.append(f"Model pominął ocenę źródeł: {', '.join(missing)}.")
    return [reviews[source_id] for source_id in by_id]


def consistency_problems(parsed: ModelVerdict, sources: Sequence[ReferenceSource]) -> list[str]:
    """Niespójności odpowiedzi modelu, które `apply_checks` rozstrzygnęłoby obniżeniem.

    Służy do jednej rundy naprawczej (verdict.py): model dostaje opis problemu i
    szansę na poprawkę, zanim kod obniży werdykt. Lista jest pusta, gdy odpowiedź
    przejdzie kontrolę bez zmiany werdyktu.
    """
    by_id = {s.source_id: s for s in sources}
    problems: list[str] = []
    supports = refutes = 0
    for item in parsed.evidence:
        source = by_id.get(item.source_id)
        if source is None:
            problems.append(f"dowód wskazuje źródło [{item.source_id}], którego nie ma w danych")
        elif verify_quote(item.quote, source.text) is None:
            problems.append(
                f"cytat przypisany [{item.source_id}] nie występuje w nim dosłownie: "
                f"„{item.quote[:150]}”"
            )
        elif item.stance == "potwierdza":
            supports += 1
        else:
            refutes += 1
    if parsed.verdict == "prawda" and not supports:
        problems.append("werdykt „prawda”, ale żaden dosłowny cytat nie ma stanowiska „potwierdza”")
    if parsed.verdict == "falsz" and not refutes:
        problems.append("werdykt „falsz”, ale żaden dosłowny cytat nie ma stanowiska „zaprzecza”")
    if parsed.verdict == "prawda" and refutes:
        problems.append(
            "werdykt „prawda”, choć dowody zawierają fragment „zaprzecza” "
            "(nierozstrzygnięta sprzeczność albo źródło wyjaśnione, które nie powinno być "
            "dowodem „zaprzecza” – R10)"
        )
    problems.extend(_misapplied_freshness(parsed, by_id))
    return problems


_CURRENT_SOURCE_RE = re.compile(r"\baktualn|\bnieaktualn|\barchiwaln", re.IGNORECASE)


def _misapplied_freshness(parsed: ModelVerdict, by_id: dict[str, ReferenceSource]) -> list[str]:
    """„Brak danych”, bo rzekomo brak aktualnego źródła, choć istotne źródło jest aktualne.

    Aktualne = ma datę publikacji i mieści się w limicie (brak flagi archiwalnej).
    O aktualności rozstrzyga limit, nie rok danych w treści (R11).
    """
    if parsed.verdict != NO_DATA:
        return []
    reasons = " ".join([*parsed.missing_information, *parsed.reasoning_steps])
    if not _CURRENT_SOURCE_RE.search(reasons):
        return []
    current = [
        review.source_id
        for review in parsed.sources_reviewed
        if review.relevant
        and (source := by_id.get(review.source_id)) is not None
        and source.age_days is not None
        and source.age_days >= 0
        and not source.freshness_flags
    ]
    if not current:
        return []
    return [
        "werdykt „brak_wystarczajacych_danych” uzasadniony brakiem aktualnego źródła, choć "
        f"istotne źródła {', '.join(f'[{s}]' for s in current)} są aktualne (mieszczą się "
        "w limicie, nie mają atrybutu archival). Według R11 o aktualności rozstrzyga wyłącznie "
        "limit, a aktualne źródło rozstrzyga stan obecny także wtedy, gdy podaje dane za "
        "wcześniejszy okres – oceń twierdzenie ponownie na podstawie ich treści"
    ]


def apply_checks(
    *,
    claim_id: str,
    claim: str,
    parsed: ModelVerdict,
    sources: Sequence[ReferenceSource],
    model: str | None,
    prior_adjustments: Sequence[str] = (),
) -> ClaimVerdict:
    by_id = {s.source_id: s for s in sources}
    adjustments: list[str] = list(prior_adjustments)
    evidence = _evidence(parsed, by_id, adjustments)
    reviews = _reviews(parsed, by_id, adjustments)

    verified = [e for e in evidence if e.quote_verified]
    supports = [e for e in verified if e.stance == "potwierdza"]
    refutes = [e for e in verified if e.stance == "zaprzecza"]

    verdict = parsed.verdict
    confidence: Confidence = parsed.confidence
    conflicts = list(parsed.conflicts)
    missing_information = list(parsed.missing_information)
    downgrade_reason = None

    if verdict == "prawda" and not supports:
        downgrade_reason = "brak zweryfikowanego cytatu potwierdzającego twierdzenie"
    elif verdict == "falsz" and not refutes:
        downgrade_reason = "brak zweryfikowanego cytatu zaprzeczającego twierdzeniu"
    elif verdict == "prawda" and refutes:
        downgrade_reason = "źródła zawierają zweryfikowany fragment zaprzeczający twierdzeniu"
        if not conflicts:
            conflicts.append(
                "Źródła "
                + ", ".join(sorted({e.source_id for e in supports}))
                + " potwierdzają twierdzenie, a "
                + ", ".join(sorted({e.source_id for e in refutes}))
                + " mu zaprzeczają."
            )

    explanation = parsed.explanation
    if downgrade_reason:
        adjustments.append(
            f"Werdykt modelu „{VERDICT_LABELS_PL[verdict]}” obniżono do "
            f"„{VERDICT_LABELS_PL[NO_DATA]}”: {downgrade_reason}."
        )
        explanation = (
            f"Werdykt modelu „{VERDICT_LABELS_PL[verdict]}” nie przeszedł kontroli "
            f"({downgrade_reason}), dlatego twierdzenia nie można jednoznacznie rozstrzygnąć. "
            f"Uzasadnienie modelu: {parsed.explanation}"
        )
        missing_information.append(
            "Fragment źródła wzorcowego, który dosłownie i jednoznacznie rozstrzyga twierdzenie."
        )
        verdict, confidence = NO_DATA, "niska"

    if verdict == NO_DATA and not missing_information:
        missing_information.append(
            "Źródła nie zawierają informacji pozwalających jednoznacznie rozstrzygnąć twierdzenie."
        )
        adjustments.append("Uzupełniono pustą listę brakujących informacji.")

    decisive = supports if verdict == "prawda" else refutes if verdict == "falsz" else []
    if (
        decisive
        and confidence == "wysoka"
        and all(by_id[e.source_id].kind == "fact_check" for e in decisive)
    ):
        confidence = "srednia"
        adjustments.append(
            "Pewność obniżono do „srednia”: rozstrzygnięcie opiera się wyłącznie na wpisach "
            "fact-checkingowych, bez źródła dokumentowego."
        )

    freshness_flags: list[str] = []
    if decisive and all(is_archival(by_id[e.source_id]) for e in decisive):
        freshness_flags.append(FLAG_VERDICT_ON_ARCHIVAL)
        if confidence == "wysoka":
            confidence = "srednia"
            adjustments.append(
                "Pewność obniżono do „srednia”: rozstrzygnięcie opiera się wyłącznie na "
                "materiale archiwalnym (starszym niż limit aktualności)."
            )

    return ClaimVerdict(
        freshness_flags=freshness_flags,
        claim_id=claim_id,
        claim=claim,
        verdict=verdict,
        verdict_label=VERDICT_LABELS_PL[verdict],
        confidence=confidence,
        claim_interpretation=parsed.claim_interpretation,
        explanation=explanation,
        reasoning_steps=parsed.reasoning_steps,
        evidence=evidence,
        sources_reviewed=reviews,
        conflicts=conflicts,
        missing_information=missing_information,
        adjustments=adjustments,
        model_verdict=parsed.verdict,
        source_ids=list(by_id),
        model=model,
    )
