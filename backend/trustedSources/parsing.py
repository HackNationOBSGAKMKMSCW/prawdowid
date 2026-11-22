"""Hardened parsers for feeds, sitemaps and listing pages of whitelisted sites."""

import contextlib
import re
import zlib
from dataclasses import dataclass, field
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from urllib.parse import urljoin, urlsplit

from lxml import etree, html

from .text import clean_snippet

MAX_DECOMPRESSED_BYTES = 10 * 1024 * 1024
MAX_ENTRIES = 5000
MAX_LINKS = 200
MIN_LINK_TEXT = 15

_XML_PARSER_KWARGS = {
    "resolve_entities": False,
    "no_network": True,
    "load_dtd": False,
    "huge_tree": False,
    "recover": True,
}
_NAV_HINT = re.compile(r"(^|[\s_-])(nav|menu|footer|header|breadcrumb|cookie|social|skip)", re.I)
_SKIP_SCHEMES = ("mailto:", "tel:", "javascript:", "#")
_SKIP_EXTENSIONS = (".pdf", ".jpg", ".jpeg", ".png", ".gif", ".zip", ".doc", ".docx", ".xls")


@dataclass(frozen=True)
class PageEntry:
    url: str
    title: str
    snippet: str = ""
    published_at: datetime | None = None


@dataclass
class HtmlPage:
    title: str = ""
    description: str = ""
    feed_urls: list[str] = field(default_factory=list)
    links: list[PageEntry] = field(default_factory=list)


def parse_date(value: str | None) -> datetime | None:
    if not value:
        return None
    text = value.strip()
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        try:
            parsed = parsedate_to_datetime(text)
        except (TypeError, ValueError, IndexError):
            return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def maybe_gunzip(body: bytes) -> bytes:
    """Decompress gzip bodies (``sitemap.xml.gz``) with a hard output limit."""

    if not body.startswith(b"\x1f\x8b"):
        return body
    decompressor = zlib.decompressobj(16 + zlib.MAX_WBITS)
    data = decompressor.decompress(body, MAX_DECOMPRESSED_BYTES)
    if decompressor.unconsumed_tail:
        raise ValueError("decompressed document exceeds the size limit")
    return data


def _xml_root(body: bytes) -> etree._Element | None:
    parser = etree.XMLParser(**_XML_PARSER_KWARGS)
    try:
        return etree.fromstring(maybe_gunzip(body), parser=parser)
    except (etree.XMLSyntaxError, ValueError):
        return None


def _local(tag: object) -> str:
    return etree.QName(tag).localname.lower() if isinstance(tag, str) else ""


def _child_text(element: etree._Element, *names: str) -> str:
    for child in element:
        if _local(child.tag) in names:
            return "".join(child.itertext()).strip()
    return ""


def parse_feed(body: bytes, base_url: str) -> list[PageEntry] | None:
    """RSS 2.0 / RSS 1.0 / Atom items, or ``None`` when ``body`` is not a feed."""

    root = _xml_root(body)
    if root is None or _local(root.tag) not in {"rss", "feed", "rdf"}:
        return None
    entries: list[PageEntry] = []
    for item in root.iter():
        name = _local(item.tag)
        if name not in {"item", "entry"}:
            continue
        link = _child_text(item, "link") if name == "item" else ""
        if not link:
            for child in item:
                if _local(child.tag) == "link" and child.get("rel", "alternate") == "alternate":
                    link = child.get("href", "")
                    break
        title = _child_text(item, "title")
        if not link or not title:
            continue
        entries.append(
            PageEntry(
                url=urljoin(base_url, link.strip()),
                title=clean_snippet(title, 300),
                snippet=clean_snippet(_child_text(item, "description", "summary", "content")),
                published_at=parse_date(_child_text(item, "pubdate", "published", "updated", "date")),
            )
        )
        if len(entries) >= MAX_ENTRIES:
            break
    return entries


@dataclass(frozen=True)
class SitemapDocument:
    is_index: bool
    entries: list[PageEntry]


