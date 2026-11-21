import pytest

from prawdowid_analysis.schemas import Claim, Evidence
from prawdowid_analysis.verdict.rules import aggregate, error_status

VERDICTS = {"confirmed", "false", "misleading", "insufficient_evidence", "not_verifiable"}


def _claim(type_="legal", check_worthy=True) -> Claim:
    return Claim(claim_id="clm_001", text="...", type=type_, check_worthy=check_worthy)


def _ev(i: int, stance: str, verified: bool = True, claim_id: str = "clm_001") -> Evidence:
    return Evidence(
        evidence_id=f"ev_{i:03d}",
        claim_id=claim_id,
        chunk_id=f"doc_00{i}_c0",
        quote="cytat",
        quote_verified=verified,
        stance=stance,
    )


def test_no_evidence_is_insufficient():
    v = aggregate(_claim(), [])
    assert (v.outcome_class, v.outcome) == ("verdict", "insufficient_evidence")
    assert v.evidence_ids == []
    assert v.handover.recommended and not v.handover.created


def test_only_neutral_or_insufficient_stances_is_insufficient():
    v = aggregate(_claim(), [_ev(1, "neutral"), _ev(2, "insufficient")])
    assert v.outcome == "insufficient_evidence"


def test_unverified_quote_cannot_support_verdict():
    v = aggregate(_claim(), [_ev(1, "supports", verified=False)])
    assert v.outcome == "insufficient_evidence"
    assert v.evidence_ids == []
    assert any("odrzuconych" in f for f in v.strength.factors)


def test_evidence_of_other_claim_is_ignored():
    v = aggregate(_claim(), [_ev(1, "supports", claim_id="clm_999")])
    assert v.outcome == "insufficient_evidence"


@pytest.mark.parametrize("claim", [_claim("opinion"), _claim(check_worthy=False)])
def test_opinion_is_not_verifiable_even_with_evidence(claim):
    v = aggregate(claim, [_ev(1, "supports")])
    assert (v.outcome_class, v.outcome) == ("verdict", "not_verifiable")


def test_failure_is_error_status_not_verdict():
    v = aggregate(_claim(), [_ev(1, "supports")], error="LLMError: timeout")
    assert (v.outcome_class, v.outcome) == ("status", "error")
    assert v.outcome not in VERDICTS
    assert v.strength is None and v.evidence_ids == []
    assert v.limitations == ["LLMError: timeout"]


def test_error_status_without_claim():
    v = error_status(None, "retriever niedostępny")
    assert v.claim_id is None and v.outcome == "error"


def test_skeleton_supports_and_refutes():
    assert aggregate(_claim(), [_ev(1, "supports")]).outcome == "confirmed"
    v = aggregate(_claim(), [_ev(1, "refutes"), _ev(2, "neutral")])
    assert v.outcome == "false"
    assert v.evidence_ids == ["ev_001"]


def test_conflicting_evidence_abstains_with_flag():
    v = aggregate(_claim(), [_ev(1, "supports"), _ev(2, "refutes")])
    assert v.outcome == "insufficient_evidence"
    assert v.flags == ["conflicting_sources"]
