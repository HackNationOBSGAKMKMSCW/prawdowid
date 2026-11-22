import pytest

from scripts import eval_metrics as m

CLASSES = ("prawda", "falsz", "brak_wystarczajacych_danych")
BRAK = "brak_wystarczajacych_danych"


def row(expected, verdict, *, accept=(), scenario="A", forbidden=False, leak=False, evidence=()):
    return {
        "id": f"{expected}-{verdict}",
        "claim": "twierdzenie",
        "expected_main": expected,
        "expected": sorted({expected, *accept}),
        "verdict": verdict,
        "scenario": scenario,
        "forbidden": forbidden,
        "leak": leak,
        "evidence": list(evidence),
    }


def test_macro_f1_matches_hand_computed_value():
    rows = [
        row("prawda", "prawda"),
        row("prawda", "prawda"),
        row("prawda", "falsz"),
        row("falsz", "falsz"),
        row(BRAK, BRAK),
        row(BRAK, "prawda"),
    ]
    result = m.macro_f1(rows, CLASSES)
    # prawda: P=2/3 R=2/3 F1=0.6667; falsz: P=1/2 R=1 F1=0.6667; brak: P=1 R=1/2 F1=0.6667
    assert result["value"] == pytest.approx(0.6667, abs=1e-4)
    assert result["per_class"]["falsz"]["precision"] == 0.5
    assert result["per_class"][BRAK]["support"] == 2


def test_accepted_alternative_counts_as_hit():
    rows = [row(BRAK, "falsz", accept=["falsz"])]
    assert m.macro_f1(rows, CLASSES)["value"] == 1.0
    assert m.per_scenario(rows) == {"A": {"ok": 1, "total": 1}}


def test_macro_f1_ignores_classes_without_support():
    rows = [row("prawda", "prawda"), row("falsz", "falsz")]
    assert m.macro_f1(rows, CLASSES)["value"] == 1.0


def test_abstention_and_injection_shares():
    rows = [
        row(BRAK, BRAK, scenario="D"),
        row(BRAK, "falsz", scenario="D"),
        row("falsz", "falsz", scenario="E"),
        row("falsz", "prawda", scenario="E", forbidden=True),
        row("prawda", "prawda", scenario="E", leak=True),
    ]
    assert m.abstention(rows) == {"value": 0.5, "hits": 1, "total": 2}
    assert m.injection_robustness(rows)["hits"] == 1
    assert m.injection_robustness(rows)["total"] == 3


def test_citation_coverage_counts_only_decisive_verdicts_with_verified_quote():
    rows = [
        row("prawda", "prawda", evidence=[{"quote_verified": True}]),
        row("falsz", "falsz", evidence=[{"quote_verified": False}]),
        row(BRAK, BRAK),
    ]
    assert m.citation_coverage(rows) == {"value": 0.5, "hits": 1, "total": 2}
    assert m.unverified_quotes(rows) == {"value": 0.5, "hits": 1, "total": 2}


def test_latency_summary():
    assert m.latency([3.0, 1.0, 2.0, 10.0])["median_s"] == 2.5
    assert m.latency([])["median_s"] is None


def test_citation_sample_round_trip(tmp_path):
    ev = {"quote_verified": True, "quote": "cytat", "stance": "potwierdza", "publisher": "GUS"}
    rows = [row("prawda", "prawda", evidence=[ev]) for _ in range(3)]
    sample = m.sample_citations(rows, 2, seed=1)
    assert len(sample) == 2
    path = tmp_path / "cytaty.csv"
    m.write_citation_sample(path, sample)
    assert m.citation_correctness(path) == {"value": None, "hits": 0, "total": 0, "unrated": 2}
    sample[0]["ocena"], sample[1]["ocena"] = "TAK", " nie "
    m.write_citation_sample(path, sample)
    assert m.citation_correctness(path) == {"value": 0.5, "hits": 1, "total": 2, "unrated": 0}
