"""Ustawienia samego panelu admina (token, baza, pseudonimizacja użytkowników)."""

from __future__ import annotations

import hashlib
import hmac
import os
from dataclasses import dataclass, field
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent / "data"
DEFAULT_DB_PATH = DATA_DIR / "admin.db"
_DEFAULT_SALT = "prawdowid-admin"


@dataclass(frozen=True)
class AdminSettings:
    api_token: str | None = field(default=None, repr=False)
    db_path: Path = DEFAULT_DB_PATH
    user_salt: str = field(default=_DEFAULT_SALT, repr=False)
    max_text_length: int = 4000

    @classmethod
    def from_environment(cls) -> AdminSettings:
        return cls(
            api_token=(os.getenv("ADMIN_API_TOKEN") or "").strip() or None,
            db_path=Path(os.getenv("ADMIN_DB_PATH") or DEFAULT_DB_PATH),
            user_salt=os.getenv("ADMIN_USER_SALT") or _DEFAULT_SALT,
        )

    def user_key(self, user_id: str) -> str:
        """Pseudonim użytkownika: HMAC identyfikatora, stały między zapytaniami."""
        digest = hmac.new(self.user_salt.encode(), user_id.strip().encode(), hashlib.sha256)
        return digest.hexdigest()[:16]


def user_label(user_id: str) -> str:
    """Zamaskowany identyfikator do wyświetlenia w panelu (np. numer telefonu)."""
    value = user_id.strip()
    if len(value) <= 4:
        return "***"
    return "***" + value[-3:]
