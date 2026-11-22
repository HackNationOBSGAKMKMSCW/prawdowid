"""Public, token-safe data models for the article extraction stage."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel

LinkOrigin = Literal["fact_check", "trusted_source", "user_text"]
SourceLinkKind = Literal["fact_check", "trusted_source", "trusted_reference", "user_text"]
SourceLinkStatus = Literal["scraped", "failed", "not_scraped", "reference"]

# Evidence must come from at least this many different sites (see ``site_key``).
MIN_DISTINCT_SITES = 2


class ScrapedArticle(BaseModel):
    """One downloaded article: metadata and the full extracted body."""

    url: str
    site: str = ""
    title: str | None = None
    published_at: datetime | None = None
    text: str
    # Byline found in the page; ``publisher`` is the institution or newsroom behind the site.
    author: str | None = None
    publisher: str | None = None
    truncated: bool = False
    source: LinkOrigin | None = None


class SourceLink(BaseModel):
    """Every link found for the claim, scraped or not."""

    url: str
    site: str
    kind: SourceLinkKind
    title: str | None = None
    publisher: str | None = None
    status: SourceLinkStatus


class ArticleFailure(BaseModel):
    """A safe per-link failure without an exception, request, or credential."""

    url: str
    kind: str
    status_code: int | None = None
    source: LinkOrigin | None = None


class ScrapingReport(BaseModel):
    """Final structured output: the user's request plus the evidence downloaded for it."""

    submitted_at: datetime
    user_input: str
    articles: list[ScrapedArticle]
    sources: list[SourceLink]
    distinct_sites: int
    min_sites_met: bool
    failures: list[ArticleFailure]
    finished_at: datetime

    # Older names of the first two fields.
    @property
    def started_at(self) -> datetime:
        return self.submitted_at

    @property
    def user_text(self) -> str:
        return self.user_input
