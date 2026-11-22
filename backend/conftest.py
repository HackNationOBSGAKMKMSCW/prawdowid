"""Testy backendu nie łączą się z bazą z ``DATABASE_URL`` (np. z ``backend/.env``).

Testy integracyjne PostgreSQL używają osobnej zmiennej ``TEST_DATABASE_URL`` i
tymczasowego schematu (``backend/database/tests``).
"""

import os

os.environ["ADMIN_STORE"] = "sqlite"
# /api/check nie zapisuje do rejestru panelu (admin/data/admin.db); testy wstrzykują atrapę.
os.environ["ADMIN_MONITOR"] = "off"
os.environ["TRUSTED_SOURCES_STORE"] = "static"
# Limit zapytań na IP sprawdzają osobne testy (z własnym RateLimiter); reszta go nie potrzebuje.
os.environ["CHECK_RATE_LIMIT"] = "off"

# server.py montuje panel admina: rejestr i nadpisania konfiguracji testów w katalogu
# tymczasowym, a nie w backend/admin/data (nadpisania zmieniałyby środowisko innych testów).
import tempfile  # noqa: E402
from pathlib import Path  # noqa: E402

_ADMIN_TMP = Path(tempfile.mkdtemp(prefix="prawdowid-admin-tests-"))
os.environ["ADMIN_DB_PATH"] = str(_ADMIN_TMP / "admin.db")
os.environ["RUNTIME_CONFIG_FILE"] = str(_ADMIN_TMP / "runtime_config.json")
