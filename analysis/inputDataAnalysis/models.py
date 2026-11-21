"""Modele danych: wejście (źródła prawdy), schematy odpowiedzi LLM i obiekt wynikowy.

Schematy ``LLM*`` są celowo płaskie: bez unii i bez ``null`` (puste pola to ``""``),
bo endpoint Gemini zgodny z OpenAI obsługuje tylko podzbiór JSON Schema.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal, get_args

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator

# --- słowniki ---------------------------------------------------------------------------------

CategoryCode = Literal[
    "EMOTIONAL_LANGUAGE",
    "FEAR_APPEAL",
    "CONSPIRACY_FRAMING",
    "FALSE_URGENCY",
    "LACK_OF_SOURCE",
    "EXAGGERATION",
    "CHERRY_PICKING",
]
CATEGORY_CODES: tuple[str, ...] = get_args(CategoryCode)

SourceSubtype = Literal["none", "unverifiable", "unreliable", "inadequate"]
Attribution = Literal["author", "quoted"]
Severity = Literal["low", "medium", "high"]
DateIssueCode = Literal[
    "DATE_MISMATCH",
    "OUTDATED_AS_CURRENT",
    "ANACHRONISM",
    "FUTURE_AS_PAST",
    "INTERNAL_INCONSISTENCY",
    "STALE_DATA",
    "BEFORE_SOURCES",
]
DateRole = Literal["event", "publication", "data_as_of", "future", "reference"]
Tense = Literal["past", "present", "future"]
TextCategory = Literal["breaking", "political_legal", "economic", "other"]
LLMGranularity = Literal["day", "week", "month", "quarter", "year", "unknown"]


# --- wejście ----------------------------------------------------------------------------------


class TruthSource(BaseModel):
    """Źródło prawdy przekazane przez inny moduł.

    Przyjmuje też popularne alternatywne nazwy pól (``text``/``body``, ``date``/``publication_date``).
    """

    model_config = ConfigDict(coerce_numbers_to_str=True, populate_by_name=True)

    id: str = Field(validation_alias=AliasChoices("id", "source_id"))
    content: str = Field(validation_alias=AliasChoices("content", "text", "body"))
    title: str | None = None
    url: str | None = None
    published_at: date | None = Field(
        default=None,
        validation_alias=AliasChoices("published_at", "publication_date", "date"),
    )

    @field_validator("published_at", mode="before")
    @classmethod
    def _datetime_to_date(cls, value: object) -> object:
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, str) and len(value) > 10:
            try:
                return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
            except ValueError:
                return value
        return value

    @property
    def label(self) -> str:
        return self.title or self.id


# --- schematy odpowiedzi LLM ------------------------------------------------------------------


class LLMFragment(BaseModel):
    quote: str
    category: CategoryCode
    subtype: str = Field(
        description="Tylko dla LACK_OF_SOURCE: none|unverifiable|unreliable|inadequate; inaczej pusty napis."
    )
    indicators: list[str]
    test_answer: str
    explanation: str
    confidence: float
    attribution: Attribution
    source_id: str = Field(
        description="Tylko dla CHERRY_PICKING: id źródła z pominiętym kontekstem; inaczej pusty napis."
    )
    source_evidence: str = Field(
        description="Dosłowny cytat ze źródła prawdy z pominiętym kontekstem; inaczej pusty napis."
    )


class LLMManipulationResponse(BaseModel):
    fragments: list[LLMFragment]


class LLMSourceMatch(BaseModel):
    found: bool
    source_id: str
    source_quote: str
    iso_start: str
    iso_end: str
    granularity: LLMGranularity
    relative_expression: str
    status: Literal["occurred", "planned", "unknown"]


class LLMDateItem(BaseModel):
    id: str
    quote: str
    what: str
    role: DateRole
    tense: Tense
    iso_start: str
    iso_end: str
    granularity: LLMGranularity
    absolute_given: bool
    relative_expression: str
    weekday_mentioned: str
    recency_framing: float
    match: LLMSourceMatch


class LLMDatesResponse(BaseModel):
    article_date_in_text: str
    text_category: TextCategory
    recency_framing: float
    dates: list[LLMDateItem]


# --- wynik ------------------------------------------------------------------------------------


class SourceEvidence(BaseModel):
    source_id: str
    quote: str


class ManipulationFragment(BaseModel):
    quote: str
    start: int
    end: int
    category: CategoryCode
    category_name: str
    subtype: SourceSubtype | None = None
    indicators: list[str] = Field(default_factory=list)
    test_answer: str = ""
    explanation: str = ""
    confidence: float
    attribution: Attribution = "author"
    source_evidence: SourceEvidence | None = None


class ManipulationResult(BaseModel):
    manipulation_detected: bool
    score: int = Field(ge=0, le=100)
    counts: dict[str, int]
    fragments: list[ManipulationFragment]
    dropped_fragments: int = Field(
        default=0, description="Fragmenty od LLM, których cytatu nie znaleziono w tekście."
    )


class DateIssue(BaseModel):
    code: DateIssueCode
    severity: Severity
    description: str
    input_quote: str | None = None
    start: int | None = None
    end: int | None = None
    source_id: str | None = None
    source_quote: str | None = None
    delta_days: int | None = None


class SkippedCheck(BaseModel):
    check: str
    reason: str


class ExtractedDate(BaseModel):
    id: str
    quote: str
    start: int
    end: int
    what: str
    role: DateRole
    tense: Tense
    date_from: date | None = None
    date_to: date | None = None
    granularity: str = "unknown"
    recency_framing: float = 0.0
    source_id: str | None = None
    source_quote: str | None = None
    source_date_from: date | None = None
    source_date_to: date | None = None


class DatesResult(BaseModel):
    dates_consistent: bool
    article_date: date | None = None
    text_category: TextCategory = "other"
    issues: list[DateIssue] = Field(default_factory=list)
    extracted: list[ExtractedDate] = Field(default_factory=list)
    unverified: list[str] = Field(default_factory=list)
    skipped_checks: list[SkippedCheck] = Field(default_factory=list)


class AnalysisResult(BaseModel):
    manipulation: ManipulationResult
    dates: DatesResult
