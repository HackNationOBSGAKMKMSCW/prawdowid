"""Klient LLM przez API zgodne z OpenAI (Ollama, vLLM, dostawca chmurowy...).

Konfiguracja wyłącznie ze zmiennych środowiskowych (CONTRIBUTING.md, sekcja 5):
`OPENAI_BASE_URL`, `OPENAI_API_KEY`, `LLM_MODEL`, opcjonalnie `LLM_TIMEOUT_S`.
Nazwa modelu nie jest wpisana w kodzie. Każda awaria (brak konfiguracji, timeout,
błąd dostawcy) to `LLMError`, który API zamienia na status `error`, nigdy na werdykt.
"""

import os
import time
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI, OpenAIError

load_dotenv(Path(__file__).with_name(".env"))


class LLMError(Exception):
    """Błąd techniczny LLM: brak konfiguracji, niedostępny serwer, timeout."""


@dataclass(frozen=True)
class LLMSettings:
    base_url: str
    api_key: str
    model: str
    timeout_s: float

    @classmethod
    def from_env(cls) -> "LLMSettings":
        base_url = os.getenv("OPENAI_BASE_URL", "").strip()
        model = os.getenv("LLM_MODEL", "").strip()
        missing = [n for n, v in (("OPENAI_BASE_URL", base_url), ("LLM_MODEL", model)) if not v]
        if missing:
            raise LLMError(f"Brak konfiguracji LLM: {', '.join(missing)}")
        return cls(
            base_url=base_url,
            # Ollama nie sprawdza klucza, ale klient OpenAI wymaga niepustej wartości.
            api_key=os.getenv("OPENAI_API_KEY", "").strip() or "none",
            model=model,
            timeout_s=float(os.getenv("LLM_TIMEOUT_S", "60")),
        )


@dataclass
class LLMResult:
    text: str
    model: str
    tokens_in: int
    tokens_out: int
    duration_ms: int

    def as_run_model(self) -> dict:
        """Wpis do `run.models` z CONTRACTS.md."""
        return {"name": self.model, "tokens_in": self.tokens_in, "tokens_out": self.tokens_out}


def get_client(settings: LLMSettings | None = None) -> tuple[OpenAI, LLMSettings]:
    settings = settings or LLMSettings.from_env()
    client = OpenAI(
        base_url=settings.base_url,
        api_key=settings.api_key,
        timeout=settings.timeout_s,
        max_retries=1,
    )
    return client, settings


def chat(
    messages: list[dict],
    *,
    json_mode: bool = False,
    temperature: float = 0.0,
    max_tokens: int | None = None,
    client: OpenAI | None = None,
    settings: LLMSettings | None = None,
) -> LLMResult:
    if client is None:
        client, settings = get_client(settings)
    settings = settings or LLMSettings.from_env()
    kwargs: dict = {"model": settings.model, "messages": messages, "temperature": temperature}
    if max_tokens:
        kwargs["max_tokens"] = max_tokens
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}

    started = time.perf_counter()
    try:
        resp = client.chat.completions.create(**kwargs)
    except OpenAIError as exc:
        raise LLMError(f"Błąd wywołania LLM: {type(exc).__name__}") from exc
    duration_ms = int((time.perf_counter() - started) * 1000)

    if not resp.choices:
        raise LLMError("LLM zwrócił pustą odpowiedź")
    usage = resp.usage
    return LLMResult(
        text=resp.choices[0].message.content or "",
        model=resp.model or settings.model,
        tokens_in=usage.prompt_tokens if usage else 0,
        tokens_out=usage.completion_tokens if usage else 0,
        duration_ms=duration_ms,
    )


def health() -> dict:
    """Sprawdza, czy serwer LLM odpowiada i czy skonfigurowany model jest dostępny."""
    try:
        client, settings = get_client()
    except LLMError as exc:
        return {"status": "not_configured", "detail": str(exc)}
    try:
        available = sorted(m.id for m in client.models.list())
    except OpenAIError as exc:
        return {"status": "unreachable", "model": settings.model, "detail": type(exc).__name__}
    if settings.model not in available:
        return {"status": "model_missing", "model": settings.model, "available": available}
    return {"status": "ok", "model": settings.model}
