import os
import re
from abc import ABC, abstractmethod

from dotenv import load_dotenv
from openai import OpenAI
from pydantic import BaseModel, Field

try:
    # Import przy uruchamianiu jako pakiet (np. from dataPreparation.keys import ...)
    from .container import AnalysisDataContainer, KeywordItem
except ImportError:
    # Import przy bezpośrednim uruchomieniu pliku (python keys.py)
    from container import AnalysisDataContainer, KeywordItem

load_dotenv()


class _ApiKeywordSchema(BaseModel):
    term: str
    context_note: str


class _ApiAnalysisSchema(BaseModel):
    """Wewnętrzny schemat walidacji odpowiedzi z API."""
    category: str
    confidence: float = Field(ge=0.0, le=1.0)
    context_reasoning: str
    keywords: list[_ApiKeywordSchema]
    statements: list[str]


class BaseTextAnalyzer(ABC):
    """Interfejs bazowy analizatora tekstu."""

    @abstractmethod
    def analyze(self, text: str, top_keywords: int = 5) -> AnalysisDataContainer:
        pass


class ProxyContextAnalyzer(BaseTextAnalyzer):
    """Analizator komunikujący się z API i zwracający wypełniony obiekt AnalysisDataContainer."""

    DEFAULT_CATEGORIES = [
        "Technologia i IT",
        "Biznes i Finanse",
        "Nauka i Edukacja",
        "Zdrowie i Medycyna",
        "Prawo i Administracja",
        "Kultura i Historia",
        "Ogólne / Inne",
    ]

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str = "auto",
        categories: list[str] | None = None,
    ):
        resolved_key = api_key or os.getenv("FREELLM_API_KEY")
        resolved_url = base_url or os.getenv("FREELLM_BASE_URL", "http://100.115.139.118:3001/v1")

        if not resolved_key:
            raise ValueError(
                "Brak klucza API. Ustaw FREELLM_API_KEY w pliku .env lub przekaż parametr api_key."
            )

        self.client = OpenAI(api_key=resolved_key, base_url=resolved_url)
        self.model = model
        self.categories = categories or self.DEFAULT_CATEGORIES

    @staticmethod
    def _clean_json_response(raw_content: str) -> str:
        cleaned = raw_content.strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
            cleaned = re.sub(r"\s*```$", "", cleaned)
        return cleaned

    def analyze(self, text: str, top_keywords: int = 5) -> AnalysisDataContainer:
        # 1. Inicjalizacja pustego kontenera z pliku container.py
        container = AnalysisDataContainer()

        raw_sentences = [s for s in re.split(r"(?<=[.!?])\s+", text.strip()) if s]
        allowed_categories = ", ".join(self.categories)

        system_instruction = (
            "Jesteś precyzyjnym analitykiem tekstu. Przeanalizuj tekst z uwzględnieniem "
            "pełnego kontekstu, intencji autora oraz powiązań między zdaniami.\n"
            f"1. Przypisz tekst wyłącznie do jednej z kategorii: [{allowed_categories}].\n"
            f"2. Wyodrębnij maksymalnie {top_keywords} słów lub fraz kluczowych (w mianowniku) "
            "wraz z krótkim opisem ich roli w kontekście wypowiedzi.\n"
            "3. Wyciągnij główne stwierdzenia i tezy wynikające z tekstu.\n"
            "4. Zwróć WYŁĄCZNIE poprawny obiekt JSON o dokładnie takiej strukturze:\n"
            '{\n'
            '  "category": "wybrana kategoria",\n'
            '  "confidence": 0.95,\n'
            '  "context_reasoning": "uzasadnienie wyboru kategorii w 1-2 zdaniach",\n'
            '  "keywords": [{"term": "słowo", "context_note": "znaczenie w tekście"}],\n'
            '  "statements": ["stwierdzenie 1", "stwierdzenie 2"]\n'
            '}'
        )

        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_instruction},
                {"role": "user", "content": text},
            ],
            temperature=0.2,
        )

        raw_output = response.choices[0].message.content or "{}"
        parsed = _ApiAnalysisSchema.model_validate_json(self._clean_json_response(raw_output))

        keyword_objects = [
            KeywordItem(term=item.term, context_note=item.context_note)
            for item in parsed.keywords[:top_keywords]
        ]

        # 2. Wypełnienie kontenera danymi z API
        container.populate(
            source_text=text,
            category=parsed.category,
            confidence=round(parsed.confidence, 2),
            context_reasoning=parsed.context_reasoning,
            keywords=keyword_objects,
            statements=parsed.statements,
            total_sentences=len(raw_sentences),
        )

        # 3. Zwrócenie gotowego obiektu
        return container


def run_analysis(text: str, top_keywords: int = 5) -> AnalysisDataContainer:
    """Funkcja wejściowa zwracająca wypełniony obiekt kontenera."""
    analyzer = ProxyContextAnalyzer(model="auto")
    return analyzer.analyze(text, top_keywords=top_keywords)


if __name__ == "__main__":
    print("Wklej tekst do analizy (naciśnij Enter, aby zatwierdzić):")
    user_text = input("> ").strip()

    if not user_text:
        user_text = (
            "Spółka odnotowała w trzecim kwartale wyraźny spadek marży operacyjnej "
            "z powodu rosnących kosztów łańcucha dostaw. Zarząd rozważa emisję obligacji, "
            "aby utrzymać płynność przed planowaną ekspansją na rynki zachodnie."
        )

    result_object: AnalysisDataContainer = run_analysis(user_text)

    print(f"\nKlasa obiektu: {type(result_object).__name__}")
    print(f"Kategoria: {result_object.category} (pewność: {result_object.confidence})")
    print(f"Uzasadnienie: {result_object.context_reasoning}")
    print(f"Słowa kluczowe: {result_object.keyword_terms}")
    print(f"Stwierdzenia: {result_object.statements}")
