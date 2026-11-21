from dataclasses import asdict, dataclass, field
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
    category: str = ""
    confidence: float = 0.0
    context_reasoning: str = ""
    keywords: list[KeywordItem] = field(default_factory=list)
    statements: list[str] = field(default_factory=list)
    total_sentences: int = 0

    def populate(
        self,
        *,
        source_text: str,
        category: str,
        confidence: float,
        context_reasoning: str,
        keywords: list[KeywordItem],
        statements: list[str],
        total_sentences: int,
    ) -> None:
        """Wypełnia pusty kontener wynikami analizy."""
        self.source_text = source_text
        self.category = category
        self.confidence = confidence
        self.context_reasoning = context_reasoning
        self.keywords = keywords
        self.statements = statements
        self.total_sentences = total_sentences

    @property
    def is_empty(self) -> bool:
        """Sprawdza, czy kontener nie został jeszcze wypełniony danymi."""
        return not bool(self.source_text or self.category)

    @property
    def keyword_terms(self) -> list[str]:
        """Zwraca listę samych haseł kluczowych."""
        return [kw.term for kw in self.keywords]

    def is_confident(self, threshold: float = 0.75) -> bool:
        """Sprawdza, czy pewność kategoryzacji przekracza zadany próg."""
        return self.confidence >= threshold

    def to_dict(self) -> dict[str, Any]:
        """Konwertuje obiekt kontenera do słownika."""
        return asdict(self)
