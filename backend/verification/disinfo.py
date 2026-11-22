"""Known EUvsDisinfo cases override the claim verdict.

A claim found in the database (and confirmed by the matching judge) is verified pro-Kremlin
disinformation, whatever the evidence-based verdict said: it becomes ``falsz`` labelled
"Zweryfikowana rosyjska dezinformacja", with the case as the first piece of evidence, and the
text verdict is recomputed with the verdict module's own rule (``aggregate``).
"""

from __future__ import annotations

from collections.abc import Sequence
from types import SimpleNamespace
from typing import Any

from knownDisinfo import DisinfoCheck, StatementCheck

from . import _analysis

LABEL = "Zweryfikowana rosyjska dezinformacja"
_EXPLANATION = (
    "Twierdzenie figuruje w bazie EUvsDisinfo jako udokumentowany przypadek prokremlowskiej "
    "dezinformacji: {title} ({url})."
)


def summary(check: DisinfoCheck) -> dict[str, Any]:
    """What the front gets under ``claims_verdict.data.known_disinfo``."""
    return {
        "status": check.status,
        "source": "EUvsDisinfo",
        "matches": [
            {
                "claim_id": f"T{hit.index}",
                "statement": hit.statement,
                "reason": hit.reason,
                **hit.match.model_dump(mode="json"),  # type: ignore[union-attr]
            }
            for hit in check.matches
        ],
        "warnings": list(check.warnings),
    }


def _evidence(hit: StatementCheck) -> dict[str, Any]:
    case = hit.match
    assert case is not None
    schemas = _analysis.verdict_schemas()
    return schemas.EvidenceOut(
        source_id="EUVD",
        quote=(case.summary or case.title)[:500],
        stance="zaprzecza",
        explanation="Przypadek z bazy EUvsDisinfo (prokremlowska dezinformacja).",
        quote_verified=True,
        source_title=case.title,
        publisher="EUvsDisinfo",
        url=case.url,
    ).model_dump(mode="json")


def _mark(claim: dict[str, Any], hit: StatementCheck) -> dict[str, Any]:
    case = hit.match
    assert case is not None
    marked = dict(claim)
    marked.update(
        verdict="falsz",
        verdict_label=LABEL,
        confidence="wysoka",
        explanation=_EXPLANATION.format(title=case.title, url=case.url)
        + (f" {hit.reason}" if hit.reason else ""),
        evidence=[_evidence(hit), *claim.get("evidence", [])],
        adjustments=[
            *claim.get("adjustments", []),
            f"Werdykt nadpisany: twierdzenie jest w bazie EUvsDisinfo ({case.url}).",
        ],
        known_disinformation=case.model_dump(mode="json") | {"reason": hit.reason},
    )
    return marked


def _recompute(verdict: dict[str, Any], marked: int) -> dict[str, Any]:
    aggregate = _analysis.verdict_aggregate().aggregate
    value, text = aggregate([SimpleNamespace(verdict=c.get("verdict")) for c in verdict["claims"]])
    verdict["verdict"] = value
    verdict["summary"] = (
        f"{text} W tym {marked} – {LABEL.lower()} (EUvsDisinfo)." if marked else text
    )
    return verdict


def _hit_for(claim: dict[str, Any], position: int, hits: dict[int, StatementCheck]) -> Any:
    claim_id = str(claim.get("claim_id") or "")
    if claim_id.startswith("T") and claim_id[1:].isdigit():
        return hits.get(int(claim_id[1:]))
    return hits.get(position)


def apply_known_disinfo(verdict: dict[str, Any], check: DisinfoCheck) -> dict[str, Any]:
    """Mark the claims found in the database; ``known_disinfo`` is added in every case."""
    result = dict(verdict)
    hits = {hit.index: hit for hit in check.matches}
    marked = 0
    if hits:
        claims = []
        for position, claim in enumerate(result.get("claims") or [], 1):
            hit = _hit_for(claim, position, hits)
            if hit is None and isinstance(claim, dict):
                text = " ".join(str(claim.get("claim", "")).split())
                hit = next(
                    (h for h in hits.values() if " ".join(h.statement.split()) == text), None
                )
            if hit is not None:
                claim, marked = _mark(claim, hit), marked + 1
            claims.append(claim)
        result["claims"] = claims
        if marked:
            result = _recompute(result, marked)
    result["known_disinfo"] = summary(check)
    return result


def verdict_from_matches(
    statements: Sequence[str], check: DisinfoCheck, error: BaseException
) -> dict[str, Any]:
    """The evidence-based verdict failed, but database hits are conclusive on their own."""
    schemas = _analysis.verdict_schemas()
    reason = f"Ocena na podstawie źródeł nie powiodła się ({type(error).__name__})."
    claims = [
        schemas.ClaimVerdict(
            claim_id=f"T{index}",
            claim=statement,
            verdict="blad_analizy",
            verdict_label=schemas.VERDICT_LABELS_PL["blad_analizy"],
            confidence="niska",
            explanation=reason,
            adjustments=[reason],
        ).model_dump(mode="json")
        for index, statement in enumerate(statements, 1)
    ]
    verdict = {
        "verdict": "blad_analizy",
        "summary": "",
        "claims": claims,
        "sources": [],
        "quarantined_sources": [],
        "input_sources": [],
        "warnings": [reason + " Werdykt opiera się wyłącznie na bazie EUvsDisinfo."],
    }
    return apply_known_disinfo(verdict, check)
