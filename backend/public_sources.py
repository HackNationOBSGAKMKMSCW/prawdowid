"""Read-only trusted-source list for the browser app (``GET /api/trusted-sources``).

Only the public fields the page needs. The detection and search endpoints of
``trustedSources.api`` (``POST …/check``, ``POST …/search``) fetch remote pages and
call the LLM, so they stay out of the public, unauthenticated browser API; they are
mounted by the WhatsApp simulator.

The list comes from the ``trusted_sources`` table only (the one the admin panel edits).
Unlike the verification, which falls back to the code list so it never searches without
sources, this endpoint never shows the code list: without the database it answers 503
``sources_unavailable`` and the page says the list cannot be loaded.
"""

from __future__ import annotations

import logging
import threading

from fastapi import APIRouter, HTTPException, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/trusted-sources", tags=["trusted-sources"])

REFRESH_SECONDS = 60.0
_registry_lock = threading.Lock()
_db_registry = None


class SourcesUnavailable(RuntimeError):
    """The database list cannot be read."""


def _registry():
    """Registry over the database table alone (no code-list fallback), refreshed every minute."""
    global _db_registry
    with _registry_lock:
        if _db_registry is None:
            from accounts.trusted import PostgresSourceStore
            from database import database_url, get_database
            from trustedSources.registry import SourceRegistry

            if not database_url():
                raise SourcesUnavailable("DATABASE_URL is not set")
            _db_registry = SourceRegistry(
                store=PostgresSourceStore(get_database()), refresh_seconds=REFRESH_SECONDS
            )
        return _db_registry


def reload() -> None:
    """Zmiana listy w panelu admina (ten sam proces): wczytaj tabelę od razu, nie po minucie."""
    with _registry_lock:
        registry = _db_registry
    if registry is not None:
        registry.refresh()


def _enabled_sources():
    try:
        return _registry().list(enabled_only=True)
    except Exception as exc:  # noqa: BLE001 - database details stay out of the response
        logger.warning("public_trusted_sources_unavailable error_type=%s", type(exc).__name__)
        raise SourcesUnavailable(type(exc).__name__) from None


def _unavailable() -> JSONResponse:
    return JSONResponse(
        status_code=503,
        content={
            "error": {
                "code": "sources_unavailable",
                "message": "The source list could not be loaded.",
            }
        },
        headers={"Cache-Control": "no-store"},
    )


class PublicTrustedSource(BaseModel):
    id: str
    name: str
    url: str
    trust: str
    topics: list[str]
    description: str


def _public(source) -> PublicTrustedSource:
    return PublicTrustedSource(
        id=source.id,
        name=source.name,
        url=source.url,
        trust=source.trust,
        topics=list(source.topics),
        description=source.description,
    )


@router.get("", response_model=list[PublicTrustedSource])
def list_trusted_sources(response: Response):
    """Enabled sources from the database, the list the admin panel edits."""
    try:
        sources = _enabled_sources()
    except SourcesUnavailable:
        return _unavailable()
    response.headers["Cache-Control"] = "public, max-age=60"
    return [_public(source) for source in sources]


@router.get("/{source_id}", response_model=PublicTrustedSource)
def get_trusted_source(source_id: str):
    try:
        sources = _enabled_sources()
    except SourcesUnavailable:
        return _unavailable()
    source = next((source for source in sources if source.id == source_id), None)
    if source is None:
        raise HTTPException(404, "Trusted source not found.")
    return _public(source)
