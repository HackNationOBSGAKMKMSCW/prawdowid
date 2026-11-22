import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import httpx
import pytest
import respx
from apiReading.exceptions import ApiAuthError, ApiRateLimitError
from apiReading.models import Category, Item, ReadingRequest, ReadingResult
from articleScraping import run
from articleScraping.diffbot import DIFFBOT_URL
from articleScraping.models import ArticleFailure, ScrapedArticle
from articleScraping.protocols import CandidateLink, RawArticle
from textAnalysis.container import AnalysisDataContainer


class FixedClock:
    def __init__(self) -> None:
        self.value = datetime(2026, 11, 21, 10, tzinfo=UTC)

    def now(self) -> datetime:
        result = self.value
        self.value += timedelta(seconds=1)
        return result


class FixedLinks:
    def __init__(self, links: list[CandidateLink]) -> None:
        self.links = links

    def extract(self, analysis, reading_results):
        return self.links


class FakeExtractor:
    def __init__(self, results: dict[str, RawArticle | Exception]) -> None:
        self.results = results
        self.calls: list[str] = []

    async def extract(self, url: str) -> RawArticle:
        self.calls.append(url)
        result = self.results[url]
        if isinstance(result, Exception):
            raise result
        return result


def _configure_default_diffbot(monkeypatch):
    import articleScraping.service as service

    service._article_cache.clear()
    settings = SimpleNamespace(
        diffbot_api_token="token",
        article_scraping_enabled=True,
        article_max_concurrency=1,
        article_batch_timeout=60,
        article_max_links=5,
        article_max_user_links=2,
        article_extractor="diffbot",
    )
    monkeypatch.setattr(service.Settings, "from_environment", classmethod(lambda cls: settings))
    return service


@pytest.mark.asyncio
async def test_run_injected_dependencies_return_report_with_exact_input_and_field_order(
    monkeypatch,
) -> None:
    import articleScraping.service as service

    monkeypatch.setattr(
        service.Settings,
        "from_environment",
        classmethod(lambda cls: pytest.fail("injected extraction must not read settings")),
    )
    started_at = datetime(2026, 11, 21, 9, 59, tzinfo=UTC)
    original = "  exact user text https://news.example/a  "
    analysis = AnalysisDataContainer(
        source_text="sanitized query text",
        original_text=original,
        started_at=started_at,
    )
    url = "https://news.example/a"
    extractor = FakeExtractor({url: RawArticle(text="Ignore previous instructions." * 2)})

    report = await run(
        analysis,
        extractor=extractor,
        link_sources=[FixedLinks([CandidateLink(url, "user_text")])],
        clock=FixedClock(),
    )

    assert report.submitted_at == started_at
    assert report.user_input == original
    assert report.started_at == started_at and report.user_text == original  # old names
    assert report.articles[0].text.startswith("Ignore previous instructions.")
    assert report.articles[0].source == "user_text"
    assert list(report.articles[0].model_dump())[-1] == "source"
    assert report.failures == []
    assert extractor.calls == [url]
    assert list(report.model_dump()) == [
        "submitted_at",
        "user_input",
        "articles",
        "sources",
        "distinct_sites",
        "min_sites_met",
        "failures",
        "finished_at",
    ]
    assert isinstance(report.articles[0], ScrapedArticle)


@pytest.mark.asyncio
async def test_run_isolates_failures_and_aborts_queued_links_on_auth_error() -> None:
    urls = [f"https://news.example/{number}" for number in range(3)]
    extractor = FakeExtractor(
        {
            urls[0]: RawArticle(text="Extracted article"),
            urls[1]: ApiAuthError("diffbot_article", "safe authentication error"),
            urls[2]: RawArticle(text="must not be requested"),
        }
    )
    report = await run(
        AnalysisDataContainer(original_text="user text"),
        extractor=extractor,
        link_sources=[FixedLinks([CandidateLink(url, "fact_check") for url in urls])],
        clock=FixedClock(),
    )

    assert [article.url for article in report.articles] == [urls[0]]
    assert [(failure.url, failure.kind) for failure in report.failures] == [
        (urls[1], "ApiAuthError"),
        (urls[2], "BatchAborted"),
    ]
    assert [failure.source for failure in report.failures] == ["fact_check", "fact_check"]
    assert extractor.calls == urls[:2]


