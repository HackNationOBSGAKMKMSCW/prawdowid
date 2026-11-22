"""Wikipedia and Sejm ELI adapters, and their classification by host."""

import httpx
import pytest
from apiReading.exceptions import ApiReadingError

from trustedSources.adapters.sejm_eli import SejmEliAdapter
from trustedSources.adapters.wikipedia import WikipediaAdapter, article_url
from trustedSources.registry import new_source

from .conftest import make_source
from .fake_web import FakeWeb


def test_wikipedia_and_isap_are_classified_without_network() -> None:
    wiki = new_source("https://pl.wikipedia.org/")
    assert (wiki.adapter, wiki.params, wiki.trust) == ("wikipedia", {"lang": "pl"}, "other")
    assert wiki.domains == ["pl.wikipedia.org"]

    isap = new_source("https://isap.sejm.gov.pl/")
    assert (isap.adapter, isap.trust) == ("sejm_eli", "official")
    assert isap.owns_url("api.sejm.gov.pl") and isap.owns_url("isap.sejm.gov.pl")


def test_article_url_encodes_title() -> None:
    assert article_url("pl", "Rysy") == "https://pl.wikipedia.org/wiki/Rysy"
    assert article_url("pl", "Stolica Polski") == "https://pl.wikipedia.org/wiki/Stolica_Polski"
    assert article_url("pl", "Kraków (miasto)") == "https://pl.wikipedia.org/wiki/Krak%C3%B3w_(miasto)"


def _wiki_source():
    return make_source(
        id="wiki", url="https://pl.wikipedia.org/", name="Wikipedia (polska)", adapter="wikipedia",
        params={"lang": "pl"}, domains=["pl.wikipedia.org"], path_prefix="/", trust="other",
    )


@pytest.mark.asyncio
async def test_wikipedia_hits_link_articles_and_strip_markup() -> None:
    web = FakeWeb()

    def search(request: httpx.Request) -> httpx.Response:
        assert request.url.params["list"] == "search"
        query = request.url.params["srsearch"]
        return httpx.Response(200, json={"query": {"search": [
            {"title": "Rysy", "snippet": f'<span class="searchmatch">{query}</span> w Tatrach'},
        ]}})

    web.add("https://pl.wikipedia.org/w/api.php", search)
    queries = ["Rysy", "najwyższy szczyt", "trzecie", "czwarte", "piąte"]
    hits = await WikipediaAdapter().search([_wiki_source()], queries, web.context())

    assert len(web.requests) == 4  # MAX_QUERIES
    assert hits[0].url == "https://pl.wikipedia.org/wiki/Rysy"
    assert hits[0].snippet == "Rysy w Tatrach"
    assert hits[0].trust == "other" and hits[0].kind == "article"


@pytest.mark.asyncio
async def test_wikipedia_raises_only_when_every_request_fails() -> None:
    web = FakeWeb()
    web.add("https://pl.wikipedia.org/w/api.php", httpx.Response(503))
    with pytest.raises(ApiReadingError):
        await WikipediaAdapter().search([_wiki_source()], ["Rysy"], web.context())


@pytest.mark.asyncio
async def test_sejm_eli_links_act_text_or_isap_page() -> None:
    web = FakeWeb()
    web.add("https://api.sejm.gov.pl/eli/acts/search", {
        "totalCount": 2, "count": 2, "offset": 0,
        "items": [
            {"publisher": "DU", "year": 2024, "pos": 10, "title": "Ustawa o płatnościach",
             "address": "WDU20240000010", "status": "obowiązujący", "textHTML": True,
             "promulgation": "2024-01-05"},
            {"publisher": "MP", "year": 2023, "pos": 7, "title": "Obwieszczenie w sprawie gotówki",
             "address": "WMP20230000007", "textHTML": False},
        ],
    })
    source = make_source(
        id="isap", url="https://isap.sejm.gov.pl/", adapter="sejm_eli", params={},
        domains=["api.sejm.gov.pl", "isap.sejm.gov.pl"], path_prefix="/",
    )
    hits = await SejmEliAdapter().search([source], ["gotówka"], web.context())

    assert [hit.url for hit in hits] == [
        "https://api.sejm.gov.pl/eli/acts/DU/2024/10/text.html",
        "https://isap.sejm.gov.pl/isap.nsf/DocDetails.xsp?id=WMP20230000007",
    ]
    assert hits[0].published_at is not None and hits[0].published_at.year == 2024
    assert "obowiązujący" in hits[0].snippet
