"""Trwały rejestr panelu admina w SQLite (stdlib, jeden plik, tryb WAL).

Tabele: ``queries`` (zapytania użytkowników), ``claims`` (twierdzenia z werdyktem i
tematem), ``topics`` (grupy podobnych twierdzeń + stan luki informacyjnej), ``users``
(pseudonimy, liczniki, blokady), ``alerts`` (zdarzenia dla admina), ``config_audit``.
"""

from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from collections.abc import Iterable
from pathlib import Path
from typing import Any

SCHEMA = """
CREATE TABLE IF NOT EXISTS queries (
    id TEXT PRIMARY KEY,
    ts TEXT NOT NULL,
    user_key TEXT NOT NULL,
    user_label TEXT,
    channel TEXT,
    text TEXT,
    text_sha TEXT,
    status TEXT NOT NULL,
    verdict TEXT,
    flags TEXT NOT NULL DEFAULT '[]',
    safety TEXT,
    request_id TEXT,
    sources_count INTEGER,
    completed_at TEXT,
    error TEXT
);
CREATE INDEX IF NOT EXISTS ix_queries_ts ON queries(ts);
CREATE INDEX IF NOT EXISTS ix_queries_user ON queries(user_key, ts);

CREATE TABLE IF NOT EXISTS claims (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    query_id TEXT NOT NULL,
    ts TEXT NOT NULL,
    user_key TEXT NOT NULL,
    topic_id TEXT NOT NULL,
    text TEXT NOT NULL,
    verdict TEXT,
    kind TEXT NOT NULL,
    sources_count INTEGER
);
CREATE INDEX IF NOT EXISTS ix_claims_topic ON claims(topic_id, kind, ts);
CREATE INDEX IF NOT EXISTS ix_claims_query ON claims(query_id);

CREATE TABLE IF NOT EXISTS topics (
    id TEXT PRIMARY KEY,
    label TEXT NOT NULL,
    tokens TEXT NOT NULL,
    created_at TEXT NOT NULL,
    last_seen TEXT NOT NULL,
    gap_status TEXT NOT NULL DEFAULT 'brak',
    gap_since TEXT,
    gap_users INTEGER NOT NULL DEFAULT 0,
    gap_note TEXT,
    gap_updated_at TEXT
);
CREATE INDEX IF NOT EXISTS ix_topics_seen ON topics(last_seen);

CREATE TABLE IF NOT EXISTS users (
    user_key TEXT PRIMARY KEY,
    label TEXT,
    first_seen TEXT NOT NULL,
    last_seen TEXT NOT NULL,
    queries INTEGER NOT NULL DEFAULT 0,
    dangerous INTEGER NOT NULL DEFAULT 0,
    blocked_until TEXT,
    block_reason TEXT
);

CREATE TABLE IF NOT EXISTS alerts (
    id TEXT PRIMARY KEY,
    type TEXT NOT NULL,
    subject TEXT NOT NULL,
    severity TEXT NOT NULL,
    status TEXT NOT NULL,
    title TEXT NOT NULL,
    count INTEGER NOT NULL DEFAULT 0,
    users INTEGER NOT NULL DEFAULT 0,
    first_seen TEXT NOT NULL,
    last_seen TEXT NOT NULL,
    details TEXT NOT NULL DEFAULT '{}',
    note TEXT,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_alerts_open ON alerts(type, subject, status);

CREATE TABLE IF NOT EXISTS config_audit (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    actor TEXT NOT NULL,
    field TEXT NOT NULL,
    old TEXT,
    new TEXT
);
"""

OPEN_ALERT_STATUSES = ("otwarty", "w_analizie")


def new_id() -> str:
    return uuid.uuid4().hex[:12]


def _row(row: sqlite3.Row | None, json_fields: Iterable[str] = ()) -> dict[str, Any] | None:
    if row is None:
        return None
    data = dict(row)
    for name in json_fields:
        if data.get(name) is not None:
            data[name] = json.loads(data[name])
    return data


