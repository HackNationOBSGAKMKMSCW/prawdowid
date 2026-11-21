from datetime import UTC, datetime

import pytest

from prawdowid_analysis.freshness import (
    FLAG_ARCHIVAL,
    FLAG_FUTURE_DATE,
    FLAG_NO_DATE,
    annotate,
    archival_warning,
    iso_timestamp,
    parse_date,
    recency_factor,
)
from tests.fakes import source

NOW = datetime(2026, 11, 21, 12, 30, tzinfo=UTC)


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


def test_annotate_fresh_archival_undated_and_future():
    fresh = annotate(source(published_at="2026-01-01"), NOW, 730)
    assert fresh.age_days == 324 and fresh.freshness_flags == []
    old = annotate(source(published_at="2015-01-05"), NOW, 730)
    assert FLAG_ARCHIVAL in old.freshness_flags and old.age_days > 730
    assert annotate(source(), NOW, 730).freshness_flags == [FLAG_NO_DATE]
    assert annotate(source(published_at="2027-01-01"), NOW, 730).freshness_flags == [
        FLAG_FUTURE_DATE
    ]


def test_annotate_is_idempotent_and_respects_limit():
    once = annotate(source(published_at="2025-01-01"), NOW, 300)
    twice = annotate(once, NOW, 300)
    assert twice.freshness_flags == once.freshness_flags == [FLAG_ARCHIVAL]
    assert annotate(once, NOW, 1000).freshness_flags == []


def test_recency_factor_prefers_newer():
    newer = annotate(source(published_at="2026-11-01"), NOW, 730)
    older = annotate(source(published_at="2025-06-01"), NOW, 730)
    archival = annotate(source(published_at="2010-01-01"), NOW, 730)
    undated = annotate(source(), NOW, 730)
    assert recency_factor(newer, 730) > recency_factor(older, 730) > 0
    assert recency_factor(older, 730) > recency_factor(archival, 730) > 0
    assert recency_factor(undated, 730) == 0
    at_limit = annotate(source(published_at="2024-11-21"), NOW, 730)
    assert recency_factor(at_limit, 730) == 0.5


def test_archival_warning_mentions_date_age_and_limit():
    old = annotate(source("UZ-stare", published_at="2015-01-05"), NOW, 730)
    warning = archival_warning(old, 730)
    assert "[UZ-stare]" in warning and "2015-01-05" in warning and "730 dni" in warning
