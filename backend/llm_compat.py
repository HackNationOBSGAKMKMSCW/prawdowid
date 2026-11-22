"""Parametry czatu zgodne z różnymi modelami (OpenAI, Gemini, Ollama).

Kod wysyła ``temperature`` i ``reasoning_effort`` (``"none"`` wyłącza rozumowanie, więc
odpowiedzi są szybsze). Nie każdy model je przyjmuje: na API OpenAI np. gpt-4o/gpt-4.1
odrzucają ``reasoning_effort``, a gpt-5/gpt-5-mini odrzucają ``"none"`` i ``temperature``
inne niż 1. ``create_chat_completion`` przy takim błędzie 400 usuwa ten parametr, ponawia
zapytanie i pamięta to do końca procesu, więc zmiana modelu nie wymaga zmian w kodzie.

``LLM_REASONING_EFFORT`` ustawia wysyłaną wartość: ``none`` (domyślnie), ``minimal``,
``low``, ``medium``, ``high``; pusta albo ``off`` w ogóle jej nie wysyła.
"""

from __future__ import annotations

import logging
import os
from typing import Any

import openai

log = logging.getLogger(__name__)

# Parametry, bez których zapytanie nadal ma sens (kolejność: najpierw rozumowanie).
OPTIONAL_PARAMS = ("reasoning_effort", "temperature")
_rejected: set[tuple[str, str]] = set()


def reasoning_effort() -> str | None:
    """Wartość ``reasoning_effort`` z ``LLM_REASONING_EFFORT`` (``None``: nie wysyłaj)."""
    value = os.getenv("LLM_REASONING_EFFORT", "none").strip().lower()
    return None if value in {"", "off"} else value


def _rejected_param(exc: openai.BadRequestError, kwargs: dict[str, Any]) -> str | None:
    """Opcjonalny parametr, którego dotyczy błąd 400, albo ``None`` (inny błąd)."""
    param = getattr(exc, "param", None)
    if param in OPTIONAL_PARAMS and param in kwargs:
        return param
    message = str(exc).lower()
    for name in OPTIONAL_PARAMS:
        if name in kwargs and name in message:
            return name
    return None


def reset() -> None:
    """Zapomnij odrzucone parametry (testy, zmiana modelu w panelu)."""
    _rejected.clear()


async def create_chat_completion(client: Any, **kwargs: Any) -> Any:
    """``client.chat.completions.create`` bez parametrów, których model nie obsługuje."""
    model = str(kwargs.get("model") or "")
    for name in OPTIONAL_PARAMS:
        if kwargs.get(name) is None or (model, name) in _rejected:
            kwargs.pop(name, None)
    while True:
        try:
            return await client.chat.completions.create(**kwargs)
        except openai.BadRequestError as exc:
            name = _rejected_param(exc, kwargs)
            if name is None:
                raise
            _rejected.add((model, name))
            kwargs.pop(name)
            log.warning("llm_param_unsupported model=%s param=%s: ponawiam bez niego", model, name)
