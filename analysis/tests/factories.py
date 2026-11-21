"""Fabryki obiektów testowych dla verdict/ (fikcyjne dane)."""

from prawdowid_analysis.schemas import Claim, Evidence, Passage
from prawdowid_analysis.verdict.sources import EvidenceItem


def passage(
    i: int = 1,
    source_type: str = "official_primary",
    publisher: str = "Urząd A",
    published_at: str | None = "2026-10-01",
) -> Passage:
    return Passage(
        chunk_id=f"doc_{i}_c0",
        doc_id=f"doc_{i}",
        title="T",
        publisher=publisher,
        url=f"https://example.org/{i}",
        published_at=published_at,
        fetched_at="2026-11-21T10:00:00Z",
        source_type=source_type,
        text="tekst",
        char_start=0,
        char_end=5,
        text_hash="sha256:x",
        rerank_score=0.5,
    )


def evidence(
    p: Passage, stance: str = "supports", verified: bool = True, claim_id: str = "clm_001"
) -> Evidence:
    return Evidence(
        evidence_id=f"ev_{p.doc_id}",
        claim_id=claim_id,
        chunk_id=p.chunk_id,
        quote="cytat",
        quote_verified=verified,
        stance=stance,
    )


def item(stance: str = "supports", **kw) -> EvidenceItem:
    p = passage(**kw)
    return EvidenceItem(evidence(p, stance), p)


def claim(type_: str = "numeric", check_worthy: bool = True) -> Claim:
    return Claim(claim_id="clm_001", text="...", type=type_, check_worthy=check_worthy)
