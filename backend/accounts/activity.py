"""Dziennik działań w aplikacji (tabela ``activity_logs``)."""

from __future__ import annotations

import ipaddress
import json
from dataclasses import dataclass
from typing import Any

from database import Database


@dataclass(frozen=True)
class Actor:
    """Kto wykonuje działanie: konto, token serwisowy panelu albo sam system."""

    label: str
    user_id: int | None = None
    ip: str | None = None
    user_agent: str | None = None

    @classmethod
    def system(cls) -> Actor:
        return cls("system")


def normalize_ip(value: str | None) -> str | None:
    if not value:
        return None
    try:
        return str(ipaddress.ip_address(value.strip()))
    except ValueError:
        return None


class ActivityLog:
    def __init__(self, db: Database) -> None:
        self.db = db

    def record(
        self,
        action: str,
        actor: Actor,
        *,
        subject_type: str | None = None,
        subject_id: str | int | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.db.execute(
            "INSERT INTO activity_logs "
            "(user_id, actor, action, subject_type, subject_id, details, ip_address, user_agent) "
            "VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s, %s)",
            [
                actor.user_id,
                actor.label[:255],
                action[:100],
                subject_type,
                None if subject_id is None else str(subject_id)[:255],
                json.dumps(details or {}, ensure_ascii=False, default=str),
                normalize_ip(actor.ip),
                (actor.user_agent or "")[:255] or None,
            ],
        )

    def list(
        self,
        *,
        action: str | None = None,
        user_id: int | None = None,
        subject_type: str | None = None,
        subject_id: str | None = None,
        since: str | None = None,
        until: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[dict[str, Any]], int]:
        where, params = [], []
        if action:
            # "auth." pokazuje całą grupę działań
            if action.endswith("."):
                where.append("action LIKE %s")
                params.append(action.replace("%", "") + "%")
            else:
                where.append("action = %s")
                params.append(action)
        if user_id is not None:
            where.append("user_id = %s")
            params.append(user_id)
        if subject_type:
            where.append("subject_type = %s")
            params.append(subject_type)
        if subject_id:
            where.append("subject_id = %s")
            params.append(subject_id)
        if since:
            where.append("occurred_at >= %s")
            params.append(since)
        if until:
            where.append("occurred_at < %s")
            params.append(until)
        clause = f"WHERE {' AND '.join(where)}" if where else ""
        total = self.db.fetch_value(f"SELECT COUNT(*) FROM activity_logs {clause}", params)
        rows = self.db.fetch_all(
            "SELECT id, occurred_at, user_id, actor, action, subject_type, subject_id, details, "
            f"host(ip_address) AS ip_address, user_agent FROM activity_logs {clause} "
            "ORDER BY occurred_at DESC, id DESC LIMIT %s OFFSET %s",
            [*params, limit, offset],
        )
        return [dict(row) for row in rows], int(total or 0)

    def count_since(
        self, action: str, since: str, *, subject_id: str | None = None, ip: str | None = None
    ) -> int:
        """Zdarzenia ``action`` od ``since``, opcjonalnie dla obiektu i/lub adresu IP."""
        sql = "SELECT COUNT(*) FROM activity_logs WHERE action = %s AND occurred_at >= %s"
        params: list[Any] = [action, since]
        if subject_id is not None:
            sql += " AND subject_id = %s"
            params.append(subject_id)
        if ip is not None:
            sql += " AND ip_address = %s::inet"
            params.append(ip)
        return int(self.db.fetch_value(sql, params) or 0)

    def count_recent(self, action: str, subject_id: str, since: str) -> int:
        return int(
            self.db.fetch_value(
                "SELECT COUNT(*) FROM activity_logs WHERE action = %s AND subject_id = %s "
                "AND occurred_at >= %s",
                [action, subject_id, since],
            )
            or 0
        )
