"""Public request and response contracts for the browser API."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class SourceResponse(BaseModel):
    quote: str
    publisher: str
    url: str | None = None
    year: str | None = None
    lang: str | None = None


class ClaimResponse(BaseModel):
    verdict: Literal["confirmed", "false", "misleading", "insufficient", "unverifiable"]
    text: str
    explanation: str
    sources: list[SourceResponse] | None = None


class ManipulationFragmentResponse(BaseModel):
    quote: str
    start: int
    end: int
    category: str
    explanation: str
    confidence: float


class ManipulationResponse(BaseModel):
    manipulation_detected: bool
    score: int
    fragments: list[ManipulationFragmentResponse]


class DateIssueResponse(BaseModel):
    code: str
    severity: Literal["low", "medium", "high"]
    start: int
    source_id: str | None = None
    delta_days: int | None = None
    description: str | None = None


class ExtractedDateResponse(BaseModel):
    start: int
    what: str
    source_date_from: str | None = None


class DatesResponse(BaseModel):
    dates_consistent: bool
    article_date: str | None = None
    issues: list[DateIssueResponse]
    extracted: list[ExtractedDateResponse]


class TextAnalysisResponse(BaseModel):
    manipulation: ManipulationResponse | None = None
    dates: DatesResponse | None = None


class CheckResponse(BaseModel):
    status: Literal["result"] = "result"
    id: str
    input_type: Literal["text", "url"]
    claims: list[ClaimResponse]
    analysis: TextAnalysisResponse | None = None
    source_names: dict[str, str] | None = None


class ReportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: Literal["wrong_verdict", "bad_source", "misunderstood", "other"]
    comment: str | None = Field(default=None, max_length=1000)

    @field_validator("comment")
    @classmethod
    def blank_comment_is_omitted(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None


class ErrorDetail(BaseModel):
    code: str
    message: str


class ErrorResponse(BaseModel):
    error: ErrorDetail
    request_id: str | None = None
