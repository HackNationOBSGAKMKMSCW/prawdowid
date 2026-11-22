"""Adapter registry: one adapter per *kind* of site, many sources per adapter.

To support a new kind of site, subclass ``SourceAdapter``, decorate it with
``@register_adapter("name")`` and import the module below. Sources in the
registry then refer to it by ``adapter: "name"``.
"""

from abc import ABC, abstractmethod
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import ClassVar, TypeVar

import httpx
from articleScraping.safe_http import SafeFetcher

from ..cache import TTLCache
from ..models import EvidenceHit, TrustedSource
from ..settings import TrustedSettings


@dataclass
class SearchContext:
    """Shared resources for one search run."""

    http: httpx.AsyncClient  # for fixed, trusted API hosts (gov.pl, Google)
    fetcher: SafeFetcher  # for arbitrary whitelisted pages (SSRF-safe)
    cache: TTLCache
    settings: TrustedSettings


class SourceAdapter(ABC):
    name: ClassVar[str]
    # Provider already ranks results against the claim; ranking uses relaxed coverage.
    server_ranked: ClassVar[bool] = False
    # Adapter keeps page content that ``warm()`` can prefetch into the cache.
    prefetchable: ClassVar[bool] = False

    @abstractmethod
    async def search(
        self,
        sources: Sequence[TrustedSource],
        queries: Sequence[str],
        ctx: SearchContext,
    ) -> list[EvidenceHit]:
        """Return raw (unranked) hits for all ``sources`` using this adapter."""

    async def prefetch(self, source: TrustedSource, ctx: SearchContext) -> None:  # noqa: B027
        """Warm the cache for ``source`` (no-op unless the adapter keeps page content)."""


ADAPTERS: dict[str, type[SourceAdapter]] = {}
_A = TypeVar("_A", bound=type[SourceAdapter])


def register_adapter(name: str) -> Callable[[_A], _A]:
    def decorator(cls: _A) -> _A:
        cls.name = name
        ADAPTERS[name] = cls
        return cls

    return decorator


def get_adapter(name: str) -> SourceAdapter | None:
    cls = ADAPTERS.get(name)
    return cls() if cls is not None else None


# Import built-in adapters so they register themselves.
from . import fact_check, feed, govpl, listing, reference, sitemap  # noqa: E402, F401

__all__ = ["ADAPTERS", "SearchContext", "SourceAdapter", "get_adapter", "register_adapter"]
