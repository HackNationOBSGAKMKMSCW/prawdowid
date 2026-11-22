"""Map the Diffbot article subset into the public scraping model."""

import unicodedata
from contextlib import suppress
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Literal
from urllib.parse import urlsplit

from .models import ScrapedArticle
from .protocols import RawArticle
from .url_validation import InvalidUrlError, site_key, validate_url

MAX_ARTICLE_CHARS = 50_000
MAX_TITLE_CHARS = 300
MAX_AUTHOR_CHARS = 200
MAX_DESCRIPTION_CHARS = 1000


def _clean_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value)
    return "".join(
        character
        for character in normalized
        if unicodedata.category(character) not in {"Cf", "Cs"}
        and (unicodedata.category(character) != "Cc" or character in "\n\r\t")
    ).strip()


def _published_at(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = parsedate_to_datetime(value)
    except (TypeError, ValueError, OverflowError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def map_article(
    url: str,
    article: RawArticle,
    source: Literal["fact_check", "trusted_source", "user_text"] | None = None,
    *,
    title: str | None = None,
    publisher: str | None = None,
) -> ScrapedArticle:
    """Create the public whitelist model and validate Diffbot's redirect output.

    ``title`` and ``publisher`` come from the link source and fill gaps in the page metadata.
    """

    text = _clean_text(article.text)
    if article.resolved_page_url or article.page_url:
        with suppress(InvalidUrlError):
            # The redirect is untrusted and is deliberately not exposed.
            validate_url(article.resolved_page_url or article.page_url or "")
    page_title = article.title or title
    return ScrapedArticle(
        url=url,
        site=site_key(url),
        title=_clean_text(page_title)[:MAX_TITLE_CHARS] or None if page_title else None,
        published_at=_published_at(article.date),
        text=text[:MAX_ARTICLE_CHARS],
        author=_clean_text(article.author)[:MAX_AUTHOR_CHARS] or None if article.author else None,
        publisher=_clean_text(publisher)[:MAX_AUTHOR_CHARS] or None if publisher else None,
        truncated=len(text) > MAX_ARTICLE_CHARS,
        domain=urlsplit(url).hostname,
        site_name=_clean_text(article.site_name)[:MAX_AUTHOR_CHARS] if article.site_name else None,
        description=(
            _clean_text(article.description)[:MAX_DESCRIPTION_CHARS]
            if article.description
            else None
        ),
        language=article.language[:35] if article.language else None,
        fetched_at=datetime.now(UTC),
        source=source,
    )
