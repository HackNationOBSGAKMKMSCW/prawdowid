"""Data models for the trusted-source whitelist and its search results."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

Trust = Literal["official", "fact_checker", "other"]
HitKind = Literal["article", "reference"]

# Adapter value for an entry that was added but not yet probed (detection runs lazily).
PENDING_ADAPTER = "pending"


class LastCheck(BaseModel):
    """Outcome of the most recent type detection for a source."""

    at: datetime
    ok: bool
    error: str | None = None
    detail: str | None = None


class TrustedSource(BaseModel):
    """One whitelisted site (or section of a site) and how to search it."""

    model_config = ConfigDict(extra="ignore")

    id: str
    url: str
    name: str
    adapter: str = PENDING_ADAPTER
    params: dict[str, Any] = Field(default_factory=dict)
    # Adapter set in the whitelist; automatic detection never overrides it.
    adapter_locked: bool = False
    domains: list[str]
    path_prefix: str = "/"
    trust: Trust = "official"
    topics: list[str] = Field(default_factory=list)
    description: str = ""
    enabled: bool = True
    added_at: datetime
    last_check: LastCheck | None = None

    def owns_url(self, url_host: str | None) -> bool:
        """True when ``url_host`` belongs to one of this source's whitelisted domains."""

        if not url_host:
            return False
        host = url_host.lower().rstrip(".")
        return any(host == domain or host.endswith(f".{domain}") for domain in self.domains)


class EvidenceHit(BaseModel):
    """A page on a whitelisted source that matches one of the search queries."""

    source_id: str
    source_name: str
    trust: Trust = "official"
    url: str
    title: str
    snippet: str = ""
    published_at: datetime | None = None
    query: str = ""
    score: float = 0.0
    kind: HitKind = "article"


class SourceFailure(BaseModel):
    """A per-source failure that did not stop the other sources."""

    source_id: str
    kind: str
    status_code: int | None = None


class TrustedSearchReport(BaseModel):
    """Result of ``trustedSources.run``: ranked hits plus isolated failures."""

    queries: list[str]
    hits: list[EvidenceHit]
    failures: list[SourceFailure] = Field(default_factory=list)
    sources_queried: int = 0
    duration_ms: int = 0

    @property
    def articles(self) -> list[EvidenceHit]:
        return [hit for hit in self.hits if hit.kind == "article"]

    @property
    def references(self) -> list[EvidenceHit]:
        return [hit for hit in self.hits if hit.kind == "reference"]
