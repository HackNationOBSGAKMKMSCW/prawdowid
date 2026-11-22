"""Events emitted by the verification flow (one per finished part)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel

Part = Literal["evidence", "input_analysis", "claims_verdict"]
PARTS: tuple[Part, ...] = ("evidence", "input_analysis", "claims_verdict")
Status = Literal["ok", "error"]


class PartError(BaseModel):
    # evidence_failed (no assessment was started), Timeout, LLMError, AnalysisUnavailable, ...
    kind: str
    message: str


class VerificationEvent(BaseModel):
    """One finished part of a verification request.

    ``data`` for ``evidence``: ``{"statements": [...], "scraping": ScrapingReport}``;
    ``input_analysis``: ``inputDataAnalysis.AnalysisResult``;
    ``claims_verdict``: ``prawdowid_analysis.schemas.TextVerdict`` (all as JSON dicts).
    """

    request_id: str
    part: Part
    status: Status
    data: dict[str, Any] | None = None
    error: PartError | None = None
    duration_ms: int
    finished_at: datetime


class VerificationReport(BaseModel):
    request_id: str
    submitted_at: datetime
    evidence: VerificationEvent
    input_analysis: VerificationEvent
    claims_verdict: VerificationEvent
