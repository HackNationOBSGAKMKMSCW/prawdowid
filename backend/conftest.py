"""Testy backendu nie łączą się z bazą z ``DATABASE_URL`` (np. z ``backend/.env``).

Testy integracyjne PostgreSQL używają osobnej zmiennej ``TEST_DATABASE_URL`` i
tymczasowego schematu (``backend/database/tests``).
"""

import os

os.environ["ADMIN_STORE"] = "sqlite"
os.environ["TRUSTED_SOURCES_STORE"] = "static"
