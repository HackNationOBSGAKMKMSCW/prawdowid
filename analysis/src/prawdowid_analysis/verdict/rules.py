"""Reguły werdyktu: z twierdzenia i dowodów do jednego z pięciu werdyktów albo statusu.

Czyste funkcje: bez sieci i bez LLM, testowalne na zbiorze ewaluacyjnym.

SZKIELET (etap 0:45–2:00). Działa już:
- awaria techniczna (LLM, retriever, brak klucza) -> status `error`, nigdy werdykt,
- opinia albo twierdzenie niesprawdzalne -> `not_verifiable`,
- brak dowodu z potwierdzonym cytatem i stanowiskiem -> `insufficient_evidence`,
- dowód z `quote_verified = false` nie wspiera werdyktu.
Do zrobienia w pełnej wersji (3:30–5:30): min. 2 niezależne źródła T1–T2 dla
`confirmed`/`false`, `misleading`, siła z `strength.py`, flagi z `flags.py`.
"""

from ..schemas import Claim, Evidence, Handover, Strength, Verdict

DECISIVE_STANCES = ("supports", "refutes")


def usable_evidence(evidence: list[Evidence]) -> list[Evidence]:
    """Dowody, które mogą wspierać werdykt: zweryfikowany cytat i rozstrzygające stanowisko."""
    return [e for e in evidence if e.quote_verified and e.stance in DECISIVE_STANCES]


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


def _verdict(
    claim: Claim,
    outcome: str,
    explanation: str,
    factors: list[str],
    *,
    evidence_ids: list[str] | None = None,
    flags: list[str] | None = None,
    unresolved: list[str] | None = None,
    limitations: list[str] | None = None,
    handover: bool = False,
) -> Verdict:
    return Verdict(
        claim_id=claim.claim_id,
        outcome_class="verdict",
        outcome=outcome,
        # Szkielet: zawsze `low`. Poziom z jawnych czynników policzy strength.py.
        strength=Strength(level="low", factors=factors),
        explanation_pl=explanation,
        evidence_ids=evidence_ids or [],
        flags=flags or [],
        unresolved=unresolved or [],
        limitations=limitations or [],
        handover=Handover(recommended=handover),
    )


def aggregate(claim: Claim, evidence: list[Evidence], *, error: str | None = None) -> Verdict:
    """Werdykt dla jednego twierdzenia.

    `error` ustawia potok, gdy wcześniejszy krok (retrieve, stance) się nie powiódł:
    wtedy zwracamy status, a nie werdykt oparty na niepełnych danych.
    """
    if error:
        return error_status(claim.claim_id, error)

    if claim.type == "opinion" or not claim.check_worthy:
        return _verdict(
            claim,
            "not_verifiable",
            "To twierdzenie jest opinią lub oceną, a nie faktem, który da się sprawdzić "
            "w źródłach.",
            ["twierdzenie typu opinia" if claim.type == "opinion" else "niesprawdzalne"],
        )

    own = [e for e in evidence if e.claim_id == claim.claim_id]
    usable = usable_evidence(own)
    if not usable:
        rejected = sum(1 for e in own if not e.quote_verified and e.stance in DECISIVE_STANCES)
        factors = ["0 dowodów z potwierdzonym cytatem"]
        if rejected:
            factors.append(f"{rejected} dowodów odrzuconych: cytat nie występuje w źródle")
        return _verdict(
            claim,
            "insufficient_evidence",
            "W dostępnych źródłach nie znaleźliśmy fragmentu, który jednoznacznie potwierdza "
            "albo obala to twierdzenie.",
            factors,
            unresolved=["brak źródła, które rozstrzyga twierdzenie"],
            handover=True,
        )

    supports = [e for e in usable if e.stance == "supports"]
    refutes = [e for e in usable if e.stance == "refutes"]
    ids = [e.evidence_id for e in usable]
    factors = [f"{len(supports)} cytatów potwierdzających", f"{len(refutes)} cytatów obalających"]

    if supports and refutes:
        return _verdict(
            claim,
            "insufficient_evidence",
            "Źródła są ze sobą sprzeczne: część potwierdza, a część obala to twierdzenie.",
            factors,
            evidence_ids=ids,
            flags=["conflicting_sources"],
            unresolved=["sprzeczne źródła"],
            handover=True,
        )
    if supports:
        return _verdict(
            claim,
            "confirmed",
            "Źródła zawierają fragment, który potwierdza to twierdzenie.",
            factors,
            evidence_ids=ids,
            limitations=["szkielet reguł: nie sprawdzono jeszcze niezależności i rangi źródeł"],
        )
    return _verdict(
        claim,
        "false",
        "Źródła zawierają fragment, który przeczy temu twierdzeniu.",
        factors,
        evidence_ids=ids,
        limitations=["szkielet reguł: nie sprawdzono jeszcze niezależności i rangi źródeł"],
    )
