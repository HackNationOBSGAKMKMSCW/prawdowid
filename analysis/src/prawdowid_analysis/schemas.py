"""Kontrakty danych modułu werdyktu.

Trzy grupy modeli:
- `ReferenceSource`: źródło wzorcowe pokazywane modelowi (z dowolnego pochodzenia).
- `ModelVerdict` i pochodne: DOKŁADNY kształt JSON, który musi zwrócić model.
  Ten sam schemat jest opisany w prompcie (prompts/werdykt_system.md).
- `ClaimVerdict` i `TextVerdict`: wynik końcowy po kontroli deterministycznej,
  zwracany wywołującemu jako JSON.

Wartości wyliczeniowe są w ASCII (bez polskich znaków), żeby były stabilne
jako kody; opisy i uzasadnienia są po polsku.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

SourceKind = Literal["fact_check", "korpus", "uzytkownik"]
Stance = Literal["potwierdza", "zaprzecza"]
ModelVerdictValue = Literal["prawda", "falsz", "brak_wystarczajacych_danych"]
ClaimVerdictValue = Literal["prawda", "falsz", "brak_wystarczajacych_danych", "blad_analizy"]
Confidence = Literal["wysoka", "srednia", "niska"]
TextVerdictValue = Literal[
    "prawdziwy",
    "falszywy",
    "zawiera_falsz",
    "czesciowo_potwierdzony",
    "brak_wystarczajacych_danych",
    "nieweryfikowalny",
    "blad_analizy",
]

VERDICT_LABELS_PL: dict[str, str] = {
    "prawda": "Prawda",
    "falsz": "Fałsz",
    "brak_wystarczajacych_danych": "Brak wystarczających danych",
    "blad_analizy": "Błąd analizy",
}


# ── Źródła wzorcowe ──────────────────────────────────────────────────────────


class ReferenceSource(BaseModel):
    """Jedno źródło wzorcowe (lub jego fragment) przekazywane modelowi.

    `text` to jedyna treść, z której model może cytować; cytaty są sprawdzane
    dosłownie właśnie względem tego pola.
    """

    model_config = ConfigDict(frozen=True)

    source_id: str = Field(min_length=1)
    kind: SourceKind
    title: str = ""
    publisher: str = ""
    url: str | None = None
    published_at: str | None = Field(default=None, description="ISO 8601 (YYYY-MM-DD)")
    text: str = Field(min_length=1)
    rating: str | None = Field(
        default=None, description="Ocena fact-checkera (textualRating), tylko dla kind=fact_check"
    )
    language: str | None = Field(
        default=None, description="Kod języka źródła (BCP-47), jeśli znany"
    )
    fetched_at: str | None = Field(
        default=None, description="Znacznik czasu pobrania treści, ISO 8601 UTC"
    )
    age_days: int | None = Field(
        default=None, description="Wiek źródła w dniach od publikacji do dnia analizy"
    )
    freshness_flags: list[str] = Field(
        default=[],
        description="Flagi aktualności: material_archiwalny, brak_daty_publikacji, "
        "data_publikacji_w_przyszlosci",
    )
    provider: str | None = Field(
        default=None, description="Dostawca danych z backendu (np. google_fact_check)"
    )


# ── Odpowiedź modelu (schemat wymuszany promptem) ────────────────────────────


class _Strict(BaseModel):
    model_config = ConfigDict(extra="ignore")


class ModelEvidence(_Strict):
    source_id: str
    quote: str = Field(description="Dosłowny fragment pola `text` źródła")
    stance: Stance
    explanation: str = ""


class ModelSourceReview(_Strict):
    source_id: str
    relevant: bool
    why: str


class ModelVerdict(_Strict):
    claim_interpretation: str = Field(description="Jak model rozumie sprawdzane twierdzenie")
    verdict: ModelVerdictValue
    confidence: Confidence
    reasoning_steps: list[str] = Field(min_length=1)
    evidence: list[ModelEvidence] = []
    sources_reviewed: list[ModelSourceReview] = []
    conflicts: list[str] = []
    missing_information: list[str] = []
    explanation: str = Field(min_length=1)


# ── Wynik końcowy ────────────────────────────────────────────────────────────


class EvidenceOut(BaseModel):
    source_id: str
    quote: str
    stance: Stance
    explanation: str = ""
    quote_verified: bool
    source_title: str = ""
    publisher: str = ""
    url: str | None = None
    published_at: str | None = None
    fetched_at: str | None = None
    age_days: int | None = None
    freshness_flags: list[str] = []


class SourceReviewOut(BaseModel):
    source_id: str
    relevant: bool
    why: str


class ClaimVerdict(BaseModel):
    claim_id: str
    claim: str
    verdict: ClaimVerdictValue
    verdict_label: str
    confidence: Confidence
    claim_interpretation: str = ""
    explanation: str
    reasoning_steps: list[str] = []
    evidence: list[EvidenceOut] = []
    sources_reviewed: list[SourceReviewOut] = []
    conflicts: list[str] = []
    missing_information: list[str] = []
    adjustments: list[str] = Field(
        default=[],
        description="Zmiany wprowadzone przez kontrolę deterministyczną względem odpowiedzi modelu",
    )
    model_verdict: ModelVerdictValue | None = Field(
        default=None, description="Werdykt zwrócony przez model przed kontrolą"
    )
    source_ids: list[str] = Field(default=[], description="Źródła pokazane modelowi")
    security_warnings: list[str] = Field(
        default=[], description="Wykryte próby manipulacji w treści twierdzenia"
    )
    freshness_flags: list[str] = Field(
        default=[],
        description="zrodla_archiwalne – model widział materiał archiwalny; "
        "werdykt_na_materiale_archiwalnym – dowody rozstrzygające są wyłącznie archiwalne",
    )
    context: str | None = Field(
        default=None,
        description="Fragment oryginalnego tekstu pokazany modelowi do interpretacji (nie dowód)",
    )
    model: str | None = None


class QuarantinedSource(BaseModel):
    """Źródło pominięte, bo zawiera próbę wstrzyknięcia instrukcji (nie trafia do modelu)."""

    source_id: str
    kind: SourceKind
    title: str = ""
    publisher: str = ""
    url: str | None = None
    reasons: list[str]


InputSourceStatus = Literal["cytowane", "pokazane_modelowi", "nieuzyte", "kwarantanna"]


class InputSourceOut(BaseModel):
    """Źródło, które przyszło na wejściu (od użytkownika albo z backendu), z linkiem.

    Status (od najważniejszego):
    - `kwarantanna`: odrzucone przez ochronę przed wstrzyknięciem, model go nie widział;
    - `cytowane`: zweryfikowany cytat z tego źródła jest dowodem w werdykcie;
    - `pokazane_modelowi`: model je ocenił, ale nie jest dowodem;
    - `nieuzyte`: nie pasowało do żadnego twierdzenia, więc nie trafiło do modelu.
    """

    source_id: str
    kind: SourceKind
    title: str = ""
    publisher: str = ""
    url: str | None = None
    published_at: str | None = None
    provider: str | None = None
    rating: str | None = None
    fetched_at: str | None = None
    age_days: int | None = None
    freshness_flags: list[str] = []
    status: InputSourceStatus
    shown_for_claims: list[str] = Field(
        default=[], description="Twierdzenia, przy których pokazano je modelowi"
    )
    cited_in_claims: list[str] = Field(
        default=[], description="Twierdzenia, w których jest zweryfikowanym dowodem"
    )


class TextVerdict(BaseModel):
    verdict: TextVerdictValue
    summary: str
    claims: list[ClaimVerdict]
    sources: list[ReferenceSource] = Field(
        default=[], description="Wszystkie źródła wzorcowe użyte w analizie"
    )
    quarantined_sources: list[QuarantinedSource] = Field(
        default=[], description="Źródła odrzucone przez ochronę przed wstrzyknięciem instrukcji"
    )
    input_sources: list[InputSourceOut] = Field(
        default=[],
        description="Wszystkie źródła z wejścia (użytkownik, backend) z linkami i statusem użycia",
    )
    warnings: list[str] = []
    analyzed_at: str | None = Field(
        default=None, description="Znacznik czasu analizy, ISO 8601 UTC (punkt odniesienia wieku)"
    )
    max_source_age_days: int | None = Field(
        default=None, description="Limit aktualności: starsze źródła to materiał archiwalny"
    )
    models: dict[str, str] = Field(
        default={},
        description="Skonfigurowane modele per etap, np. ekstrakcja_stwierdzen i werdykt",
    )
    prompt_version: str
