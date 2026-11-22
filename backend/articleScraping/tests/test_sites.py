"""At least two different sites, and the structured final report."""

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from apiReading.exceptions import ApiResponseError
from articleScraping import run
from articleScraping.links import select_candidates
from articleScraping.protocols import CandidateLink, RawArticle
from articleScraping.tests.test_service import FakeExtractor, FixedClock, FixedLinks
from articleScraping.url_validation import site_key
from textAnalysis.container import AnalysisDataContainer


def test_site_key_treats_govpl_subsites_as_sites() -> None:
    assert site_key("https://www.gov.pl/web/rcb/alert-1") == "gov.pl/web/rcb"
    assert site_key("https://www.gov.pl/web/gis/x") == "gov.pl/web/gis"
    assert site_key("https://www.demagog.org.pl/fake_news/x") == "demagog.org.pl"
    assert site_key("https://moje.cert.pl/komunikaty/1") == "moje.cert.pl"


def test_selection_always_includes_a_second_site() -> None:
    links = [CandidateLink(f"https://a.example/{index}", "fact_check") for index in range(5)]
    links.append(CandidateLink("https://b.example/1", "fact_check"))
    selected, rejected = select_candidates(links, max_links=3)
    assert [candidate.url for candidate in selected] == [
        "https://a.example/0",
        "https://a.example/1",
        "https://b.example/1",
    ]
    assert {kind for _, kind in rejected} == {"LinkLimitExceeded"}


@pytest.mark.asyncio
async def test_reserve_from_a_new_site_replaces_a_failed_one() -> None:
    a = [f"https://a.example/{index}" for index in range(5)]
    links = [
        *(CandidateLink(url, "fact_check", title=f"A {url[-1]}", publisher="Demagog") for url in a),
        CandidateLink("https://b.example/1", "fact_check", title="B", publisher="RCB"),
        CandidateLink("https://c.example/1", "fact_check", title="Tytuł z wyszukiwarki", publisher="GIS"),
    ]
    extractor = FakeExtractor(
        {
            **{url: RawArticle(text=f"treść {url}", title=f"Artykuł {url}", author="Jan Kowalski",
                               date="Fri, 13 Feb 2026 10:00:00 GMT") for url in a},
            "https://b.example/1": ApiResponseError("local_article", "broken"),
            "https://c.example/1": RawArticle(text="cała treść C"),
        }
    )
    trusted = SimpleNamespace(
        hits=[SimpleNamespace(url="https://meteo.imgw.pl/", kind="reference", title="IMGW", source_name="IMGW")]
    )
    submitted = datetime(2026, 11, 22, 8, 30, tzinfo=UTC)
    original = "  Ziemia jest płaska!!  "

    report = await run(
        AnalysisDataContainer(original_text=original, source_text="Ziemia jest płaska"),
        extractor=extractor,
        link_sources=[FixedLinks(links)],
        clock=FixedClock(),
        trusted=trusted,
        submitted_at=submitted,
    )

    assert extractor.calls[-1] == "https://c.example/1"
    assert report.min_sites_met and report.distinct_sites == 2
    assert report.submitted_at == submitted
    assert report.user_input == original

    first = report.articles[0]
    assert (first.title, first.author, first.publisher, first.site) == (
        "Artykuł https://a.example/0", "Jan Kowalski", "Demagog", "a.example"
    )
    assert first.published_at == datetime(2026, 2, 13, 10, tzinfo=UTC)
    c_article = next(article for article in report.articles if article.site == "c.example")
    assert c_article.title == "Tytuł z wyszukiwarki" and c_article.text == "cała treść C"
    assert c_article.author is None and c_article.publisher == "GIS"

    status = {link.url: (link.kind, link.status) for link in report.sources}
    assert status["https://b.example/1"] == ("fact_check", "failed")
    assert status["https://c.example/1"] == ("fact_check", "scraped")
    assert status["https://a.example/4"] == ("fact_check", "not_scraped")
    assert status["https://meteo.imgw.pl/"] == ("trusted_reference", "reference")
    assert [failure.url for failure in report.failures] == ["https://b.example/1"]


@pytest.mark.asyncio
async def test_single_site_is_reported_when_nothing_else_exists() -> None:
    links = [CandidateLink(f"https://a.example/{index}", "fact_check") for index in range(2)]
    report = await run(
        AnalysisDataContainer(original_text="x"),
        extractor=FakeExtractor({link.url: RawArticle(text="t") for link in links}),
        link_sources=[FixedLinks(links)],
        clock=FixedClock(),
    )
    assert len(report.articles) == 2
    assert report.distinct_sites == 1 and not report.min_sites_met
