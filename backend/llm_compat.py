"""Parametry czatu zgodne z różnymi modelami (OpenAI, Gemini, Ollama).

Kod wysyła ``temperature`` i ``reasoning_effort`` (``"none"`` wyłącza rozumowanie, więc
odpowiedzi są szybsze). Nie każdy model je przyjmuje: na API OpenAI np. gpt-4o/gpt-4.1
odrzucają ``reasoning_effort``, gpt-5-mini odrzuca ``"none"`` i ``temperature`` inne niż 1,
a gpt-6.2-sol odrzuca ``"none"`` (najniższy poziom to ``"low"``). ``create_chat_completion``
przy takim błędzie 400 schodzi do najniższego przyjmowanego poziomu rozumowania
(``none`` → ``minimal`` → ``low``), a gdy żaden nie przejdzie albo odrzucony jest inny
parametr, usuwa go. Wynik pamięta dla modelu do końca procesu, więc zmiana modelu nie
wymaga zmian w kodzie. Na Vercelu każda nowa instancja uczy się od nowa, dlatego dla
znanego modelu lepiej od razu ustawić ``LLM_REASONING_EFFORT`` (np. ``low``).

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
# Kolejne, coraz wyższe poziomy rozumowania do wypróbowania, gdy model odrzuca niższy.
_EFFORT_LADDER = ("none", "minimal", "low")
_rejected: set[tuple[str, str]] = set()
_effort_override: dict[str, str] = {}


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
    """Zapomnij odrzucone parametry (testy)."""
    _rejected.clear()
    _effort_override.clear()


def _next_effort(current: Any) -> str | None:
    """Następny poziom z drabiny po odrzuconym ``current`` (``None``: brak, usuń parametr)."""
    if current not in _EFFORT_LADDER:
        return None
    index = _EFFORT_LADDER.index(current)
    return _EFFORT_LADDER[index + 1] if index + 1 < len(_EFFORT_LADDER) else None


async def create_chat_completion(client: Any, **kwargs: Any) -> Any:
    """``client.chat.completions.create`` bez parametrów, których model nie obsługuje."""
    model = str(kwargs.get("model") or "")
    requested, override = kwargs.get("reasoning_effort"), _effort_override.get(model)
    # Tylko w górę: jawnie wyższy poziom (np. LLM_REASONING_EFFORT=high) zostaje.
    if (
        requested in _EFFORT_LADDER
        and override
        and _EFFORT_LADDER.index(override) > _EFFORT_LADDER.index(requested)
    ):
        kwargs["reasoning_effort"] = override
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
            if name == "reasoning_effort" and (effort := _next_effort(kwargs[name])):
                _effort_override[model] = effort
                log.warning(
                    "llm_param_unsupported model=%s reasoning_effort=%s: ponawiam z %s",
                    model,
                    kwargs[name],
                    effort,
                )
                kwargs[name] = effort
                continue
            _rejected.add((model, name))
            kwargs.pop(name)
            log.warning("llm_param_unsupported model=%s param=%s: ponawiam bez niego", model, name)