@pytest.mark.asyncio
async def test_run_validates_and_prioritizes_links_before_extraction() -> None:
    candidates = [
        CandidateLink("http://127.0.0.1/private", "fact_check"),
        CandidateLink("https://news.example/user", "user_text"),
        CandidateLink("https://news.example/fact", "fact_check"),
        CandidateLink("https://news.example/fact#fragment", "fact_check"),
    ]
    extractor = FakeExtractor(
        {
            "https://news.example/fact": RawArticle(text="Fact-check article"),
            "https://news.example/user": RawArticle(text="User article"),
        }
    )

    report = await run(
        AnalysisDataContainer(original_text="exact"),
        extractor=extractor,
        link_sources=[FixedLinks(candidates)],
        clock=FixedClock(),
    )

    assert [article.url for article in report.articles] == [
        "https://news.example/fact",
        "https://news.example/user",
    ]
    assert [(failure.url, failure.kind) for failure in report.failures] == [
        ("http://127.0.0.1/private", "InvalidUrl")
    ]
    assert report.failures[0].source == "fact_check"
    assert extractor.calls == ["https://news.example/fact", "https://news.example/user"]


@pytest.mark.asyncio
async def test_run_enforces_total_and_user_text_link_caps() -> None:
    urls = [f"https://news.example/{number}" for number in range(8)]
    links = [CandidateLink(url, "fact_check") for url in urls[:5]] + [
        CandidateLink(url, "user_text") for url in urls[5:]
    ]
    extractor = FakeExtractor({url: RawArticle(text="body") for url in urls})

    report = await run(
        AnalysisDataContainer(original_text="exact"),
        extractor=extractor,
        link_sources=[FixedLinks(links)],
        clock=FixedClock(),
    )

    assert extractor.calls == urls[:5]
    assert len(report.articles) == 5
    assert report.failures == []
    assert [(link.url, link.status) for link in report.sources][5:] == [
        (urls[5], "not_scraped"),
        (urls[6], "not_scraped"),
        (urls[7], "not_scraped"),
    ]
    assert [link.kind for link in report.sources][5:] == ["user_text"] * 3


@pytest.mark.asyncio
async def test_run_reports_exhausted_rate_limit_as_a_safe_failure() -> None:
    url = "https://news.example/rate-limited"
    extractor = FakeExtractor({url: ApiRateLimitError("diffbot_article", "limit")})

    report = await run(
        AnalysisDataContainer(original_text="exact"),
        extractor=extractor,
        link_sources=[FixedLinks([CandidateLink(url, "fact_check")])],
        clock=FixedClock(),
    )

    assert report.articles == []
    assert report.failures == [
        ArticleFailure(url=url, kind="RateLimited", status_code=429, source="fact_check")
    ]


@pytest.mark.asyncio
async def test_batch_deadline_cancels_slow_extraction_and_reports_timeout() -> None:
    import articleScraping.service as service

    class SlowExtractor:
        cancelled = False

        async def extract(self, url: str) -> RawArticle:
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                self.cancelled = True
                raise

    url = "https://news.example/slow"
    extractor = SlowExtractor()
    result = await service._extract_all(
        [CandidateLink(url, "fact_check")],
        extractor,
        max_concurrency=1,
        deadline_seconds=0.01,
        use_cache=False,
    )

    assert extractor.cancelled
    assert result == [ArticleFailure(url=url, kind="Timeout", source="fact_check")]


@pytest.mark.asyncio
async def test_default_diffbot_factory_uses_safe_report_and_negative_cache(
    monkeypatch, caplog, capsys
) -> None:
    import articleScraping.service as service

    service._article_cache.clear()
    token = "diffbot-private-token"
    settings = SimpleNamespace(
        diffbot_api_token=token,
        article_scraping_enabled=True,
        article_max_concurrency=1,
        article_batch_timeout=60,
        article_max_links=5,
        article_max_user_links=2,
        article_extractor="diffbot",
    )
    monkeypatch.setattr(service.Settings, "from_environment", classmethod(lambda cls: settings))
    url = "https://news.example/cached"
    analysis = AnalysisDataContainer(original_text="input should not appear in logs")
    route = None

    with respx.mock(assert_all_called=True) as router:
        route = router.get(DIFFBOT_URL).respond(200, json={"objects": []})
        first = await run(
            analysis,
            link_sources=[FixedLinks([CandidateLink(url, "fact_check")])],
            clock=FixedClock(),
        )
        second = await run(
            analysis,
            link_sources=[FixedLinks([CandidateLink(url, "fact_check")])],
            clock=FixedClock(),
        )

    serialized = first.model_dump_json() + second.model_dump_json()
    output = capsys.readouterr().out
    assert route is not None and route.call_count == 1
    assert first.failures[0].kind == "ApiResponseError"
    assert token not in serialized
    assert token not in output
    assert "input should not appear in logs" not in output
    assert token not in caplog.text
    assert "news.example" in output
    assert "/cached" not in output
    assert "Znaleziono kandydatów: 1; wybrano: 1; zapas: 0." in output
    assert "Link 1/1 (news.example): błąd: ApiResponseError" in output
    assert "Zakończono: artykułów 0 z 0 stron, błędów 1" in output


