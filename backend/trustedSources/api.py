"""Read-only REST endpoints for the trusted-source whitelist.

Mount in any FastAPI app::

    from trustedSources.api import router as trusted_sources_router
    app.include_router(trusted_sources_router)

The list itself is edited in ``whitelist.py`` (later: the PostgreSQL table).
"""

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from .models import TrustedSearchReport, TrustedSource
from .registry import RegistryError, default_registry
from .service import ensure_detected, queries_for_text, search, search_context

router = APIRouter(prefix="/api/trusted-sources", tags=["trusted-sources"])


class SearchBody(BaseModel):
    text: str | None = Field(default=None, max_length=2000)
    queries: list[str] = Field(default_factory=list, max_length=5)


@router.get("", response_model=list[TrustedSource])
def list_sources(enabled_only: bool = False) -> list[TrustedSource]:
    return default_registry().list(enabled_only=enabled_only)


@router.get("/{source_id}", response_model=TrustedSource)
def get_source(source_id: str) -> TrustedSource:
    try:
        return default_registry().get(source_id)
    except RegistryError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from None


@router.post("/{source_id}/check", response_model=TrustedSource)
async def check_source(source_id: str) -> TrustedSource:
    """Detect the source's type again (result kept in memory)."""

    registry = default_registry()
    try:
        source = registry.get(source_id)
    except RegistryError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from None
    async with search_context() as ctx:
        [source] = await ensure_detected(registry, ctx, [source], force=True)
    return source


@router.post("/search", response_model=TrustedSearchReport)
async def search_sources(body: SearchBody) -> TrustedSearchReport:
    """``text``: queries built as in the pipeline (textAnalysis); ``queries``: used as given."""

    queries = [*body.queries]
    if body.text and body.text.strip():
        queries = [*(await queries_for_text(body.text)), *queries]
    if not queries:
        raise HTTPException(422, "text or queries required")
    return await search(queries)
