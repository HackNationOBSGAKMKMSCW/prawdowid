"""Testy na prawdziwym PostgreSQL: ``TEST_DATABASE_URL`` + tymczasowy schemat.

Każda sesja testów tworzy schemat ``test_<losowy>``, stosuje w nim migracje i usuwa go
na końcu (``DROP SCHEMA ... CASCADE``), więc właściwe tabele serwisu są nietknięte.
Bez ``TEST_DATABASE_URL`` testy są pomijane.
"""

import os
import secrets

import pytest


@pytest.fixture(scope="session")
def pg_url() -> str:
    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.skip("ustaw TEST_DATABASE_URL, żeby uruchomić testy PostgreSQL")
    return url


@pytest.fixture(scope="session")
def pg_schema(pg_url):
    from database import Database

    name = f"test_{secrets.token_hex(4)}"
    admin = Database(pg_url, schema=None, max_size=1)
    admin.execute(f"CREATE SCHEMA {name}")
    try:
        yield name
    finally:
        admin.execute(f"DROP SCHEMA {name} CASCADE")
        admin.close()


@pytest.fixture(scope="session")
def db(pg_url, pg_schema):
    from database import Database, migrate

    database = Database(pg_url, schema=pg_schema, max_size=4)
    migrate(database)
    yield database
    database.close()


@pytest.fixture
def clean_db(db):
    """Pusta baza dla testu (te same tabele, bez danych).

    Nazwy tabel z jawnym schematem testowym: czyszczenie nigdy nie dotknie ``public``, nawet
    gdy serwer współdzieli sesję między połączeniami (np. PGlite) i ``search_path`` przecieka.
    Na takim serwerze testy i tak mogą zapisać wiersze w ``public`` — uruchamiaj je na bazie
    bez danych, na których ci zależy.
    """
    rows = db.fetch_all(
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_schema = %s AND table_type = 'BASE TABLE'",
        [db.schema],
    )
    tables = [f"{db.schema}.{r['table_name']}" for r in rows if r["table_name"] != "schema_migrations"]
    if not tables:
        pytest.fail(
            f"Migracje nie utworzyły tabel w schemacie {db.schema}: serwer współdzieli sesję "
            "między połączeniami (np. PGlite) i testy pisałyby do public. Użyj osobnej bazy."
        )
    db.execute(f"TRUNCATE {', '.join(tables)} RESTART IDENTITY CASCADE")
    return db
