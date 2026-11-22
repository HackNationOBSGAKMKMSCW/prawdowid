import httpx
import pytest
from textAnalysis.container import AnalysisDataContainer

from trustedSources import service
from trustedSources.registry import SourceRegistry
from trustedSources.settings import TrustedSettings

from .fake_web import FakeWeb, govpl_results

FEED = (
    '<?xml version="1.0"?><rss><channel>'
    "<item><title>Alert RCB: silny wiatr na Pomorzu</title><link>https://policja.pl/pol/1</link></item>"
    "<item><title>Zbiórka darów</title><link>https://policja.pl/pol/2</link></item>"
    "</channel></rss>"
)


def test_queries_prefer_llm_phrases_then_claims() -> None:
    analysis = AnalysisDataContainer(
        statements=["Ziemia jest płaska.", "Inna teza."],
        search_queries=["płaska Ziemia", "Płaska  ziemia"],
    )
    assert service.queries_for(analysis) == ["płaska Ziemia", "Ziemia jest płaska.", "Inna teza."]
    assert service.queries_for(AnalysisDataContainer(source_text="tylko tekst")) == ["tylko tekst"]


@pytest.mark.asyncio
async def test_search_combines_sources_and_isolates_failures(registry: SourceRegistry) -> None:
    web = FakeWeb()
    web.add(
        "https://www.gov.pl/api/data/search",
        govpl_results(("Alert RCB - silny wiatr (20.11)", "/web/rcb/alert-rcb-silny-wiatr")),
    )
    web.add("https://factchecktools.googleapis.com/v1alpha1/claims:search", lambda r: httpx.Response(500))
    web.add("https://policja.pl/feed.rss", FEED, content_type="application/rss+xml")
    policja = next(source for source in registry.list() if source.name == "Policja")
    registry.save(
        policja.model_copy(update={"adapter": "feed", "params": {"feed_url": "https://policja.pl/feed.rss"}})
    )
    settings = TrustedSettings(google_fact_check_api_key="k")

    report = await service.search(
        ["alert RCB silny wiatr"],
        registry=registry,
        settings=settings,
        http_client=web.client(),
        fetcher=web.fetcher(),
    )

    titles = [hit.title for hit in report.hits]
    assert "Alert RCB - silny wiatr (20.11)" in titles
    assert "Alert RCB: silny wiatr na Pomorzu" in titles
    assert "Zbiórka darów" not in titles
    assert any(hit.kind == "reference" and hit.source_name == "IMGW" for hit in report.hits)
    assert [(failure.source_id, failure.kind) for failure in report.failures] == [
        ("demagog-org-pl", "ApiHttpError")
    ]
    assert report.sources_queried == 4


@pytest.mark.asyncio
async def test_run_never_raises(monkeypatch) -> None:
    async def broken(*args, **kwargs):
        raise RuntimeError("store unavailable")

    monkeypatch.setattr(service, "search", broken)
    report = await service.run(AnalysisDataContainer(statements=["Teza."]))
    assert report.hits == []
    assert report.failures[0].kind == "RuntimeError"


@pytest.mark.asyncio
async def test_unknown_adapter_is_reported_not_fatal(registry: SourceRegistry) -> None:
    source = registry.list()[0]
    registry.save(source.model_copy(update={"adapter": "does_not_exist"}))
    settings = TrustedSettings(google_fact_check_api_key=None)
    web = FakeWeb()
    report = await service.search(
        ["cokolwiek"], registry=registry, settings=settings, http_client=web.client(), fetcher=web.fetcher()
    )
    assert ("UnknownAdapter" in {failure.kind for failure in report.failures})


def test_keyword_query_drops_function_words() -> None:
    assert service.keyword_query("Ziemia jest płaska.") == "Ziemia płaska"
    assert service.keyword_query("Policja ostrzega przed oszustami metodą na wnuczka") == (
        "Policja ostrzega oszustami metodą"
    )


@pytest.mark.asyncio
async def test_queries_for_text_falls_back_without_analysis(monkeypatch) -> None:
    import textAnalysis

    async def unavailable(text):
        raise RuntimeError("no key")

    monkeypatch.setattr(textAnalysis, "run", unavailable)
    assert await service.queries_for_text("Ziemia jest  płaska.") == ["Ziemia jest płaska.", "Ziemia płaska"]

    async def analysed(text):
        return AnalysisDataContainer(statements=["Ziemia jest płaska."], search_queries=["płaska Ziemia"])

    monkeypatch.setattr(textAnalysis, "run", analysed)
    assert await service.queries_for_text("Ziemia jest płaska.") == ["płaska Ziemia", "Ziemia jest płaska."]
