from prawdowid_analysis.checks import apply_checks
from prawdowid_analysis.schemas import ModelVerdict
from tests.fakes import model_answer, source

CLAIM = "Polska weszła do UE 1 maja 2004 roku."
QUOTE = "Polska przystąpiła do Unii Europejskiej 1 maja 2004 roku"


def check(answer, sources=None, claim=CLAIM):
    return apply_checks(
        claim_id="C1",
        claim=claim,
        parsed=ModelVerdict.model_validate(answer),
        sources=sources or [source()],
        model="atrapa",
    )


def evidence(source_id="KOR-1", quote=QUOTE, stance="potwierdza"):
    return {"source_id": source_id, "quote": quote, "stance": stance, "explanation": "x"}


def review(source_id):
    return {"source_id": source_id, "relevant": True, "why": "x"}


def test_verified_true_verdict_is_kept():
    result = check(model_answer())
    assert result.verdict == "prawda"
    assert result.confidence == "wysoka"
    assert result.evidence[0].quote_verified
    assert result.adjustments == []


def test_true_without_verified_quote_is_downgraded():
    result = check(model_answer(evidence=[evidence(quote="Polska weszła do UE w 2004 roku")]))
    assert result.verdict == "brak_wystarczajacych_danych"
    assert result.model_verdict == "prawda"
    assert result.confidence == "niska"
    assert not result.evidence[0].quote_verified
    assert any("dosłownie" in a for a in result.adjustments)
    assert any("obniżono" in a for a in result.adjustments)
    assert result.missing_information
    assert result.explanation.startswith("Werdykt modelu „Prawda” nie przeszedł kontroli")


def test_false_requires_verified_refuting_quote():
    result = check(model_answer(verdict="falsz", evidence=[evidence(stance="potwierdza")]))
    assert result.verdict == "brak_wystarczajacych_danych"


def test_false_with_verified_refuting_quote_is_kept():
    answer = model_answer(verdict="falsz", evidence=[evidence(stance="zaprzecza")])
    result = check(answer, claim="Polska weszła do UE w 2007 roku.")
    assert result.verdict == "falsz"
    assert result.adjustments == []


def test_evidence_from_unknown_source_is_not_accepted():
    result = check(model_answer(evidence=[evidence(source_id="WYMYSLONE")]))
    assert result.verdict == "brak_wystarczajacych_danych"
    assert any("WYMYSLONE" in a for a in result.adjustments)


def test_true_with_verified_contradiction_is_conflict():
    other = "Polska przystąpiła do Unii Europejskiej w 2007 roku"
    sources = [source(), source("KOR-2", text=f"{other}.")]
    answer = model_answer(
        evidence=[evidence(), evidence("KOR-2", other, "zaprzecza")],
        sources_reviewed=[review("KOR-1"), review("KOR-2")],
    )
    result = check(answer, sources)
    assert result.verdict == "brak_wystarczajacych_danych"
    assert result.conflicts and "KOR-2" in result.conflicts[0]


def test_no_data_always_lists_missing_information():
    answer = model_answer(
        verdict="brak_wystarczajacych_danych", evidence=[], missing_information=[]
    )
    result = check(answer)
    assert result.verdict == "brak_wystarczajacych_danych"
    assert result.missing_information
    assert result.adjustments


def test_fact_check_only_decision_caps_confidence():
    fc = source(
        "FC-1",
        kind="fact_check",
        text="Sprawdzane twierdzenie: Polska nie jest w UE\nOcena fact-checkera: Fałsz",
        rating="Fałsz",
    )
    answer = model_answer(
        evidence=[evidence("FC-1", "Ocena fact-checkera: Fałsz")],
        sources_reviewed=[review("FC-1")],
    )
    result = check(answer, [fc])
    assert result.verdict == "prawda"
    assert result.confidence == "srednia"


def test_unreviewed_sources_are_filled_in_and_unknown_dropped():
    sources = [source(), source("KOR-2", text="Inny tekst o czymś innym.")]
    answer = model_answer(sources_reviewed=[review("KOR-1"), review("NIEZNANE")])
    result = check(answer, sources)
    assert [r.source_id for r in result.sources_reviewed] == ["KOR-1", "KOR-2"]
    assert result.sources_reviewed[1].relevant is False
    assert any("KOR-2" in a for a in result.adjustments)


def test_consistency_problems_empty_for_coherent_answer():
    from prawdowid_analysis.checks import consistency_problems

    assert consistency_problems(ModelVerdict.model_validate(model_answer()), [source()]) == []
    no_data = model_answer(
        verdict="brak_wystarczajacych_danych", evidence=[], missing_information=[]
    )
    assert consistency_problems(ModelVerdict.model_validate(no_data), [source()]) == []


def test_consistency_problems_detect_verdict_evidence_mismatch():
    from prawdowid_analysis.checks import consistency_problems

    answer = model_answer(verdict="falsz", evidence=[evidence(stance="potwierdza")])
    problems = consistency_problems(ModelVerdict.model_validate(answer), [source()])
    assert problems == ["werdykt „falsz”, ale żaden dosłowny cytat nie ma stanowiska „zaprzecza”"]


def test_consistency_problems_detect_bad_quotes_and_unknown_sources():
    from prawdowid_analysis.checks import consistency_problems

    answer = model_answer(
        evidence=[evidence(quote="Polska weszła do UE w 2004"), evidence(source_id="X")]
    )
    problems = consistency_problems(ModelVerdict.model_validate(answer), [source()])
    assert any("nie występuje w nim dosłownie" in p for p in problems)
    assert any("[X]" in p for p in problems)
    assert any("werdykt „prawda”" in p for p in problems)


def test_verdict_resting_only_on_archival_material_is_flagged_and_capped():
    archival = source(
        published_at="2015-01-05", age_days=4338, freshness_flags=["material_archiwalny"]
    )
    result = check(model_answer(), [archival])
    assert result.verdict == "prawda", "fakt historyczny może pochodzić z archiwum"
    assert result.confidence == "srednia"
    assert result.freshness_flags == ["werdykt_na_materiale_archiwalnym"]
    assert any("materiale archiwalnym" in a for a in result.adjustments)
    assert result.evidence[0].age_days == 4338
    assert result.evidence[0].freshness_flags == ["material_archiwalny"]


def test_fresh_evidence_keeps_confidence_and_has_no_flag():
    fresh = source(published_at="2026-10-01", age_days=51, fetched_at="2026-11-21T12:00:00Z")
    result = check(model_answer(), [fresh])
    assert result.confidence == "wysoka" and result.freshness_flags == []
    assert result.evidence[0].fetched_at == "2026-11-21T12:00:00Z"
