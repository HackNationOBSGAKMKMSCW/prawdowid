from datetime import UTC, date, datetime

import pytest

from prawdowid_analysis.freshness import (
    BASIS_EVENT_DATE,
    BASIS_NO_DATE,
    BASIS_PRESENT,
    FLAG_ARCHIVAL,
    FLAG_FUTURE_DATE,
    FLAG_NO_DATE,
    annotate,
    archival_warning,
    claim_independent,
    event_reference,
    iso_timestamp,
    parse_date,
    recency_factor,
)
from tests.fakes import source

NOW = datetime(2026, 11, 21, 12, 30, tzinfo=UTC)
TODAY = NOW.date()


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("2024-05-01", "2024-05-01"),
        ("2021-03-05T10:00:00Z", "2021-03-05"),
        ("", None),
        ("wczoraj", None),
        (None, None),
    ],
)
def test_parse_date(value, expected):
    parsed = parse_date(value)
    assert (parsed.isoformat() if parsed else None) == expected


def test_iso_timestamp_is_utc_seconds():
    assert iso_timestamp(NOW.replace(microsecond=123)) == "2026-11-21T12:30:00Z"


@pytest.mark.parametrize(
    ("claim", "expected_date", "basis"),
    [
        ("W wyborach w 2014 roku burmistrzem został Jan Nowacki.", "2014-12-31", BASIS_EVENT_DATE),
        ("Polska przystąpiła do UE 1 maja 2004 roku.", "2004-05-01", BASIS_EVENT_DATE),
        ("W kwietniu 2026 roku wybrano Annę Lis.", "2026-04-30", BASIS_EVENT_DATE),
        (
            "Ustawa weszła w życie 2019-01-01, a zmieniono ją 01.03.2021.",
            "2021-03-01",
            BASIS_EVENT_DATE,
        ),
        ("Traktat podpisano w 2003 r., a wszedł w życie w 2004 r.", "2004-12-31", BASIS_EVENT_DATE),
        ("Obecnie burmistrzem jest Anna Lis.", TODAY.isoformat(), BASIS_PRESENT),
        ("Od 2014 roku do dziś rządzi Jan Nowacki.", TODAY.isoformat(), BASIS_PRESENT),
        ("Rysy mają 2499 m n.p.m.", TODAY.isoformat(), BASIS_NO_DATE),
        ("Śnieżka ma 1603 m wysokości.", TODAY.isoformat(), BASIS_NO_DATE),
        ("Firma zarobiła 2010 zł.", TODAY.isoformat(), BASIS_NO_DATE),
        ("W 2030 roku Polska przyjmie euro.", TODAY.isoformat(), BASIS_EVENT_DATE),
    ],
)
def test_event_reference(claim, expected_date, basis):
    reference = event_reference(claim, TODAY)
    assert reference.date.isoformat() == expected_date
    assert reference.basis == basis


def test_age_is_relative_to_event_not_to_analysis():
    report_2015 = source(published_at="2015-01-05")
    event_2014 = date(2014, 12, 31)
    annotated = annotate(report_2015, event_2014, TODAY, 730)
    assert annotated.age_days == -5, "relacja opublikowana 5 dni po zdarzeniu"
    assert annotated.freshness_flags == []
    present = annotate(report_2015, TODAY, TODAY, 730)
    assert FLAG_ARCHIVAL in present.freshness_flags, "dla stanu obecnego to archiwum"


def test_source_published_long_before_event_is_archival():
    old = annotate(source(published_at="2010-01-01"), date(2014, 12, 31), TODAY, 730)
    assert old.freshness_flags == [FLAG_ARCHIVAL] and old.age_days > 730


def test_undated_and_future_sources():
    assert annotate(source(), TODAY, TODAY, 730).freshness_flags == [FLAG_NO_DATE]
    future = annotate(source(published_at="2027-01-01"), TODAY, TODAY, 730)
    assert future.freshness_flags == [FLAG_FUTURE_DATE]


def test_annotate_is_idempotent_and_claim_independent_view():
    once = annotate(source(published_at="2020-01-01"), TODAY, TODAY, 300)
    assert (
        annotate(once, TODAY, TODAY, 300).freshness_flags == once.freshness_flags == [FLAG_ARCHIVAL]
    )
    neutral = claim_independent(once)
    assert neutral.age_days is None and neutral.freshness_flags == []


def test_recency_factor_prefers_sources_close_to_event():
    event = date(2014, 12, 31)
    after = annotate(source(published_at="2015-01-05"), event, TODAY, 730)
    before = annotate(source(published_at="2014-01-01"), event, TODAY, 730)
    long_before = annotate(source(published_at="2005-01-01"), event, TODAY, 730)
    undated = annotate(source(), event, TODAY, 730)
    assert recency_factor(after, 730) == 1.0
    assert 1.0 > recency_factor(before, 730) > recency_factor(long_before, 730) > 0
    assert recency_factor(undated, 730) == 0


def test_archival_warning_names_reference_date_and_claim():
    reference = event_reference("Obecnie burmistrzem jest Jan Nowacki.", TODAY)
    old = annotate(source("UZ-stare", published_at="2015-01-05"), reference.date, TODAY, 730)
    warning = archival_warning(old, reference, 730, "T1")
    assert warning.startswith("T1: źródło [UZ-stare]")
    assert "2015-01-05" in warning and "stanie obecnym" in warning and "730 dni" in warning
