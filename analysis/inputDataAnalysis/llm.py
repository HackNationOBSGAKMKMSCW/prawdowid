"""Klient LLM zgodny z OpenAI (np. Gemini przez ``/v1beta/openai/``) ze strukturalnym wyjściem.

``structured_call`` wysyła ``response_format=json_schema``, waliduje odpowiedź Pydanticiem i przy
błędzie walidacji ponawia raz, podając modelowi błąd. Gdy endpoint odrzuci schemat (400),
przełącza się na ``json_object`` ze schematem wklejonym do promptu.
"""

from __future__ import annotations

import copy
import json
import logging
import re
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

import openai
from openai import AsyncOpenAI
from pydantic import BaseModel, ValidationError

from .config import Settings, get_settings

log = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)
# Sygnatura: (system, user, schema) -> instancja schema. Testy podstawiają tu atrapę.
StructuredCall = Callable[[str, str, type[BaseModel]], Awaitable[Any]]


class LLMError(RuntimeError):
    """LLM nie zwrócił poprawnej odpowiedzi."""


_clients: dict[Settings, AsyncOpenAI] = {}
_json_schema_unsupported = False


def _client(settings: Settings) -> AsyncOpenAI:
    # Klient HTTP jest związany z pętlą zdarzeń; synchroniczne analyze() zamyka go po każdym
    # asyncio.run przez reset_clients().
    if settings not in _clients:
        _clients[settings] = AsyncOpenAI(
            api_key=settings.api_key,
            base_url=settings.base_url,
            timeout=settings.timeout,
            max_retries=settings.max_retries,
        )
    return _clients[settings]


async def reset_clients() -> None:
    """Zamyka klientów HTTP (wywoływane po zakończeniu ``asyncio.run``)."""
    clients = list(_clients.values())
    _clients.clear()
    for c in clients:
        await c.close()


def inline_schema(model: type[BaseModel]) -> dict[str, Any]:
    """JSON Schema modelu bez ``$ref``/``$defs``, ``title`` i ``default``."""
    schema = model.model_json_schema()
    defs = schema.pop("$defs", {})

    def resolve(node: Any) -> Any:
        if isinstance(node, list):
            return [resolve(n) for n in node]
        if not isinstance(node, dict):
            return node
        if "$ref" in node:
            target = copy.deepcopy(defs[node["$ref"].split("/")[-1]])
            extra = {k: v for k, v in node.items() if k != "$ref"}
            return resolve({**target, **extra})
        out: dict[str, Any] = {}
        for key, value in node.items():
            if key in ("title", "default"):
                continue
            if key == "properties":
                out[key] = {name: resolve(sub) for name, sub in value.items()}
            else:
                out[key] = resolve(value)
        return out

    return resolve(schema)


_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE)


def _extract_json(content: str) -> str:
    text = _FENCE.sub("", content.strip())
    if not text.startswith("{"):
        start, end = text.find("{"), text.rfind("}")
        if start != -1 and end > start:
            text = text[start : end + 1]
    return text


async def structured_call(
    system: str,
    user: str,
    schema: type[T],
    *,
    settings: Settings | None = None,
) -> T:
    """Wywołuje LLM i zwraca odpowiedź zwalidowaną jako ``schema``."""
    settings = settings or get_settings()
    client = _client(settings)
    json_schema = inline_schema(schema)

    messages: list[dict[str, str]] = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]

    async def send(msgs: list[dict[str, str]]) -> str:
        global _json_schema_unsupported
        if not _json_schema_unsupported:
            try:
                resp = await client.chat.completions.create(
                    model=settings.model,
                    messages=msgs,
                    temperature=settings.temperature,
                    reasoning_effort="none",
                    response_format={
                        "type": "json_schema",
                        "json_schema": {"name": schema.__name__, "schema": json_schema},
                    },
                    reasoning_effort="none",
                )
                return resp.choices[0].message.content or ""
            except openai.BadRequestError as exc:
                log.warning("Endpoint odrzucił json_schema (%s); przechodzę na json_object.", exc)
                _json_schema_unsupported = True
        fallback = [
            {
                "role": "system",
                "content": msgs[0]["content"]
                + "\n\nZwróć WYŁĄCZNIE obiekt JSON zgodny z tym schematem:\n"
                + json.dumps(json_schema, ensure_ascii=False),
            },
            *msgs[1:],
        ]
        resp = await client.chat.completions.create(
            model=settings.model,
            messages=fallback,
            temperature=settings.temperature,
            reasoning_effort="none",
            response_format={"type": "json_object"},
            reasoning_effort="none",
        )
        return resp.choices[0].message.content or ""

    content = ""
    for attempt in range(2):
        try:
            content = await send(messages)
        except openai.APIError as exc:
            raise LLMError(f"Błąd wywołania LLM: {exc}") from exc
        try:
            return schema.model_validate_json(_extract_json(content))
        except ValidationError as exc:
            if attempt == 1:
                raise LLMError(f"Odpowiedź LLM nie przeszła walidacji: {exc}") from exc
            log.info("Odpowiedź LLM nie przeszła walidacji, ponawiam: %s", exc)
            messages = [
                *messages,
                {"role": "assistant", "content": content},
                {
                    "role": "user",
                    "content": "Ta odpowiedź nie przeszła walidacji schematu:\n"
                    f"{exc}\nZwróć poprawiony, kompletny obiekt JSON.",
                },
            ]
    raise LLMError("Nieosiągalne")  # pragma: no cover