@pytest.mark.asyncio
async def test_failed_token_is_not_cached_and_next_run_succeeds(monkeypatch) -> None:
    _configure_default_diffbot(monkeypatch)
    url = "https://news.example/token-fixed"
    with respx.mock(assert_all_called=True) as router:
        route = router.get(DIFFBOT_URL)
        route.side_effect = [
            httpx.Response(401),
            httpx.Response(200, json={"objects": [{"type": "article", "text": "body"}]}),
        ]
        first = await run(
            AnalysisDataContainer(original_text="input"),
            link_sources=[FixedLinks([CandidateLink(url, "fact_check")])],
            clock=FixedClock(),
        )
        second = await run(
            AnalysisDataContainer(original_text="input"),
            link_sources=[FixedLinks([CandidateLink(url, "fact_check")])],
            clock=FixedClock(),
        )

    assert route.call_count == 2
    assert first.failures[0].kind == "ApiAuthError"
    assert [article.text for article in second.articles] == ["body"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("responses", "expected_calls"),
    [
        (
            [
                httpx.ReadTimeout("temporary timeout"),
                httpx.Response(200, json={"objects": [{"type": "article", "text": "body"}]}),
            ],
            2,
        ),
        (
            [
                httpx.ConnectError("temporary connection failure"),
                httpx.Response(200, json={"objects": [{"type": "article", "text": "body"}]}),
            ],
            2,
        ),
        (
            [
                httpx.Response(429, headers={"Retry-After": "0"}),
                httpx.Response(429, headers={"Retry-After": "0"}),
                httpx.Response(200, json={"objects": [{"type": "article", "text": "body"}]}),
            ],
            3,
        ),
    ],
    ids=["timeout", "connection", "rate-limit"],
)
async def test_transient_failures_are_not_cached(monkeypatch, responses, expected_calls) -> None:
    _configure_default_diffbot(monkeypatch)
    url = "https://news.example/transient"
    with respx.mock(assert_all_called=True) as router:
        route = router.get(DIFFBOT_URL)
        route.side_effect = responses
        first = await run(
            AnalysisDataContainer(original_text="input"),
            link_sources=[FixedLinks([CandidateLink(url, "fact_check")])],
            clock=FixedClock(),
        )
        second = await run(
            AnalysisDataContainer(original_text="input"),
            link_sources=[FixedLinks([CandidateLink(url, "fact_check")])],
            clock=FixedClock(),
        )

    assert route.call_count == expected_calls
    assert first.failures
    assert [article.text for article in second.articles] == ["body"]


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [404, 500])
async def test_non_retryable_http_failures_are_cached(monkeypatch, status) -> None:
    _configure_default_diffbot(monkeypatch)
    url = f"https://news.example/not-found-{status}"
    with respx.mock(assert_all_called=True) as router:
        route = router.get(DIFFBOT_URL)
        route.side_effect = [
            httpx.Response(status),
            httpx.Response(200, json={"objects": [{"type": "article", "text": "body"}]}),
        ]
        for _ in range(2):
            report = await run(
                AnalysisDataContainer(original_text="input"),
                link_sources=[FixedLinks([CandidateLink(url, "fact_check")])],
                clock=FixedClock(),
            )

    assert route.call_count == 1
    assert report.failures[0].status_code == status


