import gzip

import pytest

from trustedSources.parsing import maybe_gunzip, parse_feed, parse_html, parse_sitemap

RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel><title>Policja</title>
<item><title>Uwaga na oszustów &quot;na policjanta&quot;</title>
<link>https://policja.pl/pol/aktualnosci/1,Uwaga.html</link>
<description>&lt;p&gt;Oszuści dzwonią&lt;/p&gt;</description>
<pubDate>Fri, 20 Nov 2026 10:00:00 +0100</pubDate></item>
<item><title>Bez linku</title></item>
</channel></rss>""".encode()

ATOM = b"""<feed xmlns="http://www.w3.org/2005/Atom"><title>CERT</title>
<entry><title>Phishing na kuriera</title><link rel="alternate" href="/komunikaty/1/"/>
<updated>2026-11-03T08:00:00Z</updated><summary>SMS o dop\xc5\x82acie</summary></entry></feed>"""

XXE = b"""<?xml version="1.0"?>
<!DOCTYPE rss [<!ENTITY xxe SYSTEM "file:///etc/passwd">]>
<rss><channel><item><title>&xxe;</title><link>https://x.pl/a</link></item></channel></rss>"""

SITEMAP_INDEX = b"""<?xml version="1.0"?><sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
<sitemap><loc>https://sar.gov.pl/post-sitemap.xml</loc><lastmod>2026-11-10T10:00:00+00:00</lastmod></sitemap>
</sitemapindex>"""

URLSET = b"""<?xml version="1.0"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"
 xmlns:news="http://www.google.com/schemas/sitemap-news/0.9">
<url><loc>https://sar.gov.pl/akcja-ratownicza-na-baltyku</loc><lastmod>2026-11-01</lastmod></url>
<url><loc>https://sar.gov.pl/n</loc><news:news><news:title>Sztorm na Ba\xc5\x82tyku</news:title>
<news:publication_date>2026-11-02T12:00:00Z</news:publication_date></news:news></url>
</urlset>"""

LISTING = """<html><head><title>CERT – komunikaty</title>
<meta name="description" content="Komunikaty CERT Polska">
<link rel="alternate" type="application/rss+xml" href="/feed/"></head><body>
<nav><a href="/komunikaty/menu-link-ktory-jest-dlugi">Menu: wszystkie komunikaty w serwisie</a></nav>
<div class="cookie-bar"><a href="/polityka-cookies-i-prywatnosci">Polityka cookies i prywatności serwisu</a></div>
<main>
  <article><time datetime="2026-11-03">3.11</time>
    <a href="/komunikaty/2026/209/doplata-do-przesylki/">Dopłata do przesyłki? Zachowaj ostrożność!</a></article>
  <article><a href="/komunikaty/2026/208/falszywe-sklepy/">Fałszywe sklepy internetowe przed świętami</a></article>
  <a href="https://inna-domena.pl/komunikaty/x">Link do zupełnie innej domeny w treści</a>
  <a href="/komunikaty/raport.pdf">Raport roczny w formacie PDF do pobrania</a>
  <a href="#top">Powrót na górę strony serwisu</a>
</main>
<footer><a href="/komunikaty/kontakt-stopka">Kontakt z zespołem CERT Polska</a></footer>
</body></html>""".encode()


def test_parse_rss_and_atom() -> None:
    rss = parse_feed(RSS, "https://policja.pl/")
    assert rss is not None and len(rss) == 1
    assert rss[0].title == 'Uwaga na oszustów "na policjanta"'
    assert rss[0].snippet == "Oszuści dzwonią"
    assert rss[0].published_at is not None and rss[0].published_at.day == 20

    atom = parse_feed(ATOM, "https://moje.cert.pl/")
    assert atom is not None
    assert atom[0].url == "https://moje.cert.pl/komunikaty/1/"


def test_feed_parser_does_not_expand_external_entities() -> None:
    entries = parse_feed(XXE, "https://x.pl/")
    assert entries == [] or all("root:" not in entry.title for entry in entries)


def test_non_feed_returns_none() -> None:
    assert parse_feed(b"<html><body>nope</body></html>", "https://x.pl/") is None


def test_parse_sitemap_index_and_news_titles() -> None:
    index = parse_sitemap(SITEMAP_INDEX)
    assert index is not None and index.is_index
    assert index.entries[0].url.endswith("post-sitemap.xml")

    urlset = parse_sitemap(gzip.compress(URLSET))
    assert urlset is not None and not urlset.is_index
    assert [entry.title for entry in urlset.entries] == ["", "Sztorm na Bałtyku"]
    assert urlset.entries[1].published_at is not None


def test_gzip_bomb_is_rejected() -> None:
    bomb = gzip.compress(b"\0" * (11 * 1024 * 1024))
    with pytest.raises(ValueError):
        maybe_gunzip(bomb)


def test_listing_keeps_article_links_and_skips_navigation() -> None:
    page = parse_html(LISTING, "https://moje.cert.pl/komunikaty/", path_prefix="/komunikaty/")
    assert page.title == "CERT – komunikaty"
    assert page.description == "Komunikaty CERT Polska"
    assert page.feed_urls == ["https://moje.cert.pl/feed/"]
    urls = [link.url for link in page.links]
    assert urls == [
        "https://moje.cert.pl/komunikaty/2026/209/doplata-do-przesylki/",
        "https://moje.cert.pl/komunikaty/2026/208/falszywe-sklepy/",
    ]
    assert page.links[0].published_at is not None
