"""Ustawienia samego panelu admina (token awaryjny, baza).

Nie ma pseudonimizacji użytkowników aplikacji: rejestr nie zapisuje żadnych ich identyfikatorów.
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

    @classmethod
    def from_environment(cls) -> AdminSettings:
        """Zmienne środowiskowe; brakujące uzupełnia główny ``.env``, potem ``backend/.env``."""
        load_env_file()
        return cls(
            api_token=(os.getenv("ADMIN_API_TOKEN") or "").strip() or None,
            db_path=Path(os.getenv("ADMIN_DB_PATH") or DEFAULT_DB_PATH),
        )


def load_env_file(*paths: Path) -> None:
    from dotenv import load_dotenv

    for path in paths or (ENV_FILE, LEGACY_ENV_FILE):
        if path.is_file():
            load_dotenv(path, override=False)
