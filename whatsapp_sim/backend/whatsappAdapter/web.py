"""Clarification endpoint for the website (``POST /api/clarify``).

The website runs the same loop as the WhatsApp bot (``clarification.next_step``) but
keeps the conversation in the browser: each request carries every turn so far, and the
response says whether to ask the returned questions or to check ``claim``. The server
stores nothing between requests.
"""

from collections.abc import Callable
from typing import Any, Literal

from fastapi import APIRouter
from pydantic import BaseModel, Field, model_validator
from textAnalysis.analysis import InputSanitizer
from textAnalysis.clarification import DialogueTurn

from .clarification import (
    DEFAULT_CLARIFY_TIMEOUT,
    MAX_CLARIFICATION_ROUNDS,
    ClarificationStep,
    Clarifier,
    guarded,
    next_step,
)

MAX_BOT_TURN_CHARS = 1_000


class TurnIn(BaseModel):
    role: Literal["user", "bot"]
    text: str = Field(min_length=1, max_length=InputSanitizer.MAX_INPUT_LENGTH)


class ClarifyRequest(BaseModel):
    # First message, then at most two question/answer pairs.
    turns: list[TurnIn] = Field(min_length=1, max_length=2 * MAX_CLARIFICATION_ROUNDS + 1)

    @model_validator(mode="after")
    def _shape(self) -> "ClarifyRequest":
        if self.turns[0].role != "user" or not self.turns[0].text.strip():
            raise ValueError("the first turn must be the user's message")
        if self.turns[-1].role != "user":
            raise ValueError("the last turn must be the user's message or answer")
        if any(t.role == "bot" and len(t.text) > MAX_BOT_TURN_CHARS for t in self.turns):
            raise ValueError(f"bot turns are limited to {MAX_BOT_TURN_CHARS} characters")
        return self


def _turns_out(turns: tuple[DialogueTurn, ...]) -> list[dict[str, str]]:
    return [{"role": turn.role, "text": turn.text} for turn in turns]


def step_response(step: ClarificationStep) -> dict[str, Any]:
    """The JSON the website gets; ``turns`` is what it sends back with the next answer."""

    turns = (*step.turns, step.question_turn()) if step.action == "ask" else step.turns
    return {
        "status": step.action,
        "turns": _turns_out(turns),
        "questions": list(step.questions),
        "missing": list(step.missing),
        "understood_claim": step.understood_claim,
        "claim": step.claim,
        "skip_claim": step.skip_claim,
        "with_details": step.with_details,
        "new_topic": step.new_topic,
    }


def clarify_router(
    clarifier: Callable[[], Clarifier | None],
    *,
    timeout: float = DEFAULT_CLARIFY_TIMEOUT,
) -> APIRouter:
    router = APIRouter()

    @router.post("/api/clarify")
    async def clarify(request: ClarifyRequest) -> dict[str, Any]:
        turns = [DialogueTurn(turn.role, turn.text) for turn in request.turns]
        current = clarifier()
        if current is None:
            # Loop turned off: check the first message as it is.
            step = ClarificationStep("check", (turns[0],), claim=turns[0].text)
            return step_response(step)
        assess = guarded(current, timeout=timeout, label="Strona: ")
        return step_response(await next_step(assess, turns))

    return router
