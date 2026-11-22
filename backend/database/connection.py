"""Połączenie z PostgreSQL (psycopg 3 + pula połączeń).

Adres bazy: ``DATABASE_URL`` (np. ``postgresql://user:haslo@host:5432/prawdowid``) ze
zmiennych środowiskowych albo z ``backend/.env``. ``DATABASE_SCHEMA`` ustawia
``search_path`` — testy używają tymczasowego schematu, żeby nie dotykać właściwych tabel.
"""

from __future__ import annotations

import os
import re
import threading
from collections.abc import Iterable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

BACKEND_ENV_FILE = Path(__file__).resolve().parents[1] / ".env"
PROJECT_ENV_FILE = Path(__file__).resolve().parents[2] / ".env"
_SCHEMA_NAME = re.compile(r"^[a-z_][a-z0-9_]{0,62}$")

Params = Sequence[Any] | Mapping[str, Any] | None


class DatabaseNotConfigured(RuntimeError):
    """Brak ``DATABASE_URL`` — moduły z bazą są wtedy wyłączone."""


def database_url() -> str | None:
    """``DATABASE_URL`` ze środowiska, z głównego ``.env`` albo z ``backend/.env`` (zapas)."""
    value = os.getenv("DATABASE_URL")
    for env_file in (PROJECT_ENV_FILE, BACKEND_ENV_FILE):
        if value or not env_file.is_file():
            continue
        from dotenv import dotenv_values

        value = dotenv_values(env_file).get("DATABASE_URL")
    return (value or "").strip() or None


def redact(url: str) -> str:
    """Adres do logów i komunikatów: bez hasła."""
    return re.sub(r"(://[^:/@]+):[^@]*@", r"\1:***@", url)


def _plain(value: Any) -> Any:
    """Daty jako ISO 8601 UTC z 'Z', jak w reszcie backendu."""
    if isinstance(value, datetime):
        if value.tzinfo is not None:  # timestamptz przychodzi w strefie sesji (np. +01:00)
            value = value.astimezone(UTC)
        text = value.isoformat(timespec="milliseconds")
        return text.replace("+00:00", "Z")
    if isinstance(value, date):
        return value.isoformat()
    return value


class Row(dict):
    """Wiersz dostępny po nazwie kolumny i po indeksie (jak ``sqlite3.Row``)."""

    def __init__(self, columns: Sequence[str], values: Sequence[Any]) -> None:
        super().__init__(zip(columns, (_plain(v) for v in values), strict=True))
        self._values = [_plain(v) for v in values]

    def __getitem__(self, key: Any) -> Any:
        if isinstance(key, int):
            return self._values[key]
        return super().__getitem__(key)


def _row_factory(cursor: Any) -> Any:
    columns = [column.name for column in cursor.description or ()]

    def make(values: Sequence[Any]) -> Row:
        return Row(columns, values)

    return make


class Database:
    """Cienka warstwa nad pulą psycopg: zapytania z parametrami, transakcje, wiersze jako dict."""

    def __init__(
        self,
        url: str | None = None,
        *,
        schema: str | None = None,
        min_size: int = 1,
        max_size: int = 5,
        timeout: float = 10.0,
    ) -> None:
        from psycopg_pool import ConnectionPool

        url = url or database_url()
        if not url:
            raise DatabaseNotConfigured("Ustaw DATABASE_URL (np. w backend/.env).")
        schema = schema if schema is not None else (os.getenv("DATABASE_SCHEMA") or None)
        if schema is not None and not _SCHEMA_NAME.match(schema):
            raise ValueError("DATABASE_SCHEMA: małe litery, cyfry i _")
        self.url = url
        self.schema = schema
        # prepare_threshold=None: bez nazwanych prepared statements po stronie serwera —
        # zgodne z poolerami (PgBouncer) i serwerami, gdzie połączenia dzielą proces.
        kwargs: dict[str, Any] = {"autocommit": False, "prepare_threshold": None}
        if schema:
            kwargs["options"] = f"-c search_path={schema},public"
        self._pool = ConnectionPool(
            url,
            min_size=min_size,
            max_size=max_size,
            kwargs=kwargs,
            timeout=timeout,
            open=True,
            name="prawdowid",
        )

    def __repr__(self) -> str:
        return f"Database({redact(self.url)!r}, schema={self.schema!r})"

    def close(self) -> None:
        self._pool.close()

    @contextmanager
    def transaction(self) -> Iterator[Any]:
        """Kursor w jednej transakcji: commit na końcu, rollback przy wyjątku."""
        with (
            self._pool.connection() as connection,
            connection.cursor(row_factory=_row_factory) as cursor,
        ):
            yield cursor

    def execute(self, sql: str, params: Params = None) -> int:
        with self.transaction() as cursor:
            cursor.execute(sql, params)
            return cursor.rowcount

    def fetch_all(self, sql: str, params: Params = None) -> list[Row]:
        with self.transaction() as cursor:
            cursor.execute(sql, params)
            return list(cursor.fetchall()) if cursor.description else []

    def fetch_one(self, sql: str, params: Params = None) -> Row | None:
        with self.transaction() as cursor:
            cursor.execute(sql, params)
            return cursor.fetchone() if cursor.description else None

    def fetch_value(self, sql: str, params: Params = None) -> Any:
        row = self.fetch_one(sql, params)
        return None if row is None else row[0]

    def tables(self) -> list[str]:
        rows = self.fetch_all(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = current_schema() AND table_type = 'BASE TABLE' "
            "ORDER BY table_name"
        )
        return [row["table_name"] for row in rows]


_shared: dict[tuple[str, str | None], Database] = {}
_shared_lock = threading.Lock()


def get_database(url: str | None = None, *, schema: str | None = None) -> Database:
    """Wspólna pula dla procesu (jedna na adres i schemat)."""
    url = url or database_url()
    if not url:
        raise DatabaseNotConfigured("Ustaw DATABASE_URL (np. w backend/.env).")
    schema = schema if schema is not None else (os.getenv("DATABASE_SCHEMA") or None)
    key = (url, schema)
    with _shared_lock:
        if key not in _shared:
            _shared[key] = Database(url, schema=schema)
        return _shared[key]


def placeholders(sql: str) -> str:
    """Zamień parametry SQLite (``?``) na psycopg (``%s``); ``%`` w literałach podwaja."""
    out: list[str] = []
    in_string = False
    for char in sql:
        if char == "'":
            in_string = not in_string
            out.append(char)
        elif char == "?" and not in_string:
            out.append("%s")
        elif char == "%":
            out.append("%%")
        else:
            out.append(char)
    return "".join(out)


def as_params(values: Iterable[Any]) -> list[Any]:
    return list(values)
