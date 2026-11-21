from datetime import date

import pytest

from prawdowid_analysis.schemas import Claim, Evidence, Passage
from prawdowid_analysis.verdict.flags import compute_flags, is_stale, parse_date
from prawdowid_analysis.verdict.sources import (
    EvidenceItem,
    independent_sources,
    tier_of,
)

NOW = date(2026, 11, 21)


def passage(i=1, source_type="official_primary", publisher="Urząd A", published_at="2026-10-01"):
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


def item(stance="supports", **kw) -> EvidenceItem:
    p = passage(**kw)
    ev = Evidence(
        evidence_id=f"ev_{p.doc_id}",
        claim_id="clm_001",
        chunk_id=p.chunk_id,
        quote="cytat",
        quote_verified=True,
        stance=stance,
    )
    return EvidenceItem(ev, p)


def claim(type_="numeric"):
    return Claim(claim_id="clm_001", text="...", type=type_, check_worthy=True)


@pytest.mark.parametrize(
    "source_type, tier",
    [
        ("official_primary", 1),
        ("public_data", 1),
        ("research", 1),
        ("fact_check", 2),
        ("news_agency", 2),
        ("media", 3),
    ],
)
def test_tiers(source_type, tier):
    assert tier_of(passage(source_type=source_type)) == tier


def test_independence_counts_publishers_not_documents():
    items = [
        item(i=1, publisher="Urząd A"),
        item(i=2, publisher=" urząd  a "),  # ten sam wydawca, inny dokument
        item(i=3, publisher="Agencja B", source_type="news_agency"),
        item(i=4, publisher="Portal C", source_type="media"),
    ]
    assert independent_sources(items) == 3
    assert independent_sources(items, strong_only=True) == 2


def test_conflicting_sources_flag():
    assert compute_flags(claim(), [item("supports", i=1), item("refutes", i=2)], NOW) == [
        "conflicting_sources"
    ]
    assert compute_flags(claim(), [item("supports", i=1), item("supports", i=2)], NOW) == []


@pytest.mark.parametrize(
    "claim_type, published_at, stale",
    [
        ("numeric", "2025-11-20", True),  # 366 dni
        ("numeric", "2025-11-21", False),  # dokładnie 365 dni
        ("legal", "2025-06-01", False),
        ("legal", "2024-06-01", True),
        ("quote", "2010-01-01", False),  # cytat nie traci ważności
        ("numeric", None, False),  # brak daty: nie flagujemy (osobny czynnik siły)
    ],
)
def test_stale_source_by_claim_type(claim_type, published_at, stale):
    assert is_stale(passage(published_at=published_at), claim_type, NOW) is stale
    flags = compute_flags(claim(claim_type), [item(published_at=published_at)], NOW)
    assert ("stale_source" in flags) is stale


def test_parse_date_tolerates_datetime_and_garbage():
    assert parse_date("2026-10-03T12:00:00Z") == date(2026, 10, 3)
    assert parse_date("wczoraj") is None and parse_date(None) is None
