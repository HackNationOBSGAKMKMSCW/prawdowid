"""Konfiguracja LLM z pliku ``backend/.env`` (lub ze zmiennych środowiskowych)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import cache
from pathlib import Path

from dotenv import load_dotenv

ENV_PATH = Path(__file__).resolve().parent.parent / ".env"


@dataclass(frozen=True)
class Settings:
    api_key: str
    base_url: str
    model: str
    timeout: float = 60.0
    temperature: float = 0.1
    max_retries: int = 5  # SDK ponawia 429/5xx z wykładniczym odstępem


@cache
def get_settings() -> Settings:
    load_dotenv(ENV_PATH, override=False)
    missing = [k for k in ("LLM_API_KEY", "LLM_BASE_URL", "LLM_MODEL") if not os.getenv(k)]
    if missing:
        raise RuntimeError(
            f"Brak zmiennych {', '.join(missing)}. Uzupełnij {ENV_PATH} (wzór: backend/.env.example)."
        )
    return Settings(
        api_key=os.environ["LLM_API_KEY"],
        base_url=os.environ["LLM_BASE_URL"],
        model=os.environ["LLM_MODEL"],
        timeout=float(os.getenv("LLM_TIMEOUT", "60")),
        temperature=float(os.getenv("LLM_TEMPERATURE", "0.1")),
        max_retries=int(os.getenv("LLM_MAX_RETRIES", "5")),
    )
