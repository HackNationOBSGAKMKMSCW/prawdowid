"""Trwały rejestr panelu admina w SQLite (stdlib, jeden plik, tryb WAL).

Tabele: ``user_queries`` (zapytania, anonimowe), ``query_claims`` (twierdzenia z werdyktem
i tematem), ``query_topics`` (grupy podobnych twierdzeń + stan luki informacyjnej),
``monitor_alerts`` (zdarzenia dla admina), ``config_audit``. Bez danych o użytkownikach
aplikacji: ``user_key`` ma zawsze wartość ``monitor.ANONYMOUS_KEY``, ``user_label`` jest pusty.
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
CREATE TABLE IF NOT EXISTS user_queries (
    id TEXT PRIMARY KEY,
    ts TEXT NOT NULL,
    user_key TEXT NOT NULL,
    user_label TEXT,
    account_id INTEGER,
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
    error TEXT,
    report TEXT
);
CREATE INDEX IF NOT EXISTS ix_user_queries_ts ON user_queries(ts);
CREATE INDEX IF NOT EXISTS ix_user_queries_user ON user_queries(user_key, ts);
CREATE INDEX IF NOT EXISTS ix_user_queries_request ON user_queries(request_id);

CREATE TABLE IF NOT EXISTS query_claims (
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
CREATE INDEX IF NOT EXISTS ix_query_claims_topic ON query_claims(topic_id, kind, ts);
CREATE INDEX IF NOT EXISTS ix_query_claims_query ON query_claims(query_id);

CREATE TABLE IF NOT EXISTS query_topics (
    id TEXT PRIMARY KEY,
    label TEXT NOT NULL,
    tokens TEXT NOT NULL,
    created_at TEXT NOT NULL,
    last_seen TEXT NOT NULL,
    gap_status TEXT NOT NULL DEFAULT 'brak',
    gap_since TEXT,
    gap_users INTEGER NOT NULL DEFAULT 0,
    gap_queries INTEGER NOT NULL DEFAULT 0,
    gap_note TEXT,
    gap_updated_at TEXT
);
CREATE INDEX IF NOT EXISTS ix_query_topics_seen ON query_topics(last_seen);

CREATE TABLE IF NOT EXISTS monitor_alerts (
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
CREATE INDEX IF NOT EXISTS ix_monitor_alerts_open ON monitor_alerts(type, subject, status);

CREATE TABLE IF NOT EXISTS config_audit (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    actor TEXT NOT NULL,
    field TEXT NOT NULL,
    old TEXT,
    new TEXT
);
"""

# Kolumny dodane po pierwszej wersji schematu: starsze pliki SQLite dostają je przy otwarciu.
# Kolumny dodane po pierwszej wersji schematu: stare pliki SQLite dostają je przy otwarciu.
LATER_COLUMNS = {
    "user_queries": {"report": "TEXT"},  # zgłoszenia błędów ze strony
    "query_topics": {"gap_queries": "INTEGER NOT NULL DEFAULT 0"},
}

_FORGET_END_USERS = """
UPDATE user_queries SET user_key = 'anonim', user_label = NULL
    WHERE user_key <> 'anonim' OR user_label IS NOT NULL;
UPDATE query_claims SET user_key = 'anonim' WHERE user_key <> 'anonim';
DELETE FROM monitor_alerts WHERE type = 'niebezpieczny_uzytkownik';
DROP TABLE IF EXISTS end_users;
"""

OPEN_ALERT_STATUSES = ("otwarty", "w_analizie")
GAP_SORTS = {"zapytania": "gap_queries", "osoby": "gap_users", "auto": "gap_queries"}

