import os
import json
import re
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI
from pydantic import BaseModel, Field

load_dotenv()


@dataclass
class AnalysisResult:
    """Niezależny od dostawcy model danych przechowujący wynik analizy tekstu."""
    category: str
    confidence: float
    context_reasoning: str
    keywords: list[dict[str, str]]
    statements: list[str]
    total_sentences: int


class _KeywordItem(BaseModel):
    term: str = Field(description="Słowo lub fraza kluczowa w formie podstawowej (mianownik).")
    context_note: str = Field(description="Krótkie wyjaśnienie roli tego pojęcia w kontekście tekstu.")


class _AnalysisSchema(BaseModel):
    """Schemat Pydantic walidujący strukturę JSON zwróconą przez API."""
    category: str
    confidence: float = Field(ge=0.0, le=1.0)
    context_reasoning: str
    keywords: list[_KeywordItem]
    statements: list[str]


class BaseTextAnalyzer(ABC):
    """Abstrakcyjna klasa bazowa definiująca interfejs analizatora."""

    @abstractmethod
    def analyze(self, text: str, top_keywords: int = 5) -> AnalysisResult:
        pass


class ProxyContextAnalyzer(BaseTextAnalyzer):
    """Analizator łączący się z serwerem proxy kompatybilnym z OpenAI API."""

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
        """Usuwa ewentualne znaczniki markdown ```json ... ``` wokół odpowiedzi."""
        cleaned = raw_content.strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
            cleaned = re.sub(r"\s*```$", "", cleaned)
        return cleaned

    def analyze(self, text: str, top_keywords: int = 5) -> AnalysisResult:
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
        parsed = _AnalysisSchema.model_validate_json(self._clean_json_response(raw_output))

        return AnalysisResult(
            category=parsed.category,
            confidence=round(parsed.confidence, 2),
            context_reasoning=parsed.context_reasoning,
            keywords=[item.model_dump() for item in parsed.keywords[:top_keywords]],
            statements=parsed.statements,
            total_sentences=len(raw_sentences),
        )


class JsonExporter:
    """Klasa odpowiedzialna za serializację i zapis wyników do pliku JSON."""

    def __init__(self, output_path: str | Path = "wynik_analizy.json"):
        self.output_path = Path(output_path)

    def save(self, result: AnalysisResult) -> Path:
        data = asdict(result)
        with self.output_path.open("w", encoding="utf-8") as file:
            json.dump(data, file, ensure_ascii=False, indent=4)
        return self.output_path


if __name__ == "__main__":
    print("Wklej tekst do analizy (naciśnij Enter, aby zatwierdzić):")
    user_text = input("> ").strip()


    #print(os.getenv("FREELLM_API_KEY"))
    if not user_text:
        user_text = (
            "Spółka odnotowała w trzecim kwartale wyraźny spadek marży operacyjnej "
            "z powodu rosnących kosztów łańcucha dostaw. Zarząd rozważa emisję obligacji, "
            "aby utrzymać płynność przed planowaną ekspansją na rynki zachodnie. "
            "Czy akcjonariusze zaakceptują nową strategię?"
        )

    # Domyślnie używa model="auto"; możesz też wpisać konkretną nazwę z zakładki "Modele"
    analyzer = ProxyContextAnalyzer(model="auto")
    analysis_result = analyzer.analyze(user_text, top_keywords=5)

    exporter = JsonExporter("wynik_analizy.json")
    saved_file = exporter.save(analysis_result)

    print(f"Kategoria: {analysis_result.category} (pewność: {analysis_result.confidence})")
    print(f"Uzasadnienie kontekstowe: {analysis_result.context_reasoning}")
    print(f"Zapisano wynik do pliku: {saved_file.resolve()}")
