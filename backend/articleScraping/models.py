"""Public, token-safe data models for the article extraction stage."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class ScrapedArticle(BaseModel):
    """An extracted article body and a small, explicitly selected metadata set."""

    url: str
    title: str | None = None
    author: str | None = None
    published_at: datetime | None = None
    text: str
    truncated: bool = False
    source: Literal["fact_check", "user_text"] | None = None


class ArticleFailure(BaseModel):
    """A safe per-link failure without an exception, request, or credential."""

    url: str
    kind: str
    status_code: int | None = None
    source: Literal["fact_check", "user_text"] | None = None


class ScrapingReport(BaseModel):
    """Final output of the article scraping stage, in stable serialized order."""

    started_at: datetime
    user_text: str
    articles: list[ScrapedArticle]
    failures: list[ArticleFailure]
    finished_at: datetime
