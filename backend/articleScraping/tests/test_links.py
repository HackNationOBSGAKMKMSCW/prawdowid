from datetime import UTC, datetime

from apiReading.models import Category, Item, ReadingRequest, ReadingResult
from articleScraping.links import FactCheckLinkSource, TextLinkSource, extract_links
from textAnalysis.container import AnalysisDataContainer


def _reading_result() -> ReadingResult:
    return ReadingResult(
        request=ReadingRequest(query="claim", categories=[Category.FACT_CHECK]),
        results=[],
        items=[
            Item(
                id="claim-1",
                source="google_fact_check",
                payload={
                    "claimReview": [
                        {"url": "https://fact.example/review/1"},
                        {"url": "https://fact.example/review/2"},
                    ]
                },
            ),
            Item(id="claim-2", source="google_fact_check", payload={"claimReview": None}),
        ],
        categories_without_source=[],
        fetched_at=datetime.now(UTC),
        duration_ms=0,
    )


def test_text_source_strips_punctuation_and_bounds_matches() -> None:
    analysis = AnalysisDataContainer(
        original_text="See https://example.com/a_(b)., then https://example.org/path)."
    )

    candidates = TextLinkSource().extract(analysis)

    assert [candidate.url for candidate in candidates] == [
        "https://example.com/a_(b)",
        "https://example.org/path",
    ]


def test_fact_check_source_handles_missing_and_none_review_lists() -> None:
    candidates = FactCheckLinkSource().extract(AnalysisDataContainer(), [_reading_result()])

    assert [candidate.url for candidate in candidates] == [
        "https://fact.example/review/1",
        "https://fact.example/review/2",
    ]


def test_extract_links_deduplicates_canonical_urls_with_fact_checks_first() -> None:
    analysis = AnalysisDataContainer(
        original_text="See https://fact.example/review/1#section and https://user.example/article."
    )

    assert extract_links(analysis, [_reading_result()]) == [
        "https://fact.example/review/1",
        "https://fact.example/review/2",
        "https://user.example/article",
    ]


def test_extract_links_and_service_share_candidate_selection() -> None:
    from articleScraping.service import _select_candidates

    analysis = AnalysisDataContainer(
        original_text="See https://fact.example/review/1#section and https://user.example/article."
    )
    sources = [FactCheckLinkSource(), TextLinkSource()]
    service_candidates, _reserves, failures, found_count = _select_candidates(
        analysis, [_reading_result()], sources
    )

    assert [candidate.url for candidate in service_candidates] == extract_links(
        analysis, [_reading_result()]
    )
    assert failures == []
    assert found_count == 4


def test_trusted_links_interleave_with_fact_checks_before_user_links() -> None:
    from types import SimpleNamespace

    from articleScraping.links import TrustedLinkSource, select_candidates
    from articleScraping.protocols import CandidateLink

    report = SimpleNamespace(
        hits=[
            SimpleNamespace(url="https://www.gov.pl/web/rcb/a", kind="article"),
            SimpleNamespace(url="https://meteo.imgw.pl/", kind="reference"),
            SimpleNamespace(url="https://www.gov.pl/web/rcb/b", kind="article"),
        ]
    )
    trusted = TrustedLinkSource(report).extract(AnalysisDataContainer())
    assert [candidate.url for candidate in trusted] == [
        "https://www.gov.pl/web/rcb/a",
        "https://www.gov.pl/web/rcb/b",
    ]
    assert TrustedLinkSource(None).extract(AnalysisDataContainer()) == []

    candidates = [
        CandidateLink("https://user.example/1", "user_text"),
        *[CandidateLink(f"https://fact.example/{index}", "fact_check") for index in range(4)],
        *trusted,
    ]
    selected, rejected = select_candidates(candidates, max_links=4)
    assert [candidate.source for candidate in selected] == [
        "fact_check",
        "trusted_source",
        "fact_check",
        "trusted_source",
    ]
    assert {kind for _, kind in rejected} == {"LinkLimitExceeded"}
