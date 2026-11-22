"""CLI bazy (z katalogu ``backend/``)::

    python -m database check            # połączenie, lista tabel, stan migracji (bez zmian)
    python -m database migrate          # utwórz brakujące tabele
    python -m database seed-sources     # wgraj listę stron zaufanych z trustedSources/whitelist.py
    python -m database create-user --email a@b.pl --name "Jan Kowalski" --role admin

Hasło nowego konta: zmienna ``NEW_USER_PASSWORD`` albo pytanie w terminalu (bez echa).
Adres bazy nigdy nie jest wypisywany z hasłem.
"""

from __future__ import annotations

import argparse
import getpass
import os
import sys

from .connection import Database, DatabaseNotConfigured, redact
from .migrate import MigrationError, migrate, status


def _check(db: Database) -> int:
    version = db.fetch_value("SELECT current_setting('server_version')")
    name = db.fetch_value("SELECT current_database()")
    schema = db.fetch_value("SELECT current_schema()")
    print(f"Połączono: {redact(db.url)} (PostgreSQL {version}, baza {name}, schemat {schema})")
    tables = db.tables()
    print(f"Tabele ({len(tables)}): {', '.join(tables) if tables else 'brak'}")
    for row in status(db):
        state = "zastosowana " + row["applied_at"] if row["applied_at"] else "DO ZASTOSOWANIA"
        if row["changed"]:
            state += " (PLIK ZMIENIONY!)"
        print(f"  {row['version']:04d}_{row['name']}: {state}")
    return 0


def _migrate(db: Database) -> int:
    done = migrate(db)
    if not done:
        print("Schemat aktualny, nic do zrobienia.")
    for migration in done:
        print(f"Zastosowano {migration.version:04d}_{migration.name}")
    print(f"Tabele: {', '.join(db.tables())}")
    return 0


def _seed_sources(db: Database) -> int:
    from accounts.trusted import TrustedSourceRepository
    from trustedSources.whitelist import WHITELIST

    added = TrustedSourceRepository(db).seed(WHITELIST)
    print(f"Dodano {added} z {len(WHITELIST)} źródeł (istniejące bez zmian).")
    return 0


def _create_user(db: Database, args: argparse.Namespace) -> int:
    from accounts import AccountError, AccountService, Actor

    password = os.getenv("NEW_USER_PASSWORD") or getpass.getpass("Hasło nowego konta: ")
    try:
        user = AccountService(db).create_user(
            name=args.name,
            email=args.email,
            password=password,
            role=args.role,
            actor=Actor("cli"),
        )
    except AccountError as exc:
        print(f"Błąd: {exc}", file=sys.stderr)
        return 1
    print(f"Utworzono konto #{user.id} {user.email} (rola {user.role}).")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m database")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("check", help="połączenie, tabele i stan migracji")
    sub.add_parser("migrate", help="zastosuj brakujące migracje")
    sub.add_parser("seed-sources", help="wgraj listę stron zaufanych z kodu")
    create = sub.add_parser("create-user", help="utwórz konto")
    create.add_argument("--email", required=True)
    create.add_argument("--name", required=True)
    create.add_argument("--role", default="user", choices=["user", "moderator", "analyst", "admin"])
    args = parser.parse_args(argv)

    try:
        db = Database(max_size=2)
    except DatabaseNotConfigured as exc:
        print(f"Błąd: {exc}", file=sys.stderr)
        return 2
    try:
        if args.command == "check":
            return _check(db)
        if args.command == "migrate":
            return _migrate(db)
        if args.command == "seed-sources":
            return _seed_sources(db)
        return _create_user(db, args)
    except MigrationError as exc:
        print(f"Błąd migracji: {exc}", file=sys.stderr)
        return 3
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
