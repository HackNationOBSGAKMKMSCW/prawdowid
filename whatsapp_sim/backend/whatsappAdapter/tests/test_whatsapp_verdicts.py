import pytest
from whatsappAdapter.verdicts import OverallVerdict, Verdict, classify_rating, overall_verdict


@pytest.mark.parametrize(
    ("rating", "expected"),
    [
        ("Fałsz", Verdict.FALSE),
        ("Nieprawda", Verdict.FALSE),
        ("False", Verdict.FALSE),
        ("Not true", Verdict.FALSE),
        ("Pants on Fire!", Verdict.FALSE),
        ("Mostly False", Verdict.FALSE),
        ("Prawda", Verdict.TRUE),
        ("True", Verdict.TRUE),
        ("Mostly True", Verdict.TRUE),
        ("Częściowo fałsz", Verdict.MISLEADING),
        ("Częściowa prawda", Verdict.MISLEADING),
        ("Manipulacja", Verdict.MISLEADING),
        ("Half True", Verdict.MISLEADING),
        ("Missing context", Verdict.MISLEADING),
        ("Nieweryfikowalne", Verdict.UNVERIFIED),
        ("Unproven", Verdict.UNVERIFIED),
        ("", Verdict.UNVERIFIED),
        (None, Verdict.UNVERIFIED),
        ("Zobacz analizę", Verdict.UNVERIFIED),
    ],
)
def test_classify_rating(rating: str | None, expected: Verdict) -> None:
    assert classify_rating(rating) is expected


def test_overall_verdict() -> None:
    assert overall_verdict([]) is OverallVerdict.NO_DATA
    assert overall_verdict([Verdict.UNVERIFIED]) is OverallVerdict.UNVERIFIED
    assert overall_verdict([Verdict.FALSE, Verdict.FALSE]) is OverallVerdict.FALSE
    assert overall_verdict([Verdict.FALSE, Verdict.MISLEADING]) is OverallVerdict.FALSE
    assert (
        overall_verdict([Verdict.MISLEADING, Verdict.MISLEADING, Verdict.FALSE])
        is OverallVerdict.MISLEADING
    )
    assert overall_verdict([Verdict.TRUE, Verdict.UNVERIFIED]) is OverallVerdict.TRUE
    assert overall_verdict([Verdict.TRUE, Verdict.MISLEADING]) is OverallVerdict.MISLEADING
    assert overall_verdict([Verdict.TRUE, Verdict.FALSE]) is OverallVerdict.CONFLICTING
