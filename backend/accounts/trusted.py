"""Lista stron zaufanych w bazie (tabela ``trusted_sources``).

``TrustedSourceRepository`` obsługuje panel (dodawanie, edycja, wyłączanie), a
``PostgresSourceStore`` zasila moduł ``trustedSources`` (``SourceRegistry(store=...)``)
— rejestr przeładowuje listę co kilka minut, więc zmiany z panelu działają bez restartu.
"""

from __future__ import annotations

import json
import re
from collections.abc import Sequence
from typing import Any

from database import Database
from psycopg import errors

from .activity import ActivityLog, Actor

_COLUMNS = (
    "url, name, topics, description, adapter, params, enabled, created_at, updated_at, updated_by"
)
_EDITABLE = ("name", "topics", "description", "adapter", "params", "enabled")
_URL = re.compile(r"^https?://[^\s/]+\.[^\s]+$", re.IGNORECASE)


class SourceError(ValueError):
    pass


def _clean(fields: dict[str, Any]) -> dict[str, Any]:
    clean: dict[str, Any] = {}
    for key, value in fields.items():
        if key not in _EDITABLE:
            raise SourceError(f"Nieznane pole źródła: {key}.")
        if key == "name":
            value = " ".join(str(value or "").split())
            if not 1 <= len(value) <= 200:
                raise SourceError("Nazwa źródła: od 1 do 200 znaków.")
        elif key == "topics":
            value = sorted({str(t).strip() for t in value or () if str(t).strip()})[:50]
        elif key == "description":
            value = str(value or "")[:2000]
        elif key == "adapter":
            value = (str(value).strip() or None) if value is not None else None
        elif key == "params":
            if not isinstance(value, dict):
                raise SourceError("params musi być obiektem JSON.")
            value = json.dumps(value, ensure_ascii=False)
        elif key == "enabled":
            value = bool(value)
        clean[key] = value
    return clean


def _validate_url(url: str) -> str:
    url = (url or "").strip()
    if not _URL.match(url) or len(url) > 2000:
        raise SourceError("Adres źródła musi zaczynać się od http:// lub https://.")
    return url


class TrustedSourceRepository:
    def __init__(self, db: Database, activity: ActivityLog | None = None) -> None:
        self.db = db
        self.activity = activity or ActivityLog(db)

    def list(self, *, enabled_only: bool = False) -> list[dict[str, Any]]:
        where = "WHERE enabled" if enabled_only else ""
        return [
            dict(row)
            for row in self.db.fetch_all(
                f"SELECT {_COLUMNS} FROM trusted_sources {where} ORDER BY name"
            )
        ]

    def get(self, url: str) -> dict[str, Any] | None:
        row = self.db.fetch_one(f"SELECT {_COLUMNS} FROM trusted_sources WHERE url = %s", [url])
        return dict(row) if row else None

    def create(self, url: str, fields: dict[str, Any], *, actor: Actor) -> dict[str, Any]:
        url = _validate_url(url)
        clean = _clean({"enabled": True, **fields})
        if "name" not in clean:
            raise SourceError("Podaj nazwę źródła.")
        columns = ["url", *clean, "updated_by"]
        values = [url, *clean.values(), actor.user_id]
        marks = ", ".join("%s::jsonb" if c == "params" else "%s" for c in columns)
        try:
            row = self.db.fetch_one(
                f"INSERT INTO trusted_sources ({', '.join(columns)}) VALUES ({marks}) "
                f"RETURNING {_COLUMNS}",
                values,
            )
        except errors.UniqueViolation:
            raise SourceError("To źródło już jest na liście.") from None
        self.activity.record(
            "source.created",
            actor,
            subject_type="trusted_source",
            subject_id=url,
            details={"name": row["name"]},
        )
        return dict(row)

    def update(self, url: str, fields: dict[str, Any], *, actor: Actor) -> dict[str, Any]:
        before = self.get(url)
        if before is None:
            raise KeyError(url)
        clean = _clean(fields)
        if not clean:
            return before
        assignments = ", ".join(f"{c} = %s::jsonb" if c == "params" else f"{c} = %s" for c in clean)
        row = self.db.fetch_one(
            f"UPDATE trusted_sources SET {assignments}, updated_at = now(), updated_by = %s "
            f"WHERE url = %s RETURNING {_COLUMNS}",
            [*clean.values(), actor.user_id, url],
        )
        changed = {k: {"old": before[k], "new": row[k]} for k in clean if before[k] != row[k]}
        if changed:
            self.activity.record(
                "source.updated",
                actor,
                subject_type="trusted_source",
                subject_id=url,
                details=changed,
            )
        return dict(row)

    def delete(self, url: str, *, actor: Actor) -> None:
        source = self.get(url)
        if source is None:
            raise KeyError(url)
        self.db.execute("DELETE FROM trusted_sources WHERE url = %s", [url])
        self.activity.record(
            "source.deleted",
            actor,
            subject_type="trusted_source",
            subject_id=url,
            details={"name": source["name"]},
        )

    def seed(self, entries: Sequence[Any], *, actor: Actor | None = None) -> int:
        """Wgraj listę z kodu (``trustedSources.whitelist.WHITELIST``); istniejących nie zmienia."""
        added = 0
        with self.db.transaction() as cursor:
            for entry in entries:
                cursor.execute(
                    "INSERT INTO trusted_sources (url, name, topics, description, adapter, params, "
                    "enabled) VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s) ON CONFLICT (url) DO NOTHING",
                    [
                        entry.url,
                        entry.name,
                        list(entry.topics),
                        entry.description,
                        entry.adapter,
                        json.dumps(dict(entry.params), ensure_ascii=False),
                        entry.enabled,
                    ],
                )
                added += cursor.rowcount
        if added:
            self.activity.record(
                "source.seeded",
                actor or Actor.system(),
                subject_type="trusted_source",
                details={"added": added},
            )
        return added


class PostgresSourceStore:
    """``SourceStore`` dla ``trustedSources.registry.SourceRegistry``: lista z tabeli."""

    def __init__(self, db: Database) -> None:
        self.db = db

    def load(self) -> list[Any]:
        from trustedSources.whitelist import WhitelistEntry

        rows = self.db.fetch_all(
            "SELECT url, name, topics, description, adapter, enabled, params FROM trusted_sources "
            "ORDER BY name"
        )
        return [
            WhitelistEntry(
                url=row["url"],
                name=row["name"],
                topics=tuple(row["topics"] or ()),
                description=row["description"] or "",
                adapter=row["adapter"],
                enabled=row["enabled"],
                params=dict(row["params"] or {}),
            )
            for row in rows
        ]
