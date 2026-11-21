"""REST API maskowania.

- ``POST /api/masking`` – samo maskowanie (okno „Test maskowania”),
- ``POST /api/masking/llm-input`` – dokładnie ten tekst, który ``InputSanitizer``
  przekazuje do LLM (okno po kliknięciu „Sprawdź”).
"""

from __future__ import annotations

import re
from collections import Counter

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, Field

from .masker import mask_personal_data

_PLACEHOLDER = re.compile(r"\[([A-Z_]+)_\d+\]")
MAX_TEXT_LENGTH = 20_000  # InputSanitizer sam przycina do 15 000 i to zgłasza


class MaskingRequest(BaseModel):
    text: str = Field(max_length=MAX_TEXT_LENGTH)


class MaskedEntity(BaseModel):
    label: str
    placeholder: str
    start: int = Field(description="Początek wartości w tekście wejściowym.")
    end: int = Field(description="Koniec wartości w tekście wejściowym (bez niego).")


class MaskingResponse(BaseModel):
    masked_text: str
    entities: list[MaskedEntity]
    counts: dict[str, int]


router = APIRouter(prefix="/api/masking", tags=["maskowanie"])


@router.post("", response_model=MaskingResponse)
def mask(request: MaskingRequest) -> MaskingResponse:
    """Zwraca tekst z zamaskowanymi danymi osobowymi.

    Wartości nie są odsyłane: ``start``/``end`` wskazują je w tekście, który
    klient już ma. Endpoint niczego nie zapisuje.
    """
    result = mask_personal_data(request.text)
    return MaskingResponse(
        masked_text=result.text,
        entities=[MaskedEntity(**vars(e)) for e in result.entities],
        counts=result.counts,
    )


class LlmInputResponse(BaseModel):
    llm_text: str = Field(description="Tekst wstawiany do promptu w <untrusted_text>.")
    counts: dict[str, int]
    warnings: list[str] = Field(
        description="Ostrzeżenia sanitizera (przycięcie, prompt injection)."
    )


@router.post("/llm-input", response_model=LlmInputResponse)
def llm_input(request: MaskingRequest) -> LlmInputResponse:
    """Podgląd tekstu, który po sanityzacji i maskowaniu trafia do LLM. Nic nie wysyła do modelu."""
    # Import tutaj: textAnalysis sam importuje dataMasking.
    from textAnalysis.analysis import InputSanitizer

    try:
        llm_text, warnings = InputSanitizer.sanitize(request.text)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    return LlmInputResponse(
        llm_text=llm_text,
        counts=dict(Counter(_PLACEHOLDER.findall(llm_text))),
        warnings=warnings,
    )


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


def create_app() -> FastAPI:
    """Samodzielny serwer z samym maskowaniem (``python -m dataMasking``)."""
    app = FastAPI(title="Prawdowid – maskowanie danych", docs_url="/api/masking/docs")
    app.include_router(router)
    return app