class AdminStore:
    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        if str(path) != ":memory:":
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._db = sqlite3.connect(str(path), check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        with self._lock:
            if str(path) != ":memory:":
                self._db.execute("PRAGMA journal_mode=WAL")
            self._db.executescript(SCHEMA)
            self._db.commit()

    def close(self) -> None:
        with self._lock:
            self._db.close()

    def _execute(self, sql: str, params: Iterable[Any] = ()) -> sqlite3.Cursor:
        with self._lock:
            cursor = self._db.execute(sql, tuple(params))
            self._db.commit()
            return cursor

    def _all(self, sql: str, params: Iterable[Any] = ()) -> list[sqlite3.Row]:
        with self._lock:
            return self._db.execute(sql, tuple(params)).fetchall()

    def _one(self, sql: str, params: Iterable[Any] = ()) -> sqlite3.Row | None:
        with self._lock:
            return self._db.execute(sql, tuple(params)).fetchone()

    # --- zapytania ---------------------------------------------------------------------

    def insert_query(self, **fields: Any) -> None:
        for name in ("flags", "safety"):
            if name in fields and not isinstance(fields[name], str):
                fields[name] = json.dumps(fields[name], ensure_ascii=False)
        names = ", ".join(fields)
        marks = ", ".join("?" for _ in fields)
        self._execute(f"INSERT INTO queries ({names}) VALUES ({marks})", fields.values())

    def update_query(self, query_id: str, **fields: Any) -> None:
        if "flags" in fields:
            fields["flags"] = json.dumps(sorted(set(fields["flags"])), ensure_ascii=False)
        assignments = ", ".join(f"{name} = ?" for name in fields)
        self._execute(
            f"UPDATE queries SET {assignments} WHERE id = ?", [*fields.values(), query_id]
        )

    def get_query(self, query_id: str) -> dict[str, Any] | None:
        query = _row(
            self._one("SELECT * FROM queries WHERE id = ?", [query_id]), ("flags", "safety")
        )
        if query is not None:
            query["claims"] = [
                dict(row)
                for row in self._all(
                    "SELECT id, topic_id, text, verdict, kind, sources_count FROM claims "
                    "WHERE query_id = ? ORDER BY id",
                    [query_id],
                )
            ]
        return query

    def list_queries(
        self,
        *,
        user_key: str | None = None,
        flag: str | None = None,
        verdict: str | None = None,
        status: str | None = None,
        since: str | None = None,
        until: str | None = None,
        search: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[dict[str, Any]], int]:
        where, params = [], []
        if user_key:
            where.append("user_key = ?")
            params.append(user_key)
        if flag:
            where.append("EXISTS (SELECT 1 FROM json_each(queries.flags) WHERE value LIKE ?)")
            params.append(f"{flag}%")
        if verdict:
            where.append("verdict = ?")
            params.append(verdict)
        if status:
            where.append("status = ?")
            params.append(status)
        if since:
            where.append("ts >= ?")
            params.append(since)
        if until:
            where.append("ts < ?")
            params.append(until)
        if search:
            where.append("text LIKE ? ESCAPE '\\'")
            escaped = search.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            params.append(f"%{escaped}%")
        clause = f"WHERE {' AND '.join(where)}" if where else ""
        total = self._one(f"SELECT COUNT(*) FROM queries {clause}", params)[0]
        rows = self._all(
            f"SELECT * FROM queries {clause} ORDER BY ts DESC LIMIT ? OFFSET ?",
            [*params, limit, offset],
        )
        return [_row(row, ("flags", "safety")) for row in rows], total

    # --- twierdzenia i tematy ----------------------------------------------------------

    def insert_claim(self, **fields: Any) -> None:
        names = ", ".join(fields)
        marks = ", ".join("?" for _ in fields)
        self._execute(f"INSERT INTO claims ({names}) VALUES ({marks})", fields.values())

    def recent_topics(self, since: str, limit: int = 5000) -> list[tuple[str, frozenset[str]]]:
        rows = self._all(
            "SELECT id, tokens FROM topics WHERE last_seen >= ? ORDER BY last_seen DESC LIMIT ?",
            [since, limit],
        )
        return [(row["id"], frozenset(json.loads(row["tokens"]))) for row in rows]

    def create_topic(self, *, label: str, tokens: frozenset[str], ts: str) -> str:
        topic_id = new_id()
        self._execute(
            "INSERT INTO topics (id, label, tokens, created_at, last_seen) VALUES (?, ?, ?, ?, ?)",
            [topic_id, label[:300], json.dumps(sorted(tokens)), ts, ts],
        )
        return topic_id

    def touch_topic(self, topic_id: str, ts: str) -> None:
        self._execute("UPDATE topics SET last_seen = ? WHERE id = ?", [ts, topic_id])

    def topic_row(self, topic_id: str) -> dict[str, Any] | None:
        return _row(self._one("SELECT * FROM topics WHERE id = ?", [topic_id]), ("tokens",))

    def get_topic(self, topic_id: str) -> dict[str, Any] | None:
        topic = _row(self._one("SELECT * FROM topics WHERE id = ?", [topic_id]), ("tokens",))
        if topic is not None:
            topic["claims"] = [
                dict(row)
                for row in self._all(
                    "SELECT query_id, ts, user_key, text, verdict, kind, sources_count "
                    "FROM claims WHERE topic_id = ? ORDER BY ts DESC LIMIT 200",
                    [topic_id],
                )
            ]
            topic["by_kind"] = {
                row["kind"]: {"claims": row["n"], "users": row["users"]}
                for row in self._all(
                    "SELECT kind, COUNT(*) AS n, COUNT(DISTINCT user_key) AS users "
                    "FROM claims WHERE topic_id = ? GROUP BY kind",
                    [topic_id],
                )
            }
        return topic

    def set_gap(self, topic_id: str, **fields: Any) -> None:
        assignments = ", ".join(f"{name} = ?" for name in fields)
        self._execute(f"UPDATE topics SET {assignments} WHERE id = ?", [*fields.values(), topic_id])

    def list_gaps(
        self, statuses: Iterable[str], limit: int = 100, offset: int = 0
    ) -> list[dict[str, Any]]:
        statuses = list(statuses)
        marks = ", ".join("?" for _ in statuses)
        rows = self._all(
            f"SELECT id, label, created_at, last_seen, gap_status, gap_since, gap_users, gap_note, "
            f"gap_updated_at FROM topics WHERE gap_status IN ({marks}) "
            f"ORDER BY gap_users DESC, last_seen DESC LIMIT ? OFFSET ?",
            [*statuses, limit, offset],
        )
        return [dict(row) for row in rows]

    def distinct_users(self, topic_id: str, kind: str, since: str) -> int:
        row = self._one(
            "SELECT COUNT(DISTINCT user_key) FROM claims WHERE topic_id = ? AND kind = ? "
            "AND ts >= ?",
            [topic_id, kind, since],
        )
        return int(row[0])

    def claim_count(self, topic_id: str, kind: str, since: str) -> int:
        row = self._one(
            "SELECT COUNT(*) FROM claims WHERE topic_id = ? AND kind = ? AND ts >= ?",
            [topic_id, kind, since],
        )
        return int(row[0])

    # --- użytkownicy -------------------------------------------------------------------

    def touch_user(self, user_key: str, label: str, ts: str, *, dangerous: bool) -> None:
        self._execute(
            "INSERT INTO users (user_key, label, first_seen, last_seen, queries, dangerous) "
            "VALUES (?, ?, ?, ?, 1, ?) ON CONFLICT(user_key) DO UPDATE SET "
            "last_seen = excluded.last_seen, queries = queries + 1, "
            "dangerous = dangerous + excluded.dangerous",
            [user_key, label, ts, ts, int(dangerous)],
        )

    def get_user(self, user_key: str) -> dict[str, Any] | None:
        return _row(self._one("SELECT * FROM users WHERE user_key = ?", [user_key]))

    def list_users(
        self, *, flagged: bool = False, blocked_at: str | None = None, limit: int = 100
    ) -> list[dict[str, Any]]:
        where = []
        params: list[Any] = []
        if flagged:
            where.append("dangerous > 0")
        if blocked_at:
            where.append("blocked_until > ?")
            params.append(blocked_at)
        clause = f"WHERE {' AND '.join(where)}" if where else ""
        rows = self._all(
            f"SELECT * FROM users {clause} ORDER BY dangerous DESC, last_seen DESC LIMIT ?",
            [*params, limit],
        )
        return [dict(row) for row in rows]

    def set_block(self, user_key: str, until: str | None, reason: str | None) -> None:
        self._execute(
            "UPDATE users SET blocked_until = ?, block_reason = ? WHERE user_key = ?",
            [until, reason, user_key],
        )

    def dangerous_count(self, user_key: str, since: str, *, severity: str | None = None) -> int:
        sql = (
            "SELECT COUNT(*) FROM queries WHERE user_key = ? AND ts >= ? "
            "AND json_extract(safety, '$.severity') {op}"
        )
        if severity:
            row = self._one(sql.format(op="= ?"), [user_key, since, severity])
        else:
            row = self._one(sql.format(op="IN ('sredni', 'wysoki')"), [user_key, since])
        return int(row[0])

    # --- alerty ------------------------------------------------------------------------

    def open_alert(self, alert_type: str, subject: str) -> dict[str, Any] | None:
        return _row(
            self._one(
                "SELECT * FROM alerts WHERE type = ? AND subject = ? AND status IN (?, ?) "
                "ORDER BY first_seen DESC LIMIT 1",
                [alert_type, subject, *OPEN_ALERT_STATUSES],
            ),
            ("details",),
        )

    def create_alert(self, **fields: Any) -> str:
        fields.setdefault("id", new_id())
        fields["details"] = json.dumps(fields.get("details") or {}, ensure_ascii=False)
        names = ", ".join(fields)
        marks = ", ".join("?" for _ in fields)
        self._execute(f"INSERT INTO alerts ({names}) VALUES ({marks})", fields.values())
        return fields["id"]

    def update_alert(self, alert_id: str, **fields: Any) -> None:
        if "details" in fields:
            fields["details"] = json.dumps(fields["details"], ensure_ascii=False)
        assignments = ", ".join(f"{name} = ?" for name in fields)
        self._execute(f"UPDATE alerts SET {assignments} WHERE id = ?", [*fields.values(), alert_id])

    def get_alert(self, alert_id: str) -> dict[str, Any] | None:
        return _row(self._one("SELECT * FROM alerts WHERE id = ?", [alert_id]), ("details",))

    def list_alerts(
        self,
        *,
        alert_type: str | None = None,
        status: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        where, params = [], []
        if alert_type:
            where.append("type = ?")
            params.append(alert_type)
        if status:
            where.append("status = ?")
            params.append(status)
        clause = f"WHERE {' AND '.join(where)}" if where else ""
        rows = self._all(
            f"SELECT * FROM alerts {clause} ORDER BY last_seen DESC LIMIT ? OFFSET ?",
            [*params, limit, offset],
        )
        return [_row(row, ("details",)) for row in rows]

    # --- audyt i statystyki ------------------------------------------------------------

    def add_audit(self, ts: str, actor: str, changes: list[dict[str, Any]]) -> None:
        for change in changes:
            self._execute(
                "INSERT INTO config_audit (ts, actor, field, old, new) VALUES (?, ?, ?, ?, ?)",
                [
                    ts,
                    actor,
                    change["field"],
                    json.dumps(change["old"], ensure_ascii=False),
                    json.dumps(change["new"], ensure_ascii=False),
                ],
            )

    def list_audit(self, limit: int = 100) -> list[dict[str, Any]]:
        rows = self._all("SELECT * FROM config_audit ORDER BY id DESC LIMIT ?", [limit])
        return [_row(row, ("old", "new")) for row in rows]

    def stats(self, since: str, now: str) -> dict[str, Any]:
        def scalar(sql: str, params: Iterable[Any] = ()) -> int:
            return int(self._one(sql, params)[0])

        verdicts = {
            row["verdict"] or "brak": row["n"]
            for row in self._all(
                "SELECT verdict, COUNT(*) AS n FROM queries WHERE ts >= ? GROUP BY verdict",
                [since],
            )
        }
        statuses = {
            row["status"]: row["n"]
            for row in self._all(
                "SELECT status, COUNT(*) AS n FROM queries WHERE ts >= ? GROUP BY status", [since]
            )
        }
        open_alerts = {
            row["type"]: row["n"]
            for row in self._all(
                "SELECT type, COUNT(*) AS n FROM alerts WHERE status IN (?, ?) GROUP BY type",
                OPEN_ALERT_STATUSES,
            )
        }
        return {
            "queries": scalar("SELECT COUNT(*) FROM queries WHERE ts >= ?", [since]),
            "users": scalar("SELECT COUNT(DISTINCT user_key) FROM queries WHERE ts >= ?", [since]),
            "dangerous_queries": scalar(
                "SELECT COUNT(*) FROM queries WHERE ts >= ? "
                "AND json_extract(safety, '$.severity') IN ('sredni', 'wysoki')",
                [since],
            ),
            "verdicts": verdicts,
            "statuses": statuses,
            "open_alerts": open_alerts,
            "active_info_gaps": scalar(
                "SELECT COUNT(*) FROM topics WHERE gap_status IN ('aktywna', 'w_uzupelnianiu')"
            ),
            "blocked_users": scalar("SELECT COUNT(*) FROM users WHERE blocked_until > ?", [now]),
        }

    def purge(self, before: str) -> dict[str, int]:
        """Usuń zapytania i twierdzenia starsze niż ``before`` (retencja danych)."""
        with self._lock:
            claims = self._db.execute("DELETE FROM claims WHERE ts < ?", [before]).rowcount
            queries = self._db.execute("DELETE FROM queries WHERE ts < ?", [before]).rowcount
            self._db.commit()
        return {"queries": queries, "claims": claims}
