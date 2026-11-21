"""Map the Diffbot article subset into the public scraping model."""

import unicodedata
from contextlib import suppress
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Literal

from .models import ScrapedArticle
from .protocols import RawArticle
from .url_validation import InvalidUrlError, validate_url

MAX_ARTICLE_CHARS = 50_000
MAX_TITLE_CHARS = 300
MAX_AUTHOR_CHARS = 200


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
    source: Literal["fact_check", "user_text"] | None = None,
) -> ScrapedArticle:
    """Create the public whitelist model and validate Diffbot's redirect output."""

    text = _clean_text(article.text)
    if article.resolved_page_url or article.page_url:
        with suppress(InvalidUrlError):
            # The redirect is untrusted and is deliberately not exposed.
            validate_url(article.resolved_page_url or article.page_url or "")
    return ScrapedArticle(
        url=url,
        title=_clean_text(article.title)[:MAX_TITLE_CHARS] if article.title else None,
        author=_clean_text(article.author)[:MAX_AUTHOR_CHARS] if article.author else None,
        published_at=_published_at(article.date),
        text=text[:MAX_ARTICLE_CHARS],
        truncated=len(text) > MAX_ARTICLE_CHARS,
        source=source,
    )
