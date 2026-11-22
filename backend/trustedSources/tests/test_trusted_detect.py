import pytest

from trustedSources.detect import detect, detect_and_update
from trustedSources.registry import new_source

from .fake_web import FakeWeb

RSS = (
    '<?xml version="1.0"?><rss><channel>'
    + "".join(f"<item><title>Wpis {i}</title><link>https://kgsok.pl/{i}</link></item>" for i in range(4))
    + "</channel></rss>"
)
LISTING = "<html><body>" + "".join(
    f'<a href="/pol/aktualnosci/{i},Komunikat.html">Ważny komunikat policji numer {i}</a>' for i in range(6)
) + "</body></html>"
APP = "<html><head><title>Mapa utrudnień</title><meta name='description' content='Mapa na żywo'></head><body><div id='app'></div></body></html>"
SITEMAP = '<?xml version="1.0"?><sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"><sitemap><loc>https://sar.gov.pl/a.xml</loc></sitemap></sitemapindex>'


@pytest.mark.asyncio
async def test_govpl_subsite_is_confirmed_in_dictionary() -> None:
    web = FakeWeb()
    web.add("https://www.gov.pl/api/data/indexdictionary", {"ministryId": {"rcb": "Rządowe Centrum Bezpieczeństwa"}})
    result = await detect(new_source("https://www.gov.pl/web/rcb/raport-dobowy3"), web.context())
    assert result.adapter == "govpl_search"
    assert result.params == {"site_id": "rcb"}
    assert result.name == "Rządowe Centrum Bezpieczeństwa"


@pytest.mark.asyncio
async def test_known_publisher_needs_no_network() -> None:
    web = FakeWeb()
    result = await detect(new_source("https://demagog.org.pl/"), web.context())
    assert result.adapter == "fact_check_publisher"
    assert web.requests == []


@pytest.mark.asyncio
async def test_advertised_feed_is_preferred() -> None:
    web = FakeWeb()
    web.add("https://kgsok.pl/", '<html><head><link rel="alternate" type="application/rss+xml" href="/feed/"></head></html>')
    web.add("https://kgsok.pl/feed/", RSS, content_type="application/rss+xml")
    result = await detect(new_source("https://kgsok.pl/"), web.context())
    assert result.adapter == "feed"
    assert result.params == {"feed_url": "https://kgsok.pl/feed/"}


@pytest.mark.asyncio
async def test_listing_page_is_detected() -> None:
    web = FakeWeb()
    web.add("https://policja.pl/pol/aktualnosci", LISTING)
    result = await detect(new_source("https://policja.pl/pol/aktualnosci"), web.context())
    assert result.adapter == "listing"


@pytest.mark.asyncio
async def test_sitemap_from_robots_then_reference_for_apps() -> None:
    web = FakeWeb()
    web.add("https://sar.gov.pl/", "<html><body>Strona</body></html>")
    web.add("https://sar.gov.pl/robots.txt", "Sitemap: https://sar.gov.pl/sm.xml\nSitemap: https://evil.example/x.xml", content_type="text/plain")
    web.add("https://sar.gov.pl/sm.xml", SITEMAP, content_type="application/xml")
    assert (await detect(new_source("https://sar.gov.pl/"), web.context())).adapter == "sitemap"

    web.add("https://drogi.gddkia.gov.pl/mapa", APP)
    result = await detect(new_source("https://drogi.gddkia.gov.pl/mapa"), web.context())
    assert result.adapter == "reference"
    assert result.name == "Mapa utrudnień" and result.description == "Mapa na żywo"


@pytest.mark.asyncio
async def test_private_address_is_recorded_as_failed_check() -> None:
    web = FakeWeb()
    ctx = web.context()
    ctx.fetcher = web.fetcher(public=False)
    source = new_source("https://intranet-looking.example.pl/")
    updated = await detect_and_update(source, ctx)
    assert updated.adapter == "pending"
    assert updated.last_check is not None and not updated.last_check.ok
    assert updated.last_check.error == "ApiConnectionError"
    assert web.requests == []


@pytest.mark.asyncio
async def test_locked_adapter_is_not_redetected() -> None:
    source = new_source("https://meteo.imgw.pl/").model_copy(update={"adapter": "reference", "adapter_locked": True})
    web = FakeWeb()
    updated = await detect_and_update(source, web.context())
    assert updated.adapter == "reference"
    assert web.requests == []
