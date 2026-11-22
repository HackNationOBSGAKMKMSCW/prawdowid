"""Where the whitelist comes from.

Today: the hardcoded ``WHITELIST``. Later: a PostgreSQL table. The registry only
needs ``load()``, so switching storage means writing one class, e.g.::

    class PostgresSourceStore:
        def __init__(self, dsn: str): ...
        def load(self) -> list[WhitelistEntry]:
            rows = conn.execute(
                "SELECT url, name, topics, description, adapter, enabled, params"
                " FROM trusted_sources"
            )
            return [WhitelistEntry(**row) for row in rows]

and passing it to ``SourceRegistry(store=...)``.
"""

import logging
import os
from collections.abc import Sequence
from typing import Protocol

from .whitelist import WHITELIST, WhitelistEntry

logger = logging.getLogger(__name__)


class SourceStore(Protocol):
    def load(self) -> Sequence[WhitelistEntry]: ...


class StaticSourceStore:
    """Whitelist kept in code (``whitelist.py``)."""

    def __init__(self, entries: Sequence[WhitelistEntry] = WHITELIST):
        self._entries = tuple(entries)

    def load(self) -> Sequence[WhitelistEntry]:
        return self._entries


class FallbackSourceStore:
    """Primary store (the database) with a safety net.

    If the database is unreachable or the table is empty, the last good list is
    kept, and before the first success the hardcoded ``WHITELIST`` is used, so
    fact-checking never runs without trusted sources.
    """

    def __init__(self, primary: SourceStore, fallback: SourceStore | None = None):
        self._primary = primary
        self._fallback = fallback or StaticSourceStore()
        self._last_good: Sequence[WhitelistEntry] | None = None

    def load(self) -> Sequence[WhitelistEntry]:
        try:
            entries = self._primary.load()
        except Exception as exc:  # noqa: BLE001 - any database failure falls back
            logger.warning("trusted_sources: baza niedostępna (%s)", type(exc).__name__)
            entries = None
        if entries:
            self._last_good = tuple(entries)
            return self._last_good
        return self._last_good or self._fallback.load()


def default_store() -> SourceStore:
    """The ``trusted_sources`` table when ``DATABASE_URL`` is set, else the code list.

    ``TRUSTED_SOURCES_STORE=static`` forces the hardcoded list.
    """

    if os.getenv("TRUSTED_SOURCES_STORE", "").strip().lower() == "static":
        return StaticSourceStore()
    try:
        from accounts.trusted import PostgresSourceStore
        from database import database_url, get_database

        if not database_url():
            return StaticSourceStore()
        return FallbackSourceStore(PostgresSourceStore(get_database()))
    except Exception as exc:  # noqa: BLE001 - missing driver or bad URL: keep working
        logger.warning("trusted_sources: używam listy z kodu (%s)", type(exc).__name__)
        return StaticSourceStore()
