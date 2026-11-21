"""Klient modelu językowego (API zgodne z OpenAI) i parsowanie odpowiedzi JSON.

`ChatClient` to protokół: w testach podstawiamy atrapę, więc nic nie wymaga sieci.
Awaria techniczna (sieć, limit, błąd API) to `LLMError` i NIE jest zamieniana na
werdykt „brak danych”: potok zwraca wtedy jawny `blad_analizy`.
"""

import json
import re
from dataclasses import dataclass
from typing import Any, Protocol

from openai import AsyncOpenAI, OpenAIError

from .config import Settings

Message = dict[str, str]

_THINK_RE = re.compile(r"<think>.*?(</think>|$)", re.DOTALL | re.IGNORECASE)
_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE)


class LLMError(RuntimeError):
    """Model nie odpowiedział z przyczyn technicznych."""


class LLMConfigurationError(LLMError):
    """Brak wymaganej konfiguracji modelu."""


@dataclass(frozen=True)
class LLMReply:
    content: str
    model: str | None = None


class ChatClient(Protocol):
    async def complete(self, messages: list[Message]) -> LLMReply: ...


class OpenAIChatClient:
    """Klient `AsyncOpenAI` z temperaturą 0 (powtarzalność werdyktów)."""

    def __init__(self, settings: Settings, *, client: AsyncOpenAI | None = None):
        if client is None and not settings.api_key:
            raise LLMConfigurationError("Ustaw FREELLM_API_KEY, aby uruchomić werdykt.")
        self._client = client or AsyncOpenAI(
            api_key=settings.api_key,
            base_url=settings.base_url,
            timeout=settings.timeout,
            max_retries=settings.max_retries,
        )
        self._owns_client = client is None
        self.model = settings.model
        self.json_mode = settings.json_mode

    async def complete(self, messages: list[Message]) -> LLMReply:
        kwargs: dict[str, Any] = {"model": self.model, "messages": messages, "temperature": 0}
        if self.json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        try:
            response = await self._client.chat.completions.create(**kwargs)
        except OpenAIError as exc:
            raise LLMError(f"Błąd wywołania modelu: {type(exc).__name__}") from exc
        if not response.choices:
            raise LLMError("Model nie zwrócił żadnej odpowiedzi.")
        return LLMReply(
            content=response.choices[0].message.content or "",
            model=getattr(response, "model", None) or self.model,
        )

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.close()


def parse_json_object(raw: str) -> dict[str, Any]:
    """Wyciąga obiekt JSON z odpowiedzi modelu.

    Toleruje blok rozumowania `<think>`, ogrodzenie markdown oraz tekst wokół
    obiektu. Zgłasza `ValueError`, gdy obiektu nie da się odczytać.
    """
    text = _THINK_RE.sub("", raw or "").strip()
    text = _FENCE_RE.sub("", text).strip()
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start == -1 or end <= start:
            raise ValueError("Odpowiedź nie zawiera obiektu JSON.") from None
        try:
            value = json.loads(text[start : end + 1])
        except json.JSONDecodeError as exc:
            raise ValueError(f"Niepoprawny JSON: {exc.msg}") from None
    if not isinstance(value, dict):
        raise ValueError("Odpowiedź JSON nie jest obiektem.")
    return value
