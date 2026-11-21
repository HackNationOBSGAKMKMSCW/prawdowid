"""Wspólne modele danych zgodne z analysis/CONTRACTS.md.

Zmiana pola w tym pliku to zmiana kontraktu: PR, powiadomienie drugiej osoby
i wpis w historii zmian CONTRACTS.md.
"""

from typing import Literal

from pydantic import BaseModel, Field

SourceType = Literal[
    "official_primary", "public_data", "fact_check", "news_agency", "research", "media"
]
ClaimType = Literal["legal", "numeric", "scientific", "quote", "event", "opinion"]
Stance = Literal["supports", "refutes", "neutral", "insufficient"]
VerdictOutcome = Literal[
    "confirmed", "false", "misleading", "insufficient_evidence", "not_verifiable"
]
StatusOutcome = Literal["error", "cannot_check", "needs_clarification", "out_of_scope"]
Flag = Literal["conflicting_sources", "missing_context", "stale_source", "source_status_warning"]


class Passage(BaseModel):
    """Wyjście `retrieve()`: fragment dokumentu z korpusu."""

    chunk_id: str
    doc_id: str
    title: str
    publisher: str
    url: str
    published_at: str | None = Field(description="Data publikacji, ISO 8601 (YYYY-MM-DD)")
    fetched_at: str = Field(description="Czas pobrania, ISO 8601 UTC")
    source_type: SourceType
    text: str
    char_start: int = Field(ge=0)
    char_end: int = Field(ge=0)
    text_hash: str = Field(description="sha256 zapisanego clean_text dokumentu")
    rerank_score: float


class Claim(BaseModel):
    claim_id: str
    run_id: str | None = None
    text: str
    type: ClaimType
    check_worthy: bool


class Evidence(BaseModel):
    evidence_id: str
    claim_id: str
    chunk_id: str
    quote: str
    quote_verified: bool
    stance: Stance


class Strength(BaseModel):
    level: Literal["high", "medium", "low"]
    factors: list[str]


class Handover(BaseModel):
    recommended: bool = False
    created: bool = False
    case_id: str | None = None


class Verdict(BaseModel):
    claim_id: str | None
    outcome_class: Literal["verdict", "status"]
    outcome: VerdictOutcome | StatusOutcome
    strength: Strength | None = None
    explanation_pl: str
    unresolved: list[str] = []
    limitations: list[str] = []
    evidence_ids: list[str] = []
    flags: list[Flag] = []
    handover: Handover = Handover()


# ── Wejście i wyjście analizy ────────────────────────────────────────────────


class SourceIn(BaseModel):
    """Źródło przekazane do analizy: URL + gotowy, oczyszczony tekst (`clean_text`)."""

    url: str
    title: str
    publisher: str
    published_at: str | None = Field(default=None, description="ISO 8601 (YYYY-MM-DD)")
    fetched_at: str = Field(description="Czas pobrania, ISO 8601 UTC")
    source_type: SourceType
    text: str = Field(min_length=1, description="clean_text; offsety pasaży liczone względem niego")


class AnalysisInput(BaseModel):
    request_id: str
    claims: list[Claim]
    sources: list[SourceIn] = []


class IngestReport(BaseModel):
    added: int = 0
    skipped: int = 0
    replaced: int = 0


class ClaimResult(BaseModel):
    claim: Claim
    passages: list[Passage] = []
    evidence: list[Evidence] = []
    verdict: Verdict | None = None


class AnalysisOutput(BaseModel):
    request_id: str
    results: list[ClaimResult]
    ingest: IngestReport
