"""Endpoint `/api/check`: wejście zgłoszenia, walidacja i szkielet potoku.

Na tym etapie potok to: rozpoznanie typu wejścia -> retrieve() -> status.
Ekstrakcja twierdzeń, pobieranie URL i logika werdyktu dojdą w kolejnych krokach.
Dopóki ich nie ma, odpowiedź to zawsze **status** `cannot_check`, nigdy pozorny werdykt.
"""

import ipaddress
import re
import time
import uuid
from typing import Literal
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ratelimit import rate_limit
from retrieval import get_retriever
from schemas import Claim, Passage, Verdict

MAX_INPUT_CHARS = 10_000
MAX_URL_CHARS = 2_048
MIN_TEXT_CHARS = 3

# Znaki sterujące poza \t \n \r: nie mają sensu w zgłoszeniu, a ułatwiają ataki na logi i prompt.
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_URL_LIKE_RE = re.compile(r"^https?://\S+$", re.IGNORECASE)

router = APIRouter()


class CheckRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    input: str = Field(
        min_length=MIN_TEXT_CHARS,
        max_length=MAX_INPUT_CHARS,
        description="Treść do sprawdzenia albo adres URL",
    )
    input_type: Literal["auto", "text", "url"] = "auto"
    channel: Literal["web", "discord", "sms", "demo"] = "web"

    @field_validator("input")
    @classmethod
    def no_control_chars(cls, v: str) -> str:
        if _CONTROL_RE.search(v):
            raise ValueError("Treść zawiera niedozwolone znaki sterujące.")
        return v

    @model_validator(mode="after")
    def resolve_and_check_url(self) -> "CheckRequest":
        if self.input_type == "auto":
            self.input_type = "url" if _URL_LIKE_RE.match(self.input) else "text"
        if self.input_type == "url":
            validate_url(self.input)
        return self


def validate_url(url: str) -> None:
    """Podstawowa walidacja adresu. Pełna ochrona przed SSRF (rozwiązywanie DNS,
    przekierowania) musi być też w kodzie, który pobiera treść URL."""
    if len(url) > MAX_URL_CHARS:
        raise ValueError(f"Adres URL jest dłuższy niż {MAX_URL_CHARS} znaków.")
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https"):
        raise ValueError("Obsługujemy tylko adresy zaczynające się od http:// lub https://.")
    if not parts.hostname:
        raise ValueError("Adres URL nie zawiera nazwy serwera.")
    if parts.username or parts.password:
        raise ValueError("Adres URL nie może zawierać loginu ani hasła.")
    host = parts.hostname.lower()
    if host == "localhost" or host.endswith((".localhost", ".local", ".internal")):
        raise ValueError("Adres URL wskazuje na serwer lokalny.")
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return
    if not ip.is_global:
        raise ValueError("Adres URL wskazuje na adres prywatny lub zastrzeżony.")


class CheckResponse(BaseModel):
    run_id: str
    channel: str
    input_type: Literal["text", "url"]
    retriever: str
    claims: list[Claim]
    verdicts: list[Verdict]
    passages: list[Passage]
    duration_ms: int


@router.post("/check", dependencies=[Depends(rate_limit)])
def check(req: CheckRequest) -> CheckResponse:
    started = time.perf_counter()
    run_id = f"run_{uuid.uuid4().hex[:12]}"
    retrieve = get_retriever()

    if req.input_type == "url":
        # Pobieranie treści URL to kolejny krok; do tego czasu uczciwy status.
        verdict = Verdict(
            claim_id=None,
            outcome_class="status",
            outcome="cannot_check",
            explanation_pl="Sprawdzanie treści spod adresu URL nie jest jeszcze dostępne. "
            "Wklej treść jako tekst.",
            limitations=["Pobieranie treści URL nie jest jeszcze zaimplementowane."],
        )
        return CheckResponse(
            run_id=run_id,
            channel=req.channel,
            input_type="url",
            retriever=retrieve.__name__,
            claims=[],
            verdicts=[verdict],
            passages=[],
            duration_ms=_elapsed_ms(started),
        )

    # Szkielet: całe zgłoszenie jako jedno twierdzenie, dopóki nie ma ekstrakcji twierdzeń.
    claim = Claim(
        claim_id=f"clm_{run_id[4:]}_1",
        run_id=run_id,
        text=req.input,
        type="event",
        check_worthy=True,
    )
    passages = retrieve(claim.text, k=6)
    verdict = Verdict(
        claim_id=claim.claim_id,
        outcome_class="status",
        outcome="cannot_check",
        explanation_pl="Ocena twierdzeń nie jest jeszcze podłączona. "
        "Poniżej widać fragmenty źródeł znalezione dla zgłoszenia.",
        limitations=[
            "Szkielet API: brak ekstrakcji twierdzeń i logiki werdyktu.",
            f"Retriever: {retrieve.__name__}.",
        ],
    )
    return CheckResponse(
        run_id=run_id,
        channel=req.channel,
        input_type="text",
        retriever=retrieve.__name__,
        claims=[claim],
        verdicts=[verdict],
        passages=passages,
        duration_ms=_elapsed_ms(started),
    )


def _elapsed_ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)
