from datetime import date

import pytest
from factories import claim, item

from prawdowid_analysis.verdict.strength import (
    StrengthFactors,
    compute_strength,
    plural,
    strength_factors,
)

NOW = date(2026, 11, 21)


def factors(**kw) -> StrengthFactors:
    base = dict(
        independent_strong=2,
        has_t1=True,
        weak_sources=0,
        verified_quotes=2,
        stale=0,
        missing_date=0,
        conflicting=False,
    )
    return StrengthFactors(**{**base, **kw})


@pytest.mark.parametrize(
    "kw, level",
    [
        ({}, "high"),  # 2 niezależne, w tym T1, czysto
        ({"has_t1": False}, "medium"),  # 2 x T2
        ({"has_t1": False, "independent_strong": 3}, "high"),
        ({"stale": 1}, "medium"),
        ({"missing_date": 1}, "medium"),
        ({"conflicting": True}, "medium"),
        ({"independent_strong": 1}, "low"),
        ({"independent_strong": 0, "weak_sources": 5}, "low"),  # same media
    ],
)
def test_level_follows_explicit_factors(kw, level):
    assert factors(**kw).level() == level


def test_factors_are_listed_in_strength():
    s = compute_strength(factors(stale=1, weak_sources=1, conflicting=True))
    assert s.level == "medium"
    text = " | ".join(s.factors)
    assert "2 niezależne źródła T1–T2 (w tym T1)" in text
    assert "1 źródło nieaktualne" in text and "1 źródło niższej rangi" in text
    assert "T3+" in text and "przeciwnego" in text
    assert not any("%" in f for f in s.factors)  # bez procentów


@pytest.mark.parametrize(
    "n, form",
    [
        (0, "źródeł"),
        (1, "źródło"),
        (2, "źródła"),
        (4, "źródła"),
        (5, "źródeł"),
        (12, "źródeł"),
        (22, "źródła"),
        (25, "źródeł"),
    ],
)
def test_polish_plural(n, form):
    assert plural(n, "źródło", "źródła", "źródeł") == form


def test_strength_factors_from_evidence():
    side = [
        item(i=1, publisher="Urząd A"),
        item(i=2, publisher="Urząd A"),  # ten sam wydawca
        item(i=3, publisher="Agencja B", source_type="news_agency", published_at=None),
        item(i=4, publisher="Portal C", source_type="media"),
        item(i=5, publisher="GUS X", source_type="public_data", published_at="2024-01-01"),
    ]
    f = strength_factors(claim("numeric"), side, conflicting=False, now=NOW)
    assert f.independent_strong == 3 and f.has_t1
    assert f.weak_sources == 1 and f.verified_quotes == 5
    assert f.stale == 1 and f.missing_date == 1
    assert f.level() == "medium"
