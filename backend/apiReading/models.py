"""Normalized response models shared by all API clients."""

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_serializer, field_validator

from .exceptions import ApiReadingError


class Category(StrEnum):
    """Kinds of information the reader can search for or process internally."""

    FACT_CHECK = "fact_check"
    ARTICLE_EXTRACT = "article_extract"  # Internal client contract; no reader registry source.
    LEGAL_ACT = "legal_act"
    LEGISLATIVE_PROCESS = "legislative_process"
    OPEN_DATA = "open_data"
    NEWS = "news"
    OFFICIAL = "official"  # Whitelisted official sites; used by trustedSources, not the reader.


class ReadingRequest(BaseModel):
    """Provider-neutral input for a category-driven read."""

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
        revalidate_instances="always",
    )

    # Query text is sent to external providers; callers should avoid including sensitive data.
    query: str = Field(strict=True)
    categories: list[Category]
    language_code: str | None = None
    max_age_days: int | None = Field(default=None, strict=True, ge=1)
    page_size: int = Field(default=10, strict=True, ge=1)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("query")
    @classmethod
    def query_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("query must not be empty")
        return value

    @field_validator("categories")
    @classmethod
    def categories_must_be_nonempty_and_unique(cls, value: list[Category]) -> list[Category]:
        if not value:
            raise ValueError("at least one category is required")
        if len(value) != len(set(value)):
            raise ValueError("categories must not contain duplicates")
        return value

    @field_validator("language_code")
    @classmethod
    def language_code_must_not_be_blank(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("language_code must not be empty")
        return value


class Item(BaseModel):
    """A normalized item with its original API fields preserved."""

    id: str
    source: str
    payload: dict[str, Any]


class FetchResult(BaseModel):
    """Items returned by one API fetch and optional pagination metadata."""

    source: str
    items: list[Item]
    fetched_at: datetime
    total: int | None = None
    next_cursor: str | None = None


class FetchOutcome(BaseModel):
    """One client's success or failure in a multi-API fetch."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    source: str
    result: FetchResult | None = None
    error: ApiReadingError | None = None

    @field_serializer("error")
    def serialize_error(self, error: ApiReadingError | None) -> dict[str, Any] | None:
        if error is None:
            return None
        return {
            "type": type(error).__name__,
            "source": error.source,
            "message": str(error),
            "status_code": error.status_code,
        }


class ReadingResult(BaseModel):
    """Aggregated output for a single provider-neutral read request."""

    request: ReadingRequest
    results: list[FetchOutcome]
    items: list[Item]
    categories_without_source: list[Category]
    fetched_at: datetime
    duration_ms: int
