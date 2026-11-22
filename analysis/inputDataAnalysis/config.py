"""Konfiguracja LLM ze wspólnego pliku projektu lub zmiennych środowiskowych."""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import cache
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ENV_PATH = PROJECT_ROOT / ".env"
LEGACY_ENV_PATH = PROJECT_ROOT / "backend" / ".env"


@dataclass(frozen=True)
class Settings:
    api_key: str
    base_url: str
    model: str
    timeout: float = 60.0
    temperature: float = 0.1
    max_retries: int = 5  # SDK ponawia 429/5xx z wykładniczym odstępem


@cache
def _load_env_files() -> None:
    load_dotenv(ENV_PATH, override=False)
    # Starsze nazwy LLM_* pozostają akceptowane, by nie blokować dotychczasowych .env.
    load_dotenv(LEGACY_ENV_PATH, override=False)


def _apply_admin_overrides() -> None:
    """Model, klucz i adres API zmienione w panelu admina (``backend/admin/runtime.py``)."""
    try:
        from admin.runtime import apply_runtime_overrides
    except ImportError:  # analiza uruchomiona bez backendu
        return
    apply_runtime_overrides()


def get_settings() -> Settings:
    """Czytane przy każdym wywołaniu: zmiana modelu w panelu działa bez restartu.

    Pliki ``.env`` są wczytywane raz; nadpisania z panelu (plik ``runtime_config.json``,
    czytany ponownie tylko po zmianie) są nakładane na ``os.environ`` przy każdym wywołaniu.
    """
    _load_env_files()
    _apply_admin_overrides()
    api_key = os.getenv("FREELLM_API_KEY") or os.getenv("LLM_API_KEY")
    base_url = os.getenv("FREELLM_BASE_URL") or os.getenv("LLM_BASE_URL")
    model = os.getenv("FREELLM_MODEL") or os.getenv("LLM_MODEL")
    missing = [
        name
        for name, value in (
            ("FREELLM_API_KEY", api_key),
            ("FREELLM_BASE_URL", base_url),
            ("FREELLM_MODEL", model),
        )
        if not value
    ]
    if missing:
        raise RuntimeError(
            f"Brak zmiennych {', '.join(missing)}. Uzupełnij {ENV_PATH} (wzór: .env.example)."
        )
    return Settings(
        api_key=api_key or "",
        base_url=base_url or "",
        model=model or "",
        timeout=float(os.getenv("LLM_TIMEOUT", "60")),
        temperature=float(os.getenv("LLM_TEMPERATURE", "0.1")),
        max_retries=int(os.getenv("LLM_MAX_RETRIES", "5")),
    )
