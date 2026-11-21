"""Reguły werdyktu: z twierdzenia, dowodów i pasaży do jednego z pięciu werdyktów albo statusu.

Czyste funkcje: bez sieci i bez LLM, testowalne na zbiorze ewaluacyjnym. Kolejność reguł:

1. Awaria techniczna wcześniejszego kroku (LLM, retriever, brak klucza) -> status `error`.
2. Opinia albo twierdzenie niesprawdzalne -> `not_verifiable`.
3. Dowód użyteczny = cytat zweryfikowany w źródle (`quote_verified`), stanowisko
   `supports`/`refutes` i znany pasaż. Brak użytecznych -> `insufficient_evidence`.
4. Źródła T1–T2 po obu stronach -> `insufficient_evidence` + `conflicting_sources`
   (pokazujemy rozbieżność, bez arbitralnej pewności).
5. ≥ 2 niezależne źródła T1–T2 potwierdzają (żadne T1–T2 nie obala) -> `confirmed`;
   ≥ 2 niezależne T1–T2 obalają (żadne T1–T2 nie potwierdza) -> `false`.
   Przeciwne źródło niższej rangi (T3) nie blokuje werdyktu, ale daje flagę
   `conflicting_sources` i obniża siłę.
6. W pozostałych przypadkach (np. 1 źródło T1–T2, same media) -> `insufficient_evidence`.

Siła z `strength.py`, flagi z `flags.py`. `misleading` wymaga sygnału „prawda, ale bez
kontekstu”, którego obecny kontrakt stanowiska (supports/refutes/neutral/insufficient)
nie niesie, więc reguły go jeszcze nie przyznają.
"""

from datetime import date

from ..schemas import Claim, Evidence, Handover, Passage, Strength, Verdict
from .flags import compute_flags, has_conflict, today_utc
from .sources import MIN_INDEPENDENT_STRONG, EvidenceItem, independent_sources
from .strength import compute_strength, strength_factors

DECISIVE_STANCES = ("supports", "refutes")


def is_usable(evidence: Evidence) -> bool:
    """Czy dowód może wspierać werdykt: zweryfikowany cytat i rozstrzygające stanowisko."""
    return evidence.quote_verified and evidence.stance in DECISIVE_STANCES


def usable_items(
    claim: Claim, evidence: list[Evidence], passages: list[Passage]
) -> list[EvidenceItem]:
    by_chunk = {p.chunk_id: p for p in passages}
    return [
        EvidenceItem(e, by_chunk[e.chunk_id])
        for e in evidence
        if e.claim_id == claim.claim_id and is_usable(e) and e.chunk_id in by_chunk
    ]


def error_status(claim_id: str | None, reason: str) -> Verdict:
    """Status techniczny `error`. `reason` trafia do `limitations` (bez danych wrażliwych)."""
    return Verdict(
        claim_id=claim_id,
        outcome_class="status",
        outcome="error",
        strength=None,
        explanation_pl=(
            "Nie udało się sprawdzić tego twierdzenia z powodu błędu technicznego. "
            "To nie jest ocena prawdziwości. Spróbuj ponownie później."
        ),
        limitations=[reason],
    )


def _verdict(claim: Claim, outcome: str, explanation: str, strength: Strength, **kw) -> Verdict:
    handover = kw.pop("handover", False)
    return Verdict(
        claim_id=claim.claim_id,
        outcome_class="verdict",
        outcome=outcome,
        strength=strength,
        explanation_pl=explanation,
        handover=Handover(recommended=handover),
        **kw,
    )


def _low(*factors: str) -> Strength:
    return Strength(level="low", factors=list(factors))


