from datetime import date

import pytest
from factories import claim, evidence, passage

from prawdowid_analysis.verdict.rules import aggregate, error_status

VERDICTS = {"confirmed", "false", "misleading", "insufficient_evidence", "not_verifiable"}
NOW = date(2026, 11, 21)

# Źródła: dwa niezależne T1, jedno T2, dwa dokumenty jednego wydawcy, media (T3).
GOV = passage(1, "official_primary", "Urząd A")
STAT = passage(2, "public_data", "Urząd Statystyczny B")
FACT = passage(3, "fact_check", "Serwis C")
GOV_COPY = passage(4, "official_primary", "Urząd A")  # ten sam wydawca co GOV
MEDIA = passage(5, "media", "Portal D")
MEDIA2 = passage(6, "media", "Portal E")
OLD_STAT = passage(7, "public_data", "Urząd Statystyczny F", published_at="2023-01-01")
ALL = [GOV, STAT, FACT, GOV_COPY, MEDIA, MEDIA2, OLD_STAT]


def run(evs, c=None, passages=ALL, **kw):
    return aggregate(c or claim(), evs, passages, now=NOW, **kw)


# ── statusy i brak dowodów ───────────────────────────────────────────────────


def test_failure_is_error_status_not_verdict():
    v = run([evidence(GOV), evidence(STAT)], error="LLMError: timeout")
    assert (v.outcome_class, v.outcome) == ("status", "error")
    assert v.outcome not in VERDICTS
    assert v.strength is None and v.evidence_ids == []
    assert v.limitations == ["LLMError: timeout"]


def test_error_status_without_claim():
    v = error_status(None, "retriever niedostępny")
    assert v.claim_id is None and v.outcome == "error"


@pytest.mark.parametrize("c", [claim("opinion"), claim(check_worthy=False)])
def test_opinion_is_not_verifiable_even_with_evidence(c):
    v = run([evidence(GOV), evidence(STAT)], c)
    assert (v.outcome_class, v.outcome) == ("verdict", "not_verifiable")


def test_no_evidence_is_insufficient_with_handover():
    v = run([])
    assert v.outcome == "insufficient_evidence" and v.evidence_ids == []
    assert v.strength.level == "low"
    assert v.handover.recommended and not v.handover.created


def test_neutral_and_insufficient_stances_do_not_count():
    v = run([evidence(GOV, "neutral"), evidence(STAT, "insufficient")])
    assert v.outcome == "insufficient_evidence" and v.evidence_ids == []


def test_unverified_quotes_cannot_support_verdict():
    v = run([evidence(GOV, verified=False), evidence(STAT, verified=False)])
    assert v.outcome == "insufficient_evidence" and v.evidence_ids == []
    assert any("odrzuconych" in f for f in v.strength.factors)


def test_unverified_quote_does_not_complete_the_threshold():
    v = run([evidence(GOV), evidence(STAT, verified=False)])
    assert v.outcome == "insufficient_evidence"
    assert v.evidence_ids == ["ev_doc_1"]


def test_evidence_without_passage_or_of_other_claim_is_ignored():
    v = run([evidence(GOV), evidence(STAT, claim_id="clm_999")])
    assert v.outcome == "insufficient_evidence"
    v = run([evidence(GOV), evidence(STAT)], passages=[GOV])
    assert v.outcome == "insufficient_evidence"


# ── próg 2 niezależnych T1–T2 ───────────────────────────────────────────────


def test_two_independent_strong_sources_confirm():
    v = run([evidence(GOV), evidence(FACT)])
    assert (v.outcome_class, v.outcome) == ("verdict", "confirmed")
    assert v.strength.level == "high"  # 2 niezależne, w tym T1, bez zastrzeżeń
    assert v.flags == [] and not v.handover.recommended


def test_two_independent_strong_sources_refute():
    v = run([evidence(GOV, "refutes"), evidence(STAT, "refutes"), evidence(FACT, "refutes")])
    assert v.outcome == "false" and v.strength.level == "high"
    assert len(v.evidence_ids) == 3


def test_single_strong_source_is_not_enough():
    v = run([evidence(GOV)])
    assert v.outcome == "insufficient_evidence"
    assert v.strength.level == "low" and v.handover.recommended
    assert "potwierdza to twierdzenie" in v.explanation_pl


def test_same_publisher_is_not_independent():
    v = run([evidence(GOV), evidence(GOV_COPY)])
    assert v.outcome == "insufficient_evidence"


def test_media_only_never_gives_verdict():
    v = run([evidence(MEDIA), evidence(MEDIA2)])
    assert v.outcome == "insufficient_evidence"
    v = run([evidence(GOV), evidence(MEDIA), evidence(MEDIA2)])
    assert v.outcome == "insufficient_evidence"  # media nie dopełniają progu


# ── sprzeczności, aktualność, siła ───────────────────────────────────────────


def test_strong_sources_on_both_sides_abstain():
    v = run([evidence(GOV), evidence(STAT), evidence(FACT, "refutes")])
    assert v.outcome == "insufficient_evidence"
    assert v.flags == ["conflicting_sources"] and v.handover.recommended
    assert set(v.evidence_ids) == {"ev_doc_1", "ev_doc_2", "ev_doc_3"}  # obie strony


def test_weak_opposing_source_flags_but_does_not_block():
    v = run([evidence(GOV), evidence(FACT), evidence(MEDIA, "refutes")])
    assert v.outcome == "confirmed"
    assert v.flags == ["conflicting_sources"]
    assert v.strength.level == "medium"


def test_stale_source_flag_and_lower_strength():
    v = run([evidence(GOV, "refutes"), evidence(OLD_STAT, "refutes")], claim("numeric"))
    assert v.outcome == "false"
    assert v.flags == ["stale_source"] and v.strength.level == "medium"
    assert v.limitations


def test_stale_does_not_apply_to_quotes():
    v = run([evidence(GOV), evidence(OLD_STAT)], claim("quote"))
    assert v.flags == [] and v.strength.level == "high"


def test_two_t2_sources_give_medium_strength():
    fact2 = passage(8, "news_agency", "Agencja G")
    v = run([evidence(FACT), evidence(fact2)], passages=[FACT, fact2])
    assert v.outcome == "confirmed" and v.strength.level == "medium"


def test_strength_never_contains_model_percentages():
    v = run([evidence(GOV), evidence(FACT)])
    assert all("%" not in f for f in v.strength.factors)
