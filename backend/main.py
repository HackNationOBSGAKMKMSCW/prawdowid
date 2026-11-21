"""HTTP entry points for independently running text analysis and API reading."""

from dataPreparation.analysis import (
    AnalysisConfigurationError,
    AnalysisError,
    run_analysis,
)
from dataPreparation.apiReading import ApiReadingError, Category, ReadingResult
from dataPreparation.container import AnalysisDataContainer
from dataPreparation.reading import run_api_reading
from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, Field

app = FastAPI(title="Prawdowid API")
api = APIRouter(prefix="/api")


class AnalysisRequest(BaseModel):
    text: str = Field(min_length=1, max_length=15_000)
    top_keywords: int = Field(default=5, ge=1, le=15)


class ApiReadingRequest(BaseModel):
    analysis: AnalysisDataContainer
    category: Category = Category.FACT_CHECK
    language_code: str | None = None
    page_size: int = Field(default=10, ge=1, le=20)


@api.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@api.post("/analyze", response_model=AnalysisDataContainer)
async def analyze_text(payload: AnalysisRequest) -> AnalysisDataContainer:
    """Analyze submitted text without automatically requesting external fact checks."""
    try:
        return await run_analysis(payload.text, top_keywords=payload.top_keywords)
    except AnalysisConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except AnalysisError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@api.post("/check", response_model=list[ReadingResult])
async def check_analysis(payload: ApiReadingRequest) -> list[ReadingResult]:
    """Fetch fact checks for the statements in a previously returned analysis."""
    try:
        return await run_api_reading(
            payload.analysis,
            category=payload.category,
            language_code=payload.language_code,
            page_size=payload.page_size,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ApiReadingError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


app.include_router(api)
