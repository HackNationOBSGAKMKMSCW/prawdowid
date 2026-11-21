"""Klient LLM przez API zgodne z OpenAI (`POST {base_url}/chat/completions`).

Konfiguracja wyłącznie z analysis/.env (CONTRIBUTING.md, sekcja 5): `OPENAI_BASE_URL`,
`OPENAI_API_KEY`, `LLM_MODEL`, opcjonalnie `LLM_TIMEOUT_S`. Nazwa modelu nie jest wpisana
w kodzie. Każda awaria (brak konfiguracji, timeout, błąd dostawcy, pusta odpowiedź) to
`LLMError`, który potok zamienia na status `error`, nigdy na werdykt.

Funkcje wołające model (np. `stance.py`) przyjmują klienta jako parametr (`ChatClient`),
więc w testach podstawia się atrapę bez sieci.
"""

import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import httpx
from dotenv import load_dotenv

# analysis/.env: trzy poziomy nad tym plikiem (verdict -> prawdowid_analysis -> src -> analysis)
_ENV_PATH = Path(__file__).resolve().parents[3] / ".env"


class LLMError(Exception):
    """Błąd techniczny LLM: brak konfiguracji, niedostępny serwer, timeout, zła odpowiedź API."""


@dataclass(frozen=True)
class LLMSettings:
    base_url: str
    model: str
    api_key: str | None = None
    timeout_s: float = 60.0

    @classmethod
    def from_env(cls) -> "LLMSettings":
        load_dotenv(_ENV_PATH, override=False)

        def env(name: str) -> str:
            return (os.getenv(name) or "").strip()

        base_url, model = env("OPENAI_BASE_URL"), env("LLM_MODEL")
        missing = [n for n, v in (("OPENAI_BASE_URL", base_url), ("LLM_MODEL", model)) if not v]
        if missing:
            raise LLMError(f"Brak konfiguracji LLM w analysis/.env: {', '.join(missing)}")
        return cls(
            base_url=base_url.rstrip("/"),
            model=model,
            api_key=env("OPENAI_API_KEY") or None,
            timeout_s=float(env("LLM_TIMEOUT_S") or "60"),
        )


@dataclass(frozen=True)
class LLMResult:
    text: str
    model: str
    tokens_in: int
    tokens_out: int
    duration_ms: int

    def as_run_model(self) -> dict:
        """Wpis do `run.models` z CONTRACTS.md."""
        return {"name": self.model, "tokens_in": self.tokens_in, "tokens_out": self.tokens_out}


class ChatClient(Protocol):
    model: str

    def chat(
        self,
        messages: list[dict],
        *,
        json_mode: bool = False,
        temperature: float = 0.0,
        max_tokens: int | None = None,
    ) -> LLMResult: ...


class OpenAIChatClient:
    """Minimalny klient `/chat/completions` na httpx (bez SDK dostawcy)."""

    def __init__(self, settings: LLMSettings, http: httpx.Client | None = None) -> None:
        self.settings = settings
        self.model = settings.model
        headers = {"Authorization": f"Bearer {settings.api_key}"} if settings.api_key else {}
        self._http = http or httpx.Client(
            base_url=settings.base_url, headers=headers, timeout=settings.timeout_s
        )

    @classmethod
    def from_env(cls) -> "OpenAIChatClient":
        return cls(LLMSettings.from_env())

    def chat(
        self,
        messages: list[dict],
        *,
        json_mode: bool = False,
        temperature: float = 0.0,
        max_tokens: int | None = None,
    ) -> LLMResult:
        body: dict = {"model": self.model, "messages": messages, "temperature": temperature}
        if max_tokens:
            body["max_tokens"] = max_tokens
        if json_mode:
            body["response_format"] = {"type": "json_object"}

        started = time.perf_counter()
        try:
            resp = self._http.post("/chat/completions", json=body)
            resp.raise_for_status()
            data = resp.json()
        except httpx.HTTPStatusError as exc:
            raise LLMError(f"LLM zwrócił HTTP {exc.response.status_code}") from exc
        except (httpx.HTTPError, ValueError) as exc:
            raise LLMError(f"Błąd wywołania LLM: {type(exc).__name__}") from exc
        duration_ms = int((time.perf_counter() - started) * 1000)

        choices = data.get("choices") or []
        if not choices:
            raise LLMError("LLM zwrócił pustą odpowiedź")
        usage = data.get("usage") or {}
        return LLMResult(
            text=(choices[0].get("message") or {}).get("content") or "",
            model=data.get("model") or self.model,
            tokens_in=int(usage.get("prompt_tokens") or 0),
            tokens_out=int(usage.get("completion_tokens") or 0),
            duration_ms=duration_ms,
        )

    def list_models(self) -> list[str]:
        try:
            resp = self._http.get("/models")
            resp.raise_for_status()
            return sorted(m["id"] for m in resp.json().get("data", []))
        except (httpx.HTTPError, ValueError, KeyError) as exc:
            raise LLMError(f"Nie udało się pobrać listy modeli: {type(exc).__name__}") from exc