def aggregate(
    claim: Claim,
    evidence: list[Evidence],
    passages: list[Passage],
    *,
    error: str | None = None,
    now: date | None = None,
) -> Verdict:
    """Werdykt dla jednego twierdzenia.

    `passages`: pasaże, z których pochodzą dowody (źródło rangi, wydawcy i daty).
    `error`: ustawia potok, gdy wcześniejszy krok się nie powiódł; wtedy status, nie werdykt.
    `now`: data odniesienia dla `stale_source` (domyślnie dziś, UTC).
    """
    if error:
        return error_status(claim.claim_id, error)

    if claim.type == "opinion" or not claim.check_worthy:
        reason = "twierdzenie typu opinia" if claim.type == "opinion" else "niesprawdzalne"
        return _verdict(
            claim,
            "not_verifiable",
            "To twierdzenie jest opinią lub oceną, a nie faktem, który da się sprawdzić "
            "w źródłach.",
            _low(reason),
        )

    now = now or today_utc()
    items = usable_items(claim, evidence, passages)
    if not items:
        own = [e for e in evidence if e.claim_id == claim.claim_id]
        rejected = sum(1 for e in own if not e.quote_verified and e.stance in DECISIVE_STANCES)
        factors = ["0 dowodów z cytatem zweryfikowanym w źródle"]
        if rejected:
            factors.append(f"{rejected} dowodów odrzuconych: cytat nie występuje w źródle")
        return _verdict(
            claim,
            "insufficient_evidence",
            "W dostępnych źródłach nie znaleźliśmy fragmentu, który jednoznacznie potwierdza "
            "albo obala to twierdzenie.",
            _low(*factors),
            unresolved=["brak źródła, które rozstrzyga twierdzenie"],
            handover=True,
        )

    supports = [i for i in items if i.stance == "supports"]
    refutes = [i for i in items if i.stance == "refutes"]
    strong_support = independent_sources(supports, strong_only=True)
    strong_refute = independent_sources(refutes, strong_only=True)
    flags = compute_flags(claim, items, now)
    ids = [i.evidence.evidence_id for i in items]
    stale_note = (
        ["część źródeł może być nieaktualna dla tego typu twierdzenia"]
        if "stale_source" in flags
        else []
    )

    if strong_support and strong_refute:
        return _verdict(
            claim,
            "insufficient_evidence",
            "Wiarygodne źródła są ze sobą sprzeczne: część potwierdza, a część obala to "
            "twierdzenie. Pokazujemy obie strony zamiast rozstrzygać.",
            _low(
                f"{strong_support} niezależnych źródeł T1–T2 potwierdza",
                f"{strong_refute} niezależnych źródeł T1–T2 obala",
            ),
            evidence_ids=ids,
            flags=flags,
            unresolved=["sprzeczne źródła wysokiej rangi"],
            limitations=stale_note,
            handover=True,
        )

    for outcome, side, count, explanation in (
        (
            "confirmed",
            supports,
            strong_support,
            "Co najmniej dwa niezależne, wiarygodne źródła potwierdzają to twierdzenie.",
        ),
        (
            "false",
            refutes,
            strong_refute,
            "Co najmniej dwa niezależne, wiarygodne źródła przeczą temu twierdzeniu.",
        ),
    ):
        if count >= MIN_INDEPENDENT_STRONG:
            factors = strength_factors(claim, side, conflicting=has_conflict(items), now=now)
            return _verdict(
                claim,
                outcome,
                explanation,
                compute_strength(factors),
                evidence_ids=ids,
                flags=flags,
                limitations=stale_note,
            )

    # Są dowody, ale za mało niezależnych źródeł wysokiej rangi.
    side = supports if strong_support >= strong_refute and supports else refutes
    direction = "potwierdza to twierdzenie" if side is supports else "przeczy temu twierdzeniu"
    factors = strength_factors(claim, side, conflicting=has_conflict(items), now=now)
    return _verdict(
        claim,
        "insufficient_evidence",
        f"Znaleźliśmy źródło, które {direction}, ale to za mało: potrzebne są co najmniej "
        f"{MIN_INDEPENDENT_STRONG} niezależne źródła wysokiej rangi (urzędowe, statystyczne, "
        "naukowe, fact-checkingowe lub agencyjne).",
        compute_strength(factors),
        evidence_ids=ids,
        flags=flags,
        unresolved=[f"brak drugiego niezależnego źródła T1–T2, które {direction}"],
        limitations=stale_note,
        handover=True,
    )
