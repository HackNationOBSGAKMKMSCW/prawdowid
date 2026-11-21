"""Kontrola deterministyczna odpowiedzi modelu i budowa wyniku `ClaimVerdict`."""

from collections.abc import Sequence

from .schemas import (
    VERDICT_LABELS_PL,
    ClaimVerdict,
    EvidenceOut,
    ModelVerdict,
    ReferenceSource,
    SourceReviewOut,
)


def apply_checks(
    *,
    claim_id: str,
    claim: str,
    parsed: ModelVerdict,
    sources: Sequence[ReferenceSource],
    model: str | None,
) -> ClaimVerdict:
    by_id = {s.source_id: s for s in sources}
    evidence = []
    for item in parsed.evidence:
        source = by_id.get(item.source_id)
        evidence.append(
            EvidenceOut(
                source_id=item.source_id,
                quote=item.quote,
                stance=item.stance,
                explanation=item.explanation,
                quote_verified=False,
                source_title=source.title if source else "",
                publisher=source.publisher if source else "",
                url=source.url if source else None,
                published_at=source.published_at if source else None,
            )
        )
    return ClaimVerdict(
        claim_id=claim_id,
        claim=claim,
        verdict=parsed.verdict,
        verdict_label=VERDICT_LABELS_PL[parsed.verdict],
        confidence=parsed.confidence,
        claim_interpretation=parsed.claim_interpretation,
        explanation=parsed.explanation,
        reasoning_steps=parsed.reasoning_steps,
        evidence=evidence,
        sources_reviewed=[SourceReviewOut(**r.model_dump()) for r in parsed.sources_reviewed],
        conflicts=parsed.conflicts,
        missing_information=parsed.missing_information,
        model_verdict=parsed.verdict,
        source_ids=list(by_id),
        model=model,
    )