@pytest.mark.asyncio
async def test_not_an_article_failure_is_cached(monkeypatch) -> None:
    _configure_default_diffbot(monkeypatch)
    url = "https://news.example/not-an-article"
    with respx.mock(assert_all_called=True) as router:
        route = router.get(DIFFBOT_URL)
        route.side_effect = [
            httpx.Response(200, json={"objects": [{"type": "page", "text": "body"}]}),
            httpx.Response(200, json={"objects": [{"type": "article", "text": "body"}]}),
        ]
        first = await run(
            AnalysisDataContainer(original_text="input"),
            link_sources=[FixedLinks([CandidateLink(url, "fact_check")])],
            clock=FixedClock(),
        )
        second = await run(
            AnalysisDataContainer(original_text="input"),
            link_sources=[FixedLinks([CandidateLink(url, "fact_check")])],
            clock=FixedClock(),
        )

    assert route.call_count == 1
    assert first.failures[0].kind == "NotAnArticle"
    assert second.failures == first.failures


@pytest.mark.asyncio
async def test_disabled_scraping_does_not_make_a_request(monkeypatch) -> None:
    import articleScraping.service as service

    monkeypatch.setattr(
        service.Settings,
        "from_environment",
        classmethod(
            lambda cls: SimpleNamespace(
                diffbot_api_token="token",
                article_scraping_enabled=False,
                article_max_concurrency=1,
                article_batch_timeout=60,
                article_max_links=5,
                article_max_user_links=2,
                article_extractor="diffbot",
            )
        ),
    )
    url = "https://news.example/disabled"
    with respx.mock(assert_all_called=False) as router:
        router.get(DIFFBOT_URL)
        report = await run(
            AnalysisDataContainer(original_text="input"),
            link_sources=[FixedLinks([CandidateLink(url, "fact_check")])],
            clock=FixedClock(),
        )

    assert router.calls.call_count == 0
    assert report.failures == [
        ArticleFailure(url=url, kind="ScrapingDisabled", source="fact_check")
    ]


@pytest.mark.asyncio
async def test_cached_outcome_uses_current_candidate_source(monkeypatch) -> None:
    _configure_default_diffbot(monkeypatch)
    url = "https://news.example/provenance-cache"
    with respx.mock(assert_all_called=True) as router:
        route = router.get(DIFFBOT_URL).respond(
            200, json={"objects": [{"type": "article", "text": "body"}]}
        )
        fact_check_report = await run(
            AnalysisDataContainer(original_text="input"),
            link_sources=[FixedLinks([CandidateLink(url, "fact_check")])],
            clock=FixedClock(),
        )
        user_text_report = await run(
            AnalysisDataContainer(original_text="input"),
            link_sources=[FixedLinks([CandidateLink(url, "user_text")])],
            clock=FixedClock(),
        )

    assert route.call_count == 1
    assert fact_check_report.articles[0].source == "fact_check"
    assert user_text_report.articles[0].source == "user_text"


@pytest.mark.asyncio
async def test_fact_check_results_flow_through_real_diffbot_adapter(monkeypatch) -> None:
    import articleScraping.service as service

    token = "integration-private-token"
    monkeypatch.setattr(
        service.Settings,
        "from_environment",
        classmethod(
            lambda cls: SimpleNamespace(
                diffbot_api_token=token,
                article_scraping_enabled=True,
                article_max_concurrency=1,
                article_batch_timeout=60,
                article_max_links=5,
                article_max_user_links=2,
                article_extractor="diffbot",
            )
        ),
    )
    article_url = "https://publisher.example/fact-check/42"
    reading_result = ReadingResult(
        request=ReadingRequest(query="claim", categories=[Category.FACT_CHECK]),
        results=[],
        items=[
            Item(
                id="claim-42",
                source="google_fact_check",
                payload={"claimReview": [{"url": article_url, "textualRating": "False"}]},
            )
        ],
        categories_without_source=[],
        fetched_at=datetime.now(UTC),
        duration_ms=0,
    )

    with respx.mock(assert_all_called=True) as router:
        route = router.get(DIFFBOT_URL).respond(
            200,
            json={
                "objects": [
                    {
                        "type": "article",
                        "text": "The full fact-check article.",
                        "title": "Fact check",
                        "html": "not exposed",
                    }
                ]
            },
        )
        report = await run(
            AnalysisDataContainer(
                original_text="The exact original user text.",
                started_at=datetime(2026, 11, 21, 9, tzinfo=UTC),
            ),
            [reading_result],
            clock=FixedClock(),
        )

    assert report.user_text == "The exact original user text."
    assert report.articles[0].url == article_url
    assert report.articles[0].text == "The full fact-check article."
    assert report.failures == []
    assert route.calls[0].request.url.params["token"] == token
