"""Ustawienia samego panelu admina (token awaryjny, baza).

Rejestr nie zapisuje identyfikatorów użytkowników aplikacji. Wyjątek: adres IP, z którego
przyszła próba prompt injection, trafia do blokad jako klucz HMAC (``ip_salt``) z maską.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent / "data"
# Główny .env projektu, a jako zapas backend/.env — niezależnie od katalogu startu procesu.
ENV_FILE = Path(__file__).resolve().parents[2] / ".env"
LEGACY_ENV_FILE = Path(__file__).resolve().parents[1] / ".env"
DEFAULT_DB_PATH = DATA_DIR / "admin.db"


@dataclass(frozen=True)
class AdminSettings:
    api_token: str | None = field(default=None, repr=False)
    db_path: Path = DEFAULT_DB_PATH
    max_text_length: int = 4000
    # Sól HMAC kluczy adresów IP w blokadach; brak = losowa, zapisana w bazie (monitor_meta).
    ip_salt: str | None = field(default=None, repr=False)

    @classmethod
    def from_environment(cls) -> AdminSettings:
        """Zmienne środowiskowe; brakujące uzupełnia główny ``.env``, potem ``backend/.env``."""
        load_env_file()
        return cls(
            api_token=(os.getenv("ADMIN_API_TOKEN") or "").strip() or None,
            db_path=Path(os.getenv("ADMIN_DB_PATH") or DEFAULT_DB_PATH),
            ip_salt=(os.getenv("ADMIN_IP_SALT") or "").strip() or None,
        )


def load_env_file(*paths: Path) -> None:
    from dotenv import load_dotenv

    for path in paths or (ENV_FILE, LEGACY_ENV_FILE):
        if path.is_file():
            load_dotenv(path, override=False)