# Tryb „auto”: rozpoznana osoba liczy się raz, każde anonimowe zapytanie osobno.
_REPORTERS = (
    "COUNT(DISTINCT CASE WHEN user_key = ? THEN query_id END) "
    "+ COUNT(DISTINCT CASE WHEN user_key <> ? THEN user_key END)"
)
# Zapytania bez pokrycia liczone z tego samego zbioru co mianownik (zakończone, czas zapytania).
_UNCOVERED_QUERIES = (
    "SELECT COUNT(DISTINCT c.query_id) FROM query_claims AS c "
    "JOIN user_queries AS q ON q.id = c.query_id "
    "WHERE c.kind = 'luka' AND q.status = 'zakonczone' AND q.ts >= ?"
)


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
    """Rejestr w SQLite (lokalnie i w testach). ``PostgresAdminStore`` — wersja serwerowa."""

    # Fragmenty SQL zależne od dialektu (nadpisywane w PostgresAdminStore).
    _FLAG_MATCH = "EXISTS (SELECT 1 FROM json_each(user_queries.flags) WHERE value LIKE ?)"
    _SEVERITY = "json_extract(safety, '$.severity')"

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
            for table, columns in LATER_COLUMNS.items():
                present = {row["name"] for row in self._db.execute(f"PRAGMA table_info({table})")}
                for name, definition in columns.items():
                    if name not in present:
                        self._db.execute(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")
            # Starsze pliki: bez danych o użytkownikach aplikacji (jak migracja 0010 w PostgreSQL).
            self._db.executescript(_FORGET_END_USERS)
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
        self._execute(f"INSERT INTO user_queries ({names}) VALUES ({marks})", fields.values())

    def update_query(self, query_id: str, **fields: Any) -> None:
        if "flags" in fields:
            fields["flags"] = json.dumps(sorted(set(fields["flags"])), ensure_ascii=False)
        if isinstance(fields.get("report"), dict):
            fields["report"] = json.dumps(fields["report"], ensure_ascii=False)
        assignments = ", ".join(f"{name} = ?" for name in fields)
        self._execute(
            f"UPDATE user_queries SET {assignments} WHERE id = ?", [*fields.values(), query_id]
        )

    def query_by_request(self, request_id: str) -> dict[str, Any] | None:
        """Wpis dziennika dla ``request_id`` z logów (bez twierdzeń)."""
        return _row(
            self._one(
                "SELECT * FROM user_queries WHERE request_id = ? ORDER BY ts DESC LIMIT 1",
                [request_id],
            ),
            ("flags", "safety", "report"),
        )

    def get_query(self, query_id: str) -> dict[str, Any] | None:
        query = _row(
            self._one("SELECT * FROM user_queries WHERE id = ?", [query_id]),
            ("flags", "safety", "report"),
        )
        if query is not None:
            query["claims"] = [
                dict(row)
                for row in self._all(
                    "SELECT id, topic_id, text, verdict, kind, sources_count FROM query_claims "
                    "WHERE query_id = ? ORDER BY id",
                    [query_id],
                )
            ]
        return query

    def list_queries(
        self,
        *,
        account_id: int | None = None,
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
        if account_id is not None:
            where.append("account_id = ?")
            params.append(account_id)
        if flag:
            where.append(self._FLAG_MATCH)
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
        total = self._one(f"SELECT COUNT(*) FROM user_queries {clause}", params)[0]
        rows = self._all(
            f"SELECT * FROM user_queries {clause} ORDER BY ts DESC LIMIT ? OFFSET ?",
            [*params, limit, offset],
        )
        return [_row(row, ("flags", "safety", "report")) for row in rows], total

    # --- twierdzenia i tematy ----------------------------------------------------------

    def insert_claim(self, **fields: Any) -> None:
        names = ", ".join(fields)
        marks = ", ".join("?" for _ in fields)
        self._execute(f"INSERT INTO query_claims ({names}) VALUES ({marks})", fields.values())

    def recent_topics(self, since: str, limit: int = 5000) -> list[tuple[str, frozenset[str]]]:
        rows = self._all(
            "SELECT id, tokens FROM query_topics WHERE last_seen >= ? ORDER BY last_seen DESC LIMIT ?",
            [since, limit],
        )
        return [(row["id"], frozenset(_row(row, ("tokens",))["tokens"])) for row in rows]

    def create_topic(self, *, label: str, tokens: frozenset[str], ts: str) -> str:
        topic_id = new_id()
        self._execute(
            "INSERT INTO query_topics (id, label, tokens, created_at, last_seen) VALUES (?, ?, ?, ?, ?)",
            [topic_id, label[:300], json.dumps(sorted(tokens)), ts, ts],
        )
        return topic_id

    def touch_topic(self, topic_id: str, ts: str) -> None:
        self._execute("UPDATE query_topics SET last_seen = ? WHERE id = ?", [ts, topic_id])

    def topic_row(self, topic_id: str) -> dict[str, Any] | None:
        return _row(self._one("SELECT * FROM query_topics WHERE id = ?", [topic_id]), ("tokens",))

    def get_topic(self, topic_id: str) -> dict[str, Any] | None:
        topic = _row(self._one("SELECT * FROM query_topics WHERE id = ?", [topic_id]), ("tokens",))
        if topic is not None:
            topic["claims"] = [
                dict(row)
                for row in self._all(
                    "SELECT query_id, ts, user_key, text, verdict, kind, sources_count "
                    "FROM query_claims WHERE topic_id = ? ORDER BY ts DESC LIMIT 200",
                    [topic_id],
                )
            ]
            topic["by_kind"] = {
                row["kind"]: {"claims": row["n"], "users": row["users"]}
                for row in self._all(
                    "SELECT kind, COUNT(*) AS n, COUNT(DISTINCT user_key) AS users "
                    "FROM query_claims WHERE topic_id = ? GROUP BY kind",
                    [topic_id],
                )
            }
        return topic

    def set_gap(self, topic_id: str, **fields: Any) -> None:
        assignments = ", ".join(f"{name} = ?" for name in fields)
        self._execute(f"UPDATE query_topics SET {assignments} WHERE id = ?", [*fields.values(), topic_id])

    def list_gaps(
        self,
        statuses: Iterable[str],
        limit: int = 100,
        offset: int = 0,
        *,
        sort_by: str = "zapytania",
    ) -> list[dict[str, Any]]:
        statuses = list(statuses)
        marks = ", ".join("?" for _ in statuses)
        primary = GAP_SORTS.get(sort_by, "gap_queries")
        secondary = "gap_users" if primary == "gap_queries" else "gap_queries"
        rows = self._all(
            f"SELECT id, label, created_at, last_seen, gap_status, gap_since, gap_users, "
            f"gap_queries, gap_note, gap_updated_at FROM query_topics "
            f"WHERE gap_status IN ({marks}) "
            f"ORDER BY {primary} DESC, {secondary} DESC, last_seen DESC LIMIT ? OFFSET ?",
            [*statuses, limit, offset],
        )
        return [dict(row) for row in rows]

    def gap_status_counts(self) -> dict[str, int]:
        return {
            row["gap_status"]: int(row["n"])
            for row in self._all(
                "SELECT gap_status, COUNT(*) AS n FROM query_topics GROUP BY gap_status"
            )
        }

    def gap_counts(
        self, topic_id: str, kind: str, since: str, anonymous_key: str
    ) -> dict[str, int]:
        """Zapytania, różne pseudonimy i „zgłaszający” (tryb auto) dla tematu od ``since``."""
        row = self._one(
            f"SELECT COUNT(DISTINCT query_id), COUNT(DISTINCT user_key), {_REPORTERS} "
            "FROM query_claims WHERE topic_id = ? AND kind = ? AND ts >= ?",
            [anonymous_key, anonymous_key, topic_id, kind, since],
        )
        return {"queries": int(row[0]), "users": int(row[1]), "reporters": int(row[2] or 0)}

    def distinct_queries(self, topic_id: str, kind: str, since: str) -> int:
        """Zapytania (nie twierdzenia): dwa twierdzenia z jednego zapytania liczą się raz."""
        row = self._one(
            "SELECT COUNT(DISTINCT query_id) FROM query_claims WHERE topic_id = ? AND kind = ? "
            "AND ts >= ?",
            [topic_id, kind, since],
        )
        return int(row[0])

    # --- zapytania bez pokrycia w danych (ranking dla panelu) ---------------------------

    def uncovered_ranking(
        self,
        since: str,
        *,
        min_queries: int = 1,
        limit: int = 50,
        offset: int = 0,
        anonymous_key: str = "",
    ) -> tuple[list[dict[str, Any]], int]:
        """Tematy z największą liczbą zapytań bez pokrycia (``kind='luka'``) od ``since``."""
        grouped = (
            "SELECT topic_id, COUNT(DISTINCT query_id) AS queries, "
            f"COUNT(DISTINCT user_key) AS users, {_REPORTERS} AS reporters, MAX(ts) AS last_seen "
            "FROM query_claims WHERE kind = 'luka' AND ts >= ? GROUP BY topic_id "
            "HAVING COUNT(DISTINCT query_id) >= ?"
        )
        params = [anonymous_key, anonymous_key, since, min_queries]
        total = int(self._one(f"SELECT COUNT(*) FROM ({grouped}) AS g", params)[0])
        rows = self._all(
            f"SELECT g.topic_id, t.label, t.gap_status, t.gap_note, t.gap_since, g.queries, "
            f"g.users, g.reporters, g.last_seen FROM ({grouped}) AS g "
            f"JOIN query_topics AS t ON t.id = g.topic_id "
            f"ORDER BY g.queries DESC, g.last_seen DESC LIMIT ? OFFSET ?",
            [*params, limit, offset],
        )
        return [dict(row) for row in rows], total

    def uncovered_timestamps(self, topic_ids: Iterable[str], since: str) -> list[tuple[str, Any]]:
        """(topic_id, ts) zapytań bez pokrycia — do trendu dziennego liczonego w Pythonie."""
        topic_ids = list(topic_ids)
        if not topic_ids:
            return []
        marks = ", ".join("?" for _ in topic_ids)
        rows = self._all(
            f"SELECT topic_id, query_id, MIN(ts) AS ts FROM query_claims "
            f"WHERE kind = 'luka' AND ts >= ? AND topic_id IN ({marks}) "
            f"GROUP BY topic_id, query_id",
            [since, *topic_ids],
        )
        return [(row["topic_id"], row["ts"]) for row in rows]

    def uncovered_totals(self, since: str) -> dict[str, int]:
        """Zakończone zapytania w oknie i te z co najmniej jednym twierdzeniem bez pokrycia."""
        uncovered = self._one(_UNCOVERED_QUERIES, [since])[0]
        completed = self._one(
            "SELECT COUNT(*) FROM user_queries WHERE ts >= ? AND status = 'zakonczone'", [since]
        )[0]
        return {"uncovered_queries": int(uncovered), "total_queries": int(completed)}

    def claim_count(self, topic_id: str, kind: str, since: str) -> int:
        row = self._one(
            "SELECT COUNT(*) FROM query_claims WHERE topic_id = ? AND kind = ? AND ts >= ?",
            [topic_id, kind, since],
        )
        return int(row[0])

    # --- treści niebezpieczne (zbiorczo, bez danych o osobach) ---------------------------

    def dangerous_count(self, since: str, *, severity: str | None = None) -> int:
        """Zapytania o treści niebezpieczne od ``since`` (``severity``: tylko dany poziom)."""
        sql = f"SELECT COUNT(*) FROM user_queries WHERE ts >= ? AND {self._SEVERITY} "
        if severity:
            row = self._one(sql + "= ?", [since, severity])
        else:
            row = self._one(sql + "IN ('sredni', 'wysoki')", [since])
        return int(row[0])

    # --- alerty ------------------------------------------------------------------------

    def open_alert(self, alert_type: str, subject: str) -> dict[str, Any] | None:
        return _row(
            self._one(
                "SELECT * FROM monitor_alerts WHERE type = ? AND subject = ? AND status IN (?, ?) "
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
        self._execute(f"INSERT INTO monitor_alerts ({names}) VALUES ({marks})", fields.values())
        return fields["id"]

    def update_alert(self, alert_id: str, **fields: Any) -> None:
        if "details" in fields:
            fields["details"] = json.dumps(fields["details"], ensure_ascii=False)
        assignments = ", ".join(f"{name} = ?" for name in fields)
        self._execute(f"UPDATE monitor_alerts SET {assignments} WHERE id = ?", [*fields.values(), alert_id])

    def increment_alert(self, alert_id: str, **fields: Any) -> None:
        """``count = count + 1`` w SQL (bez utraty przyrostu) i pozostałe pola."""
        if "details" in fields:
            fields["details"] = json.dumps(fields["details"], ensure_ascii=False)
        assignments = "".join(f", {name} = ?" for name in fields)
        self._execute(
            f"UPDATE monitor_alerts SET count = count + 1{assignments} WHERE id = ?",
            [*fields.values(), alert_id],
        )

    def get_alert(self, alert_id: str) -> dict[str, Any] | None:
        return _row(self._one("SELECT * FROM monitor_alerts WHERE id = ?", [alert_id]), ("details",))

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
            f"SELECT * FROM monitor_alerts {clause} ORDER BY last_seen DESC LIMIT ? OFFSET ?",
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

    def stats(self, since: str, now: str | None = None) -> dict[str, Any]:
        def scalar(sql: str, params: Iterable[Any] = ()) -> int:
            return int(self._one(sql, params)[0])

        verdicts = {
            row["verdict"] or "brak": row["n"]
            for row in self._all(
                "SELECT verdict, COUNT(*) AS n FROM user_queries WHERE ts >= ? GROUP BY verdict",
                [since],
            )
        }
        statuses = {
            row["status"]: row["n"]
            for row in self._all(
                "SELECT status, COUNT(*) AS n FROM user_queries WHERE ts >= ? GROUP BY status", [since]
            )
        }
        open_alerts = {
            row["type"]: row["n"]
            for row in self._all(
                "SELECT type, COUNT(*) AS n FROM monitor_alerts WHERE status IN (?, ?) GROUP BY type",
                OPEN_ALERT_STATUSES,
            )
        }
        return {
            "queries": scalar("SELECT COUNT(*) FROM user_queries WHERE ts >= ?", [since]),
            "dangerous_queries": scalar(
                "SELECT COUNT(*) FROM user_queries WHERE ts >= ? "
                f"AND {self._SEVERITY} IN ('sredni', 'wysoki')",
                [since],
            ),
            "verdicts": verdicts,
            "statuses": statuses,
            "open_alerts": open_alerts,
            "active_info_gaps": scalar(
                "SELECT COUNT(*) FROM query_topics WHERE gap_status IN ('aktywna', 'w_uzupelnianiu')"
            ),
            "uncovered_queries": scalar(_UNCOVERED_QUERIES, [since]),
        }

    def purge(self, before: str) -> dict[str, int]:
        """Usuń zapytania i twierdzenia starsze niż ``before`` (retencja danych)."""
        claims = self._execute("DELETE FROM query_claims WHERE ts < ?", [before]).rowcount
        queries = self._execute("DELETE FROM user_queries WHERE ts < ?", [before]).rowcount
        return {"queries": queries, "claims": claims}


def open_store(settings: Any) -> AdminStore:
    """PostgreSQL, gdy jest ``DATABASE_URL`` (``ADMIN_STORE=sqlite`` wymusza plik lokalny)."""
    import os

    if os.getenv("ADMIN_STORE", "").strip().lower() != "sqlite":
        from database import database_url, get_database

        if database_url():
            return PostgresAdminStore(get_database())
    return AdminStore(settings.db_path)


class _Result:
    def __init__(self, rowcount: int) -> None:
        self.rowcount = rowcount


class PostgresAdminStore(AdminStore):
    """Ten sam rejestr na wspólnej bazie PostgreSQL (tabele z migracji 0004)."""

    _FLAG_MATCH = (
        "EXISTS (SELECT 1 FROM jsonb_array_elements_text(user_queries.flags) AS f(value) "
        "WHERE f.value LIKE ?)"
    )
    _SEVERITY = "(safety->>'severity')"

    def __init__(self, db: Any) -> None:  # database.Database
        self.db = db
        self.path = None

    def close(self) -> None:
        """Pula jest współdzielona w procesie — zamyka ją właściciel ``Database``."""

    def _execute(self, sql: str, params: Iterable[Any] = ()) -> Any:
        from database import placeholders

        return _Result(self.db.execute(placeholders(sql), list(params)))

    def _all(self, sql: str, params: Iterable[Any] = ()) -> list[Any]:
        from database import placeholders

        return [_json_as_text(row) for row in self.db.fetch_all(placeholders(sql), list(params))]

    def _one(self, sql: str, params: Iterable[Any] = ()) -> Any:
        from database import placeholders

        return _json_as_text(self.db.fetch_one(placeholders(sql), list(params)))


# Kolumny jsonb wracają z psycopg zdekodowane; reszta kodu (wspólna z SQLite) dekoduje
# je sama, więc oddajemy je jako tekst JSON — jak SQLite.
_JSON_COLUMNS = frozenset({"flags", "safety", "tokens", "details", "old", "new", "report"})


def _json_as_text(row: Any) -> Any:
    """Kolumny jsonb jako tekst JSON; pozostałe wiersze bez zmian.

    Wiersza bez kolumn JSON nie przebudowujemy: agregaty bez aliasu (np. dwa ``COUNT(...)``)
    mają w PostgreSQL tę samą nazwę ``count``, więc przebudowa po nazwach gubiła wartości
    i odczyt ``row[2]`` kończył się ``IndexError`` (luki informacyjne nie powstawały).
    """
    if row is None:
        return None
    if not any(c in _JSON_COLUMNS and row[c] is not None for c in row):
        return row
    from database import Row

    columns = list(row.keys())
    values = [
        json.dumps(row[c], ensure_ascii=False) if c in _JSON_COLUMNS and row[c] is not None else row[c]
        for c in columns
    ]
    return Row(columns, values)