def parse_sitemap(body: bytes) -> SitemapDocument | None:
    root = _xml_root(body)
    if root is None or _local(root.tag) not in {"urlset", "sitemapindex"}:
        return None
    is_index = _local(root.tag) == "sitemapindex"
    entries: list[PageEntry] = []
    for node in root:
        if _local(node.tag) not in {"url", "sitemap"}:
            continue
        loc = _child_text(node, "loc")
        if not loc:
            continue
        title = ""
        for descendant in node.iter():
            if _local(descendant.tag) == "title":
                title = "".join(descendant.itertext()).strip()
                break
        published = None
        for descendant in node.iter():
            if _local(descendant.tag) in {"publication_date", "lastmod"}:
                published = parse_date("".join(descendant.itertext()))
                if published:
                    break
        entries.append(PageEntry(url=loc, title=title, published_at=published))
        if len(entries) >= MAX_ENTRIES:
            break
    return SitemapDocument(is_index=is_index, entries=entries)


def _in_navigation(element: html.HtmlElement) -> bool:
    for ancestor in element.iterancestors():
        if ancestor.tag in {"nav", "header", "footer"}:
            return True
        marker = f"{ancestor.get('class', '')} {ancestor.get('id', '')} {ancestor.get('role', '')}"
        if _NAV_HINT.search(marker):
            return True
    return False


def _nearby_date(element: html.HtmlElement) -> datetime | None:
    for depth, ancestor in enumerate(element.iterancestors()):
        if depth > 3:
            break
        for node in ancestor.iter("time"):
            value = parse_date(node.get("datetime") or node.text_content())
            if value:
                return value
    return None


def _html_document(body: bytes, page_url: str) -> html.HtmlElement | None:
    """Parse HTML as UTF-8 when valid (lxml would assume Latin-1 without a meta charset),
    otherwise let lxml honour the page's own ``<meta charset>`` (e.g. windows-1250)."""

    attempts: list[bytes | str] = []
    with contextlib.suppress(UnicodeDecodeError):
        attempts.append(body.decode("utf-8"))
    attempts.append(body)
    for markup in attempts:
        try:
            return html.fromstring(markup, base_url=page_url)
        except (etree.ParserError, ValueError):
            continue
    return None


def parse_html(body: bytes, page_url: str, *, path_prefix: str = "/") -> HtmlPage:
    """Title, description, advertised feeds and article-like links of one page."""

    document = _html_document(body, page_url)
    if document is None:
        return HtmlPage()
    page = HtmlPage()
    title_node = document.find(".//title")
    if title_node is not None:
        page.title = clean_snippet(title_node.text_content(), 200)
    for meta in document.iter("meta"):
        if (meta.get("name") or meta.get("property") or "").lower() in {"description", "og:description"}:
            page.description = clean_snippet(meta.get("content"), 300)
            if page.description:
                break
    for link in document.iter("link"):
        kind = (link.get("type") or "").lower()
        if "alternate" in (link.get("rel") or "").lower() and kind in {
            "application/rss+xml",
            "application/atom+xml",
        }:
            href = link.get("href")
            if href:
                page.feed_urls.append(urljoin(page_url, href))

    page_parts = urlsplit(page_url)
    host = (page_parts.hostname or "").lower()
    prefix = path_prefix.rstrip("/") or ""
    scoped: dict[str, PageEntry] = {}
    loose: dict[str, PageEntry] = {}
    for anchor in document.iter("a"):
        href = (anchor.get("href") or "").strip()
        if not href or href.lower().startswith(_SKIP_SCHEMES):
            continue
        url = urljoin(page_url, href).split("#", 1)[0]
        parts = urlsplit(url)
        if (parts.hostname or "").lower() != host or parts.scheme not in {"http", "https"}:
            continue
        if parts.path.lower().endswith(_SKIP_EXTENSIONS) or parts.path.rstrip("/") == page_parts.path.rstrip("/"):
            continue
        text = clean_snippet(anchor.text_content() or anchor.get("title") or "", 300)
        if len(text) < MIN_LINK_TEXT or _in_navigation(anchor):
            continue
        entry = PageEntry(url=url, title=text, published_at=_nearby_date(anchor))
        depth = len([segment for segment in parts.path.split("/") if segment])
        if prefix and parts.path.startswith(f"{prefix}/"):
            scoped.setdefault(url, entry)
        elif depth >= 2 and len(text) >= 25:
            loose.setdefault(url, entry)
    chosen = scoped if len(scoped) >= 5 else {**scoped, **loose}
    page.links = list(chosen.values())[:MAX_LINKS]
    return page
