"""Konfiguracja z zmiennych środowiskowych (te same nazwy co w backend/textAnalysis).

Kolejność (pierwsze wygrywa):
1. zmienne środowiskowe procesu,
2. główny plik projektu `.env`,
3. `backend/.env` – wsteczna kompatybilność ze starszą konfiguracją lokalną.

`load_environment()` wczytuje pliki do `os.environ` bez nadpisywania. Wywołanie jej
PRZED importem pakietów backendu sprawia, że backend (który przy imporcie sam
czyta `.env`) używa tych samych wartości co analysis – ekstrakcja stwierdzeń
i werdykt idą wtedy przez ten sam model.
"""

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

ANALYSIS_DIR = Path(__file__).resolve().parents[2]
PROJECT_ROOT = ANALYSIS_DIR.parent
PROJECT_ENV_FILE = PROJECT_ROOT / ".env"
BACKEND_ENV_FILE = ANALYSIS_DIR.parent / "backend" / ".env"
DEFAULT_MODEL = "gpt-4o-mini"  # ta sama wartość domyślna co w backend/textAnalysis
DEFAULT_MAX_SOURCE_AGE_DAYS = 730  # 2 lata


# Starsze nazwy -> nazwy czytane przez backend/textAnalysis.
LEGACY_ALIASES = {
    "OPENAI_API_KEY": "FREELLM_API_KEY",
    "OPENAI_BASE_URL": "FREELLM_BASE_URL",
    "LLM_MODEL": "FREELLM_MODEL",
    "LLM_TIMEOUT_S": "FREELLM_TIMEOUT",
}


def load_environment(env_file: Path | None = None, backend_env_file: Path | None = None) -> None:
    load_dotenv(env_file or PROJECT_ENV_FILE, override=False)
    load_dotenv(backend_env_file or BACKEND_ENV_FILE, override=False)
    # Backend zna tylko FREELLM_*: przepisujemy starsze nazwy, gdy nowych brak,
    # żeby ekstrakcja stwierdzeń widziała ten sam klucz i model co werdykt.
    for legacy, current in LEGACY_ALIASES.items():
        value = os.environ.get(legacy, "").strip()
        if value and not os.environ.get(current, "").strip():
            os.environ[current] = value


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
    # Źródło starsze (od publikacji) niż limit jest oznaczane jako materiał archiwalny.
    max_source_age_days: int = DEFAULT_MAX_SOURCE_AGE_DAYS

    @classmethod
    def from_environment(
        cls, env_file: Path | None = None, backend_env_file: Path | None = None
    ) -> "Settings":
        """Czyta konfigurację (patrz kolejność w opisie modułu).

        Starsze nazwy `OPENAI_*` / `LLM_MODEL` są akceptowane jako zapasowe.
        """
        load_environment(env_file, backend_env_file)
        return cls(
            api_key=_env("FREELLM_API_KEY", "OPENAI_API_KEY"),
            base_url=_env("FREELLM_BASE_URL", "OPENAI_BASE_URL"),
            model=_env("FREELLM_MODEL", "LLM_MODEL", default=DEFAULT_MODEL) or DEFAULT_MODEL,
            timeout=float(_env("FREELLM_TIMEOUT", "LLM_TIMEOUT_S", default="60") or 60),
            max_retries=int(_env("FREELLM_MAX_RETRIES", default="2") or 2),
            json_mode=_bool(_env("VERDICT_JSON_MODE", default="false")),
            concurrency=max(1, int(_env("VERDICT_CONCURRENCY", default="3") or 3)),
            max_source_age_days=max(
                1,
                int(
                    _env("VERDICT_MAX_SOURCE_AGE_DAYS", default=str(DEFAULT_MAX_SOURCE_AGE_DAYS))
                    or DEFAULT_MAX_SOURCE_AGE_DAYS
                ),
            ),
        )


def backend_model() -> str:
    """Model, którego użyje backend/textAnalysis (czyta tylko FREELLM_MODEL)."""
    return _env("FREELLM_MODEL", default=DEFAULT_MODEL) or DEFAULT_MODEL
