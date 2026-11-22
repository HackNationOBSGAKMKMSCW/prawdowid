"""Migracje schematu: pliki ``migrations/NNNN_nazwa.sql`` stosowane po kolei, każdy raz.

Stan trzyma tabela ``schema_migrations`` (wersja, nazwa, suma kontrolna, czas). Całość
działa pod blokadą doradczą, więc dwa procesy nie zastosują migracji równocześnie.
Zmieniony po zastosowaniu plik jest błędem — nową zmianę dodaje się nowym plikiem.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

from .connection import Database

MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"
_FILE = re.compile(r"^(\d{4})_([a-z0-9_]+)\.sql$")
_LOCK_KEY = 7_242_026  # dowolna stała dla pg_advisory_xact_lock


@dataclass(frozen=True)
class Migration:
    version: int
    name: str
    sql: str

    @property
    def checksum(self) -> str:
        return hashlib.sha256(self.sql.encode("utf-8")).hexdigest()[:16]


class MigrationError(RuntimeError):
    pass


def discover(directory: Path = MIGRATIONS_DIR) -> list[Migration]:
    migrations = []
    for path in sorted(directory.glob("*.sql")):
        match = _FILE.match(path.name)
        if not match:
            raise MigrationError(f"zła nazwa pliku migracji: {path.name}")
        sql = path.read_text(encoding="utf-8").replace("\r\n", "\n")
        migrations.append(Migration(int(match.group(1)), match.group(2), sql))
    versions = [migration.version for migration in migrations]
    if len(set(versions)) != len(versions):
        raise MigrationError("powtórzony numer migracji")
    return migrations


_STATE_TABLE = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    version    integer PRIMARY KEY,
    name       text NOT NULL,
    checksum   text NOT NULL,
    applied_at timestamptz NOT NULL DEFAULT now()
)
"""


def applied(db: Database) -> dict[int, dict]:
    db.execute(_STATE_TABLE)
    rows = db.fetch_all("SELECT version, name, checksum, applied_at FROM schema_migrations")
    return {row["version"]: dict(row) for row in rows}


def migrate(db: Database, migrations: list[Migration] | None = None) -> list[Migration]:
    """Zastosuj brakujące migracje; zwraca listę zastosowanych teraz."""
    migrations = discover() if migrations is None else migrations
    done: list[Migration] = []
    with db.transaction() as cursor:
        cursor.execute("SELECT pg_advisory_xact_lock(%s)", [_LOCK_KEY])
        cursor.execute(_STATE_TABLE)
        cursor.execute("SELECT version, checksum FROM schema_migrations")
        existing = {row["version"]: row["checksum"] for row in cursor.fetchall()}
        for migration in migrations:
            if migration.version in existing:
                if existing[migration.version] != migration.checksum:
                    raise MigrationError(
                        f"migracja {migration.version:04d}_{migration.name} została zmieniona "
                        "po zastosowaniu — dodaj nowy plik zamiast edytować stary"
                    )
                continue
            cursor.execute(migration.sql)
            cursor.execute(
                "INSERT INTO schema_migrations (version, name, checksum) VALUES (%s, %s, %s)",
                [migration.version, migration.name, migration.checksum],
            )
            done.append(migration)
    return done


def status(db: Database) -> list[dict]:
    state = applied(db)
    return [
        {
            "version": migration.version,
            "name": migration.name,
            "applied_at": (state.get(migration.version) or {}).get("applied_at"),
            "changed": migration.version in state
            and state[migration.version]["checksum"] != migration.checksum,
        }
        for migration in discover()
    ]
