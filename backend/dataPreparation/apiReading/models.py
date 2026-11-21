"""Normalized response models shared by all API clients."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

from .exceptions import ApiReadingError


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
