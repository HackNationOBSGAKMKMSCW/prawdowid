"""Atrapy do testów: klient LLM ze skryptem odpowiedzi i fabryki danych."""

import json
from typing import Any

from prawdowid_analysis.llm import LLMError, LLMReply, Message
from prawdowid_analysis.schemas import ReferenceSource


class FakeChatClient:
    """Zwraca kolejne odpowiedzi ze skryptu; `LLMError` w skrypcie jest zgłaszany."""

    def __init__(self, *replies: str | dict | Exception, model: str = "atrapa"):
        self.replies = list(replies)
        self.calls: list[list[Message]] = []
        self.model = model

    async def complete(self, messages: list[Message]) -> LLMReply:
        self.calls.append([dict(m) for m in messages])
        if not self.replies:
            raise AssertionError("Atrapa nie ma więcej odpowiedzi")
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        if isinstance(reply, dict):
            reply = json.dumps(reply, ensure_ascii=False)
        return LLMReply(content=reply, model=self.model)


def source(
    source_id: str = "KOR-1",
    text: str = "Polska przystąpiła do Unii Europejskiej 1 maja 2004 roku.",
    kind: str = "korpus",
    **kw: Any,
) -> ReferenceSource:
    return ReferenceSource(
        source_id=source_id,
        kind=kind,
        text=text,
        title=kw.pop("title", "Tytuł"),
        publisher=kw.pop("publisher", "Wydawca"),
        **kw,
    )


def model_answer(**overrides: Any) -> dict[str, Any]:
    answer: dict[str, Any] = {
        "claim_interpretation": "Twierdzenie podaje datę akcesji Polski do UE.",
        "verdict": "prawda",
        "confidence": "wysoka",
        "reasoning_steps": ["[KOR-1] podaje datę 1 maja 2004 roku.", "Data zgadza się."],
        "evidence": [
            {
                "source_id": "KOR-1",
                "quote": "Polska przystąpiła do Unii Europejskiej 1 maja 2004 roku",
                "stance": "potwierdza",
                "explanation": "Data akcesji",
            }
        ],
        "sources_reviewed": [
            {"source_id": "KOR-1", "relevant": True, "why": "Podaje datę akcesji"}
        ],
        "conflicts": [],
        "missing_information": [],
        "explanation": "Źródło [KOR-1] wprost podaje datę 1 maja 2004 roku.",
    }
    answer.update(overrides)
    return answer


__all__ = ["FakeChatClient", "LLMError", "model_answer", "source"]
