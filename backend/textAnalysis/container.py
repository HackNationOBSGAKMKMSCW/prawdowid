from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class KeywordItem:
    """Niemutowalny kontener na pojedyncze słowo kluczowe w kontekście."""

    term: str
    context_note: str


@dataclass
class AnalysisDataContainer:
    """Pusta klasa-kontener na dane, wypełniana dopiero po zakończeniu analizy."""

    source_text: str = ""
    source_url: str | None = None
    category: str = ""
    language_code: str | None = None
    confidence: float = 0.0
    context_reasoning: str = ""
    keywords: list[KeywordItem] = field(default_factory=list)
    statements: list[str] = field(default_factory=list)
    total_sentences: int = 0
    security_warnings: list[str] = field(default_factory=list)
    original_text: str = ""
    started_at: datetime | None = None

    def populate(
        self,
        *,
        source_text: str,
        original_text: str = "",
        started_at: datetime | None = None,
        category: str,
        language_code: str | None = None,
        confidence: float,
        context_reasoning: str,
        keywords: list[KeywordItem],
        statements: list[str],
        total_sentences: int,
        source_url: str | None = None,
        security_warnings: list[str] | None = None,
    ) -> None:
        """Wypełnia pusty kontener wynikami analizy."""
        self.source_text = source_text
        self.original_text = original_text
        self.started_at = started_at
        self.source_url = source_url
        self.category = category
        self.language_code = language_code
        self.confidence = confidence
        self.context_reasoning = context_reasoning
        self.keywords = keywords
        self.statements = statements
        self.total_sentences = total_sentences
        self.security_warnings = security_warnings or []

    @property
    def is_empty(self) -> bool:
        """Sprawdza, czy kontener nie został jeszcze wypełniony danymi."""
        return not bool(self.source_text or self.category)

    @property
    def is_safe(self) -> bool:
        """Zwraca False, jeśli podczas analizy wykryto podejrzane wzorce lub naruszenia schematu."""
        return len(self.security_warnings) == 0

    @property
    def keyword_terms(self) -> list[str]:
        """Zwraca listę samych haseł kluczowych."""
        return [kw.term for kw in self.keywords]

    def is_confident(self, threshold: float = 0.75) -> bool:
        """Sprawdza, czy pewność kategoryzacji przekracza zadany próg i wynik jest bezpieczny."""
        return self.is_safe and self.confidence >= threshold

    def to_dict(self) -> dict[str, Any]:
        """Konwertuje obiekt kontenera do słownika."""
        return asdict(self)
