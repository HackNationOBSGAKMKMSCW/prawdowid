"""Durable result identifiers and idempotent feedback storage in PostgreSQL."""

from __future__ import annotations

import os
import ssl
from datetime import UTC, datetime, timedelta
from enum import Enum
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from uuid import UUID

import asyncpg

# Ten sam plik stosuje ``python -m database migrate``; jest idempotentny (IF NOT EXISTS).
MIGRATION_PATH = (
    Path(__file__).resolve().parent / "database" / "migrations" / "0005_api_feedback.sql"
)
_SSL_MODES = {"disable", "allow", "prefer", "require", "verify-ca", "verify-full"}


def _dsn_and_ssl(database_url: str) -> tuple[str, bool | str | ssl.SSLContext]:
    parts = urlsplit(database_url)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    url_ssl_mode = query.pop("sslmode", None)
    ssl_mode = os.getenv("DATABASE_SSL_MODE") or url_ssl_mode or "verify-full"
    if ssl_mode not in _SSL_MODES:
        raise ValueError("DATABASE_SSL_MODE must be a supported PostgreSQL SSL mode")
    dsn = urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))
    if ssl_mode == "disable":
        ssl_option: bool | str | ssl.SSLContext = False
    elif ssl_mode == "verify-full":
        ssl_option = ssl.create_default_context()
    else:
        ssl_option = ssl_mode
    return dsn, ssl_option


class ReportOutcome(Enum):
    """What ``save_report`` did: one report per result, the first one is kept."""

    MISSING = "missing"  # no such result, or it has expired
    SAVED = "saved"  # this call stored the report
    DUPLICATE = "duplicate"  # the result already had a report; nothing changed


class PostgresStore:
    def __init__(self, pool: asyncpg.Pool, *, retention_days: int):
        self.pool = pool
        self.retention_days = retention_days

    @classmethod
    async def connect_from_environment(cls) -> PostgresStore:
        database_url = os.getenv("DATABASE_URL", "").strip()
        if not database_url:
            raise RuntimeError("DATABASE_URL is required")
        retention_days = int(os.getenv("REPORT_RETENTION_DAYS", "180"))
        if not 1 <= retention_days <= 3650:
            raise ValueError("REPORT_RETENTION_DAYS must be between 1 and 3650")

        dsn, ssl_option = _dsn_and_ssl(database_url)
        pool = await asyncpg.create_pool(
            dsn=dsn,
            ssl=ssl_option,
            min_size=1,
            max_size=5,
            command_timeout=10,
        )
        store = cls(pool, retention_days=retention_days)
        await store.initialize()
        return store

    async def initialize(self) -> None:
        await self.pool.execute(MIGRATION_PATH.read_text(encoding="utf-8"))

    async def close(self) -> None:
        await self.pool.close()

    async def health_check(self) -> None:
        await self.pool.fetchval("SELECT 1")

    async def record_result(self, result_id: UUID, input_type: str) -> None:
        expires_at = datetime.now(UTC) + timedelta(days=self.retention_days)
        await self.pool.execute(
            """
            INSERT INTO api_check_results (id, input_type, expires_at)
            VALUES ($1, $2, $3)
            """,
            result_id,
            input_type,
            expires_at,
        )

    async def save_report(
        self, result_id: UUID, reason: str, comment: str | None
    ) -> ReportOutcome:
        async with self.pool.acquire() as connection, connection.transaction():
            exists = await connection.fetchval(
                """
                SELECT 1
                FROM api_check_results
                WHERE id = $1 AND expires_at > NOW()
                FOR KEY SHARE
                """,
                result_id,
            )
            if exists is None:
                return ReportOutcome.MISSING
            inserted = await connection.execute(
                """
                INSERT INTO api_check_reports (result_id, reason, comment)
                VALUES ($1, $2, $3)
                ON CONFLICT (result_id) DO NOTHING
                """,
                result_id,
                reason,
                comment,
            )
            if not inserted.endswith(" 1"):
                return ReportOutcome.DUPLICATE
            await connection.execute(
                """
                UPDATE api_check_results
                SET expires_at = GREATEST(expires_at, NOW() + ($2 * INTERVAL '1 day'))
                WHERE id = $1
                """,
                result_id,
                self.retention_days,
            )
        return ReportOutcome.SAVED

    async def delete_expired(self) -> int:
        status = await self.pool.execute(
            "DELETE FROM api_check_results WHERE expires_at <= NOW()"
        )
        return int(status.rsplit(" ", 1)[-1])
