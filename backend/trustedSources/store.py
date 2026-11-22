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

from collections.abc import Sequence
from typing import Protocol

from .whitelist import WHITELIST, WhitelistEntry


class SourceStore(Protocol):
    def load(self) -> Sequence[WhitelistEntry]: ...


class StaticSourceStore:
    """Whitelist kept in code (``whitelist.py``)."""

    def __init__(self, entries: Sequence[WhitelistEntry] = WHITELIST):
        self._entries = tuple(entries)

    def load(self) -> Sequence[WhitelistEntry]:
        return self._entries
