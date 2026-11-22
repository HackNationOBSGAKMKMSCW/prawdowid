import asyncio

import httpx
import pytest
from apiReading.exceptions import ApiAuthError

from trustedSources.adapters.fact_check import FactCheckPublisherAdapter
from trustedSources.adapters.govpl import GovPlSearchAdapter, site_id_from_url
from trustedSources.adapters.listing import ListingAdapter

from .conftest import make_source
from .fake_web import FakeWeb, govpl_results


def test_site_id_from_url() -> None:
    assert site_id_from_url("https://www.gov.pl/web/rcb/raport-dobowy3") == "rcb"
    assert site_id_from_url("https://www.gov.pl/web/obrona-narodowa") == "obrona-narodowa"
    assert site_id_from_url("https://www.gov.pl/") is None
    assert site_id_from_url("https://rcb.example.pl/web/rcb") is None


@pytest.mark.asyncio
async def test_govpl_searches_only_whitelisted_subsites() -> None:
    web = FakeWeb()

    def search(request: httpx.Request) -> httpx.Response:
        site = request.url.params.get("ministryId")
        if site == "rcb":
            # A result outside the queried subsite is dropped.
            return httpx.Response(
                200, json=govpl_results(("Alert RCB", "/web/rcb/alert-1"), ("Szkoła", "/web/szkola/x"))
            )
        if site == "gis":
            return httpx.Response(200, json=govpl_results(("Ostrzeżenie GIS", "/web/gis/ostrz")))
        raise AssertionError("portal-wide search must not happen")

    web.add("https://www.gov.pl/api/data/search", search)
    sources = [
        make_source(id="rcb", url="https://www.gov.pl/web/rcb", adapter="govpl_search",
                    params={"site_id": "rcb"}, domains=["www.gov.pl"]),
        make_source(id="rcb-2", url="https://www.gov.pl/web/rcb/raport", adapter="govpl_search",
                    params={"site_id": "rcb"}, domains=["www.gov.pl"]),
        make_source(id="gis", url="https://www.gov.pl/web/gis", adapter="govpl_search",
                    params={"site_id": "gis"}, domains=["www.gov.pl"]),
        make_source(id="portal", url="https://www.gov.pl/", adapter="govpl_search",
                    params={"site_id": None}, domains=["www.gov.pl"]),
    ]
    queries = ["alert", "wiatr", "trzecie", "4", "5", "6", "siódme"]
    hits = await GovPlSearchAdapter().search(sources, queries, web.context())

    # 6 queries max x (rcb + gis); duplicate rcb source and the bare portal add no request.
    assert len(web.requests) == 12
    assert {request.url.params.get("ministryId") for request in web.requests} == {"rcb", "gis"}
    urls = {(hit.source_id, hit.url) for hit in hits}
    assert ("rcb", "https://www.gov.pl/web/rcb/alert-1") in urls
    assert ("gis", "https://www.gov.pl/web/gis/ostrz") in urls
    assert all("szkola" not in url for _, url in urls)


@pytest.mark.asyncio
async def test_fact_check_adapter_filters_publisher_and_domain() -> None:
    web = FakeWeb()
    payload = {
        "claims": [
            {
                "text": "Ziemia jest płaska",
                "claimReview": [
                    {"url": "https://demagog.org.pl/fake_news/plaska", "title": "Płaska Ziemia? Fałsz",
                     "textualRating": "Fałsz", "reviewDate": "2026-02-13T00:00:00Z"},
                    {"url": "https://other.example/review", "title": "Inny"},
                ],
            }
        ]
    }
    web.add("https://factchecktools.googleapis.com/v1alpha1/claims:search", payload)
    source = make_source(id="demagog", url="https://demagog.org.pl/", adapter="fact_check_publisher",
                         params={"site": "demagog.org.pl"}, domains=["demagog.org.pl"], trust="fact_checker")

    hits = await FactCheckPublisherAdapter().search([source], ["płaska Ziemia"], web.context())

    assert web.requests[0].url.params["reviewPublisherSiteFilter"] == "demagog.org.pl"
    assert [hit.url for hit in hits] == ["https://demagog.org.pl/fake_news/plaska"]
    assert hits[0].snippet == "Fałsz: Ziemia jest płaska"
    assert hits[0].trust == "fact_checker"


@pytest.mark.asyncio
async def test_fact_check_adapter_requires_key() -> None:
    source = make_source(adapter="fact_check_publisher", params={"site": "demagog.org.pl"})
    with pytest.raises(ApiAuthError):
        await FactCheckPublisherAdapter().search(
            [source], ["x"], FakeWeb().context(google_fact_check_api_key=None)
        )


@pytest.mark.asyncio
async def test_listing_is_cached_and_served_stale_on_error() -> None:
    web = FakeWeb()
    calls = {"count": 0}
    page = (
        "<html><body><main>"
        + "".join(
            f'<a href="/aktualnosci/{index}">Komunikat numer {index} w sprawie powodzi</a>'
            for index in range(6)
        )
        + "</main></body></html>"
    )

    def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        if calls["count"] > 1:
            return httpx.Response(503)
        return httpx.Response(200, text=page, headers={"content-type": "text/html"})

    web.add("https://example.gov.pl/aktualnosci", handler)
    source = make_source()
    ctx = web.context(cache_ttl=0.2)
    first = await ListingAdapter().search([source], ["powódź"], ctx)
    assert len(first) == 6

    # Fresh cache: no second request.
    await ListingAdapter().search([source], ["powódź"], ctx)
    assert calls["count"] == 1

    # Expired cache + failing site: stale entries are served.
    await asyncio.sleep(0.25)
    again = await ListingAdapter().search([source], ["powódź"], ctx)
    assert calls["count"] == 2
    assert len(again) == 6
