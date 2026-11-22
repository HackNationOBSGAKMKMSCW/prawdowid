"""Read-only trusted-source list for the browser app (``GET /api/trusted-sources``).

Only the public fields the page needs. The detection and search endpoints of
``trustedSources.api`` (``POST …/check``, ``POST …/search``) fetch remote pages and
call the LLM, so they stay out of the public, unauthenticated browser API; they are
mounted by the WhatsApp simulator.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel

router = APIRouter(prefix="/api/trusted-sources", tags=["trusted-sources"])


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
def list_trusted_sources(response: Response) -> list[PublicTrustedSource]:
    """Enabled sources, the same list the verification searches."""
    from trustedSources.registry import default_registry

    response.headers["Cache-Control"] = "public, max-age=300"
    return [_public(source) for source in default_registry().list(enabled_only=True)]


@router.get("/{source_id}", response_model=PublicTrustedSource)
def get_trusted_source(source_id: str) -> PublicTrustedSource:
    from trustedSources.registry import RegistryError, default_registry

    try:
        source = default_registry().get(source_id)
    except RegistryError:
        raise HTTPException(404, "Trusted source not found.") from None
    if not source.enabled:
        raise HTTPException(404, "Trusted source not found.")
    return _public(source)
