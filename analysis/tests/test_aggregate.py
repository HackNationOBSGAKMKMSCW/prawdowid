import pytest

from prawdowid_analysis.aggregate import aggregate
from prawdowid_analysis.schemas import VERDICT_LABELS_PL, ClaimVerdict


def claim(verdict: str, n: int = 0) -> ClaimVerdict:
    return ClaimVerdict(
        claim_id=f"C{n}",
        claim="x",
        verdict=verdict,
        verdict_label=VERDICT_LABELS_PL[verdict],
        confidence="niska",
        explanation="x",
    )


@pytest.mark.parametrize(
    ("verdicts", "expected"),
    [
        ([], "nieweryfikowalny"),
        (["prawda", "prawda"], "prawdziwy"),
        (["falsz"], "falszywy"),
        (["prawda", "falsz"], "zawiera_falsz"),
        (["falsz", "brak_wystarczajacych_danych"], "zawiera_falsz"),
        (["prawda", "brak_wystarczajacych_danych"], "czesciowo_potwierdzony"),
        (
            ["brak_wystarczajacych_danych", "brak_wystarczajacych_danych"],
            "brak_wystarczajacych_danych",
        ),
        (["brak_wystarczajacych_danych", "blad_analizy"], "brak_wystarczajacych_danych"),
        (["blad_analizy"], "blad_analizy"),
    ],
)
def test_aggregate_rules(verdicts, expected):
    verdict, _ = aggregate([claim(v, i) for i, v in enumerate(verdicts)])
    assert verdict == expected


def test_summary_counts_and_polish_plural():
    _, summary = aggregate([claim("prawda", 1), claim("falsz", 2), claim("falsz", 3)])
    assert summary == "Sprawdzono 3 twierdzenia: 1 – prawda; 2 – fałsz."
    _, summary = aggregate([claim("prawda", i) for i in range(5)])
    assert summary.startswith("Sprawdzono 5 twierdzeń")
