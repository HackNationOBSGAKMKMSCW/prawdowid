"""Konfiguracja z zmiennych środowiskowych (te same nazwy co w backend/textAnalysis)."""

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

ANALYSIS_DIR = Path(__file__).resolve().parents[2]


def _env(name: str, *fallbacks: str, default: str | None = None) -> str | None:
    for key in (name, *fallbacks):
        value = os.getenv(key)
        if value is not None and value.strip():
            return value.strip()
    return default


def _bool(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "tak", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    api_key: str | None
    base_url: str | None
    model: str
    timeout: float
    max_retries: int
    json_mode: bool
    concurrency: int

    @classmethod
    def from_environment(cls, env_file: Path | None = None) -> "Settings":
        """Czyta `analysis/.env` (jeśli istnieje), potem zmienne środowiskowe.

        Starsze nazwy `OPENAI_*` / `LLM_MODEL` są akceptowane jako zapasowe.
        """
        load_dotenv(env_file or ANALYSIS_DIR / ".env", override=False)
        return cls(
            api_key=_env("FREELLM_API_KEY", "OPENAI_API_KEY"),
            base_url=_env("FREELLM_BASE_URL", "OPENAI_BASE_URL"),
            model=_env("FREELLM_MODEL", "LLM_MODEL", default="gpt-4o-mini") or "gpt-4o-mini",
            timeout=float(_env("FREELLM_TIMEOUT", "LLM_TIMEOUT_S", default="60") or 60),
            max_retries=int(_env("FREELLM_MAX_RETRIES", default="2") or 2),
            json_mode=_bool(_env("VERDICT_JSON_MODE", default="false")),
            concurrency=max(1, int(_env("VERDICT_CONCURRENCY", default="3") or 3)),
        )
