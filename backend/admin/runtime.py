"""Konfiguracja zmieniana przez admina w trakcie działania: modele, kluczowe API, progi.

Plik JSON (domyślnie ``backend/admin/data/runtime_config.json``, ``RUNTIME_CONFIG_FILE``)
przechowuje tylko nadpisania; ``None`` znaczy „jak w środowisku / .env”. Moduły backendu
czytają ustawienia przez ``Settings.from_environment()`` przy każdym zapytaniu, a ta
najpierw woła :func:`apply_runtime_overrides` — zmiana działa więc bez restartu, także w
innym procesie niż panel admina (plik jest czytany ponownie, gdy zmieni się jego mtime albo i-węzeł).

Moduł nie importuje FastAPI ani klientów API, żeby ``textAnalysis.settings`` mógł go
importować bez cykli.
"""

from __future__ import annotations

import contextlib
import json
import os
import re
import tempfile
import threading
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator

DEFAULT_RUNTIME_FILE = Path(__file__).resolve().parent / "data" / "runtime_config.json"
RUNTIME_FILE_ENV = "RUNTIME_CONFIG_FILE"

_MODEL_NAME = re.compile(r"^[A-Za-z0-9._:/@+-]{1,128}$")


class _Section(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class LlmConfig(_Section):
    model: str | None = Field(
        default=None, description="Model główny (FREELLM_MODEL): textAnalysis i werdykt"
    )
    text_analysis_model: str | None = Field(
        default=None, description="Osobny model tylko dla textAnalysis (TEXT_ANALYSIS_MODEL)"
    )
    base_url: str | None = Field(default=None, description="Endpoint OpenAI-compatible")
    timeout_s: float | None = Field(default=None, ge=1, le=600)
    max_retries: int | None = Field(default=None, ge=0, le=10)

    @field_validator("model", "text_analysis_model")
    @classmethod
    def _model_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not _MODEL_NAME.match(value):
            raise ValueError("nazwa modelu: 1-128 znaków [A-Za-z0-9._:/@+-]")
        return value

    @field_validator("base_url")
    @classmethod
    def _url(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not re.match(r"^https?://[^\s/]+", value):
            raise ValueError("base_url musi zaczynać się od http:// lub https://")
        return value.rstrip("/")


class ApiConfig(_Section):
    disabled_clients: list[str] | None = Field(
        default=None, description="Klienci apiReading wyłączeni z wyszukiwania (np. sejm, eurlex)"
    )
    article_scraping_enabled: bool | None = None
    article_extractor: Literal["local", "diffbot"] | None = None

    @field_validator("disabled_clients")
    @classmethod
    def _names(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        return sorted({name.strip().lower() for name in value if name.strip()})


class SecretsConfig(_Section):
    """Klucze tylko do zapisu: API nigdy ich nie zwraca, pokazuje jedynie maskę."""

    freellm_api_key: SecretStr | None = None
    google_fact_check_api_key: SecretStr | None = None
    diffbot_api_token: SecretStr | None = None

    @field_validator("*", mode="before")
    @classmethod
    def _empty_is_unset(cls, value: Any) -> Any:
        return None if isinstance(value, str) and not value.strip() else value


class MonitoringConfig(_Section):
    info_gap_count_by: Literal["auto", "zapytania", "osoby"] = Field(
        default="auto",
        description=(
            "Nieużywane (zgodność ze starszymi plikami): bez danych o użytkownikach luka liczy "
            "zawsze zapytania, próg info_gap_min_queries"
        ),
    )
    info_gap_min_queries: int = Field(default=3, ge=1, le=100_000)
    info_gap_min_users: int = Field(default=3, ge=1, le=10_000)
    info_gap_window_hours: int = Field(default=168, ge=1, le=24 * 365)
    # nazwa historyczna: liczone są zapytania o twierdzenie ocenione jako fałsz
    disinfo_min_users: int = Field(default=5, ge=2, le=100_000)
    disinfo_window_hours: int = Field(default=24, ge=1, le=24 * 90)
    dangerous_alert_after: int = Field(default=3, ge=1, le=1000)
    dangerous_block_after: int = Field(default=2, ge=1, le=1000)
    dangerous_window_hours: int = Field(default=24, ge=1, le=24 * 90)
    dangerous_block_hours: int = Field(default=24, ge=1, le=24 * 365)
    injection_alert_after: int = Field(
        default=1,
        ge=1,
        le=1000,
        description="Nieużywane (zgodność): każda próba prompt injection trafia do alertu",
    )
    # Blokada adresu IP po próbach prompt injection (strona WWW; WhatsApp nie ma adresu IP).
    injection_block_ip: bool = True
    injection_block_after: int = Field(
        default=1, ge=1, le=1000, description="Prób z jednego adresu w oknie dangerous_window_hours"
    )
    injection_block_hours: int = Field(default=24, ge=1, le=24 * 365)
    auto_block: bool = True  # nieużywane (zgodność): blokady osób usunięto
    refuse_high_risk: bool = True
    retention_days: int = Field(default=30, ge=1, le=3650)


class RuntimeConfig(_Section):
    llm: LlmConfig = Field(default_factory=LlmConfig)
    apis: ApiConfig = Field(default_factory=ApiConfig)
    secrets: SecretsConfig = Field(default_factory=SecretsConfig)
    monitoring: MonitoringConfig = Field(default_factory=MonitoringConfig)


# ścieżka pola -> zmienna środowiskowa czytana przez backend
ENV_MAP: dict[tuple[str, str], str] = {
    ("llm", "model"): "FREELLM_MODEL",
    ("llm", "text_analysis_model"): "TEXT_ANALYSIS_MODEL",
    ("llm", "base_url"): "FREELLM_BASE_URL",
    ("llm", "timeout_s"): "FREELLM_TIMEOUT",
    ("llm", "max_retries"): "FREELLM_MAX_RETRIES",
    ("apis", "disabled_clients"): "API_READING_DISABLED_CLIENTS",
    ("apis", "article_scraping_enabled"): "ARTICLE_SCRAPING_ENABLED",
    ("apis", "article_extractor"): "ARTICLE_EXTRACTOR",
    ("secrets", "freellm_api_key"): "FREELLM_API_KEY",
    ("secrets", "google_fact_check_api_key"): "GOOGLE_FACT_CHECK_API_KEY",
    ("secrets", "diffbot_api_token"): "DIFFBOT_API_TOKEN",
}
SECRET_SECTION = "secrets"


def mask(secret: str | None) -> str | None:
    if not secret:
        return None
    return "****" + secret[-4:] if len(secret) >= 12 else "****"


def _env_value(value: Any) -> str:
    if isinstance(value, SecretStr):
        return value.get_secret_value()
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, list):
        return ",".join(value)
    return str(value)


def runtime_file() -> Path:
    return Path(os.getenv(RUNTIME_FILE_ENV) or DEFAULT_RUNTIME_FILE)


class RuntimeConfigStore:
    """Odczyt i zapis pliku nadpisań; zapis atomowy (plik tymczasowy + replace)."""

    def __init__(self, path: Path | None = None) -> None:
        self._explicit = path
        self._lock = threading.Lock()
        # (plik, wersja, konfiguracja); wersja = mtime + i-węzeł: zapis robi os.replace,
        # więc nowy plik ma nowy i-węzeł nawet przy tym samym znaczniku czasu.
        self._cache: tuple[Path, tuple[int, int, int], RuntimeConfig] | None = None

    @property
    def path(self) -> Path:
        return self._explicit or runtime_file()

    def load(self) -> RuntimeConfig:
        path = self.path
        try:
            stat = path.stat()
        except OSError:
            return RuntimeConfig()
        version = (stat.st_mtime_ns, stat.st_ino, stat.st_size)
        cached = self._cache
        if cached and cached[0] == path and cached[1] == version:
            return cached[2]
        try:
            config = RuntimeConfig.model_validate(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            return cached[2] if cached and cached[0] == path else RuntimeConfig()
        self._cache = (path, version, config)
        return config

    def save(self, config: RuntimeConfig) -> None:
        path = self.path
        path.parent.mkdir(parents=True, exist_ok=True)
        data = config.model_dump(mode="python")
        for name, value in data[SECRET_SECTION].items():
            data[SECRET_SECTION][name] = value.get_secret_value() if value else None
        with self._lock:
            fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".runtime-", suffix=".json")
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as handle:
                    json.dump(data, handle, ensure_ascii=False, indent=2)
                os.replace(tmp, path)
            finally:
                with contextlib.suppress(OSError):
                    os.unlink(tmp)
            self._cache = None

    def update(self, patch: dict[str, Any]) -> tuple[RuntimeConfig, list[dict[str, Any]]]:
        """Scal częściową zmianę (sekcja -> pola); zwraca nową konfigurację i listę zmian.

        Nieznane sekcje i pola są błędem walidacji. W liście zmian sekrety są maskowane.
        """
        current = self.load()
        merged = current.model_dump(mode="python")
        for section, fields in patch.items():
            if section not in merged or not isinstance(fields, dict):
                raise ValueError(f"nieznana sekcja konfiguracji: {section}")
            for name, value in fields.items():
                if name not in merged[section]:
                    raise ValueError(f"nieznane pole konfiguracji: {section}.{name}")
                merged[section][name] = value
        updated = RuntimeConfig.model_validate(merged)
        changes = diff(current, updated)
        if changes:
            self.save(updated)
        return updated, changes


def _plain(section: str, value: Any) -> Any:
    if section == SECRET_SECTION:
        return mask(value.get_secret_value()) if value else None
    return value


def diff(old: RuntimeConfig, new: RuntimeConfig) -> list[dict[str, Any]]:
    changes = []
    for section in ("llm", "apis", "secrets", "monitoring"):
        before, after = getattr(old, section), getattr(new, section)
        for name in type(after).model_fields:
            left, right = getattr(before, name), getattr(after, name)
            if section == SECRET_SECTION:
                same = (left.get_secret_value() if left else None) == (
                    right.get_secret_value() if right else None
                )
            else:
                same = left == right
            if not same:
                changes.append(
                    {
                        "field": f"{section}.{name}",
                        "old": _plain(section, left),
                        "new": _plain(section, right),
                    }
                )
    return changes


def public_view(config: RuntimeConfig) -> dict[str, Any]:
    """Konfiguracja do pokazania w panelu: nadpisania, wartości efektywne, maski sekretów."""
    view: dict[str, Any] = {}
    for section in ("llm", "apis", "monitoring"):
        view[section] = getattr(config, section).model_dump(mode="json")
    view["secrets"] = {
        name: {
            "nadpisany": getattr(config.secrets, name) is not None,
            "ustawiony": bool(os.getenv(ENV_MAP[(SECRET_SECTION, name)])),
            "maska": mask(os.getenv(ENV_MAP[(SECRET_SECTION, name)])),
        }
        for name in SecretsConfig.model_fields
    }
    view["efektywne"] = {
        env: (mask(os.getenv(env)) if section == SECRET_SECTION else os.getenv(env))
        for (section, _), env in ENV_MAP.items()
    }
    return view


# --- nakładanie nadpisań na os.environ -------------------------------------------------

_default_store = RuntimeConfigStore()
_originals: dict[str, str | None] = {}
_apply_lock = threading.Lock()


def apply_config(config: RuntimeConfig) -> None:
    """Ustaw zmienne środowiskowe z nadpisań; zdjęte nadpisanie przywraca wartość pierwotną."""
    with _apply_lock:
        for (section, name), env in ENV_MAP.items():
            value = getattr(getattr(config, section), name)
            if value is not None:
                _originals.setdefault(env, os.environ.get(env))
                os.environ[env] = _env_value(value)
            elif env in _originals:
                original = _originals.pop(env)
                if original is None:
                    os.environ.pop(env, None)
                else:
                    os.environ[env] = original


def apply_runtime_overrides(store: RuntimeConfigStore | None = None) -> None:
    """Wywoływane przez ``Settings.from_environment()``; nigdy nie rzuca wyjątku."""
    with contextlib.suppress(Exception):
        apply_config((store or _default_store).load())
