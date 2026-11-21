"""REST API maskowania: ``POST /api/masking`` (używane przez okno testowe we frontendzie)."""

from __future__ import annotations

from fastapi import APIRouter, FastAPI
from pydantic import BaseModel, Field

from .masker import mask_personal_data

MAX_TEXT_LENGTH = 15_000


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


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


def create_app() -> FastAPI:
    """Samodzielny serwer z samym maskowaniem (``python -m dataMasking``)."""
    app = FastAPI(title="Prawdowid – maskowanie danych", docs_url="/api/masking/docs")
    app.include_router(router)
    return app
