"""Budowa prawdziwych obiektów backendu (textAnalysis, apiReading) do testów zgodności.

Używane przez tests/test_backend_contract.py oraz do odświeżenia fixture:

    .venv/Scripts/python -m tests.backend_objects   # zapisuje tests/data/backend_*.json
"""

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2] / "backend"
DATA_DIR = Path(__file__).resolve().parent / "data"
FIXTURE = DATA_DIR / "backend_contract.json"

STATEMENTS = ["Szczepionki przeciw COVID-19 zawierają mikroczipy.", "Rysy leżą w Tatrach."]
FULL_TEXT = " ".join(STATEMENTS)
GOOGLE_PAYLOAD = {
    "text": "Szczepionki zawierają mikroczipy",
    "claimant": "Post w mediach społecznościowych",
    "claimDate": "2021-03-01T00:00:00Z",
    "claimReview": [
        {
            "publisher": {"name": "Demagog", "site": "demagog.org.pl"},
            "url": "https://demagog.org.pl/fake_news/mikroczipy",
            "title": "Szczepionki nie zawierają mikroczipów",
            "reviewDate": "2021-03-05T10:00:00Z",
            "textualRating": "Fałsz",
            "languageCode": "pl",
        }
    ],
}


def import_backend():
    if str(BACKEND_DIR) not in sys.path:
        sys.path.insert(0, str(BACKEND_DIR))
    from apiReading.exceptions import ApiAuthError
    from apiReading.models import (
        Category,
        FetchOutcome,
        FetchResult,
        Item,
        ReadingRequest,
        ReadingResult,
    )
    from textAnalysis.container import AnalysisDataContainer, KeywordItem

    return {
        "ApiAuthError": ApiAuthError,
        "Category": Category,
        "FetchOutcome": FetchOutcome,
        "FetchResult": FetchResult,
        "Item": Item,
        "ReadingRequest": ReadingRequest,
        "ReadingResult": ReadingResult,
        "AnalysisDataContainer": AnalysisDataContainer,
        "KeywordItem": KeywordItem,
    }


def build(b=None):
    """Zwraca (analysis, [wynik run() dla stwierdzenia, wynik run_full_text()])."""
    b = b or import_backend()
    now = datetime(2026, 11, 21, tzinfo=UTC)
    analysis = b["AnalysisDataContainer"]()
    analysis.populate(
        source_text=FULL_TEXT,
        category="Zdrowie i Medycyna",
        language_code="pl",
        confidence=0.9,
        context_reasoning="Tekst o szczepionkach i górach.",
        keywords=[b["KeywordItem"](term="szczepionka", context_note="przedmiot twierdzenia")],
        statements=STATEMENTS,
        total_sentences=2,
        security_warnings=[],
    )
    item = b["Item"](id="gfc-1", source="google_fact_check", payload=GOOGLE_PAYLOAD)
    ok = b["FetchOutcome"](
        source="google_fact_check",
        result=b["FetchResult"](source="google_fact_check", items=[item], fetched_at=now),
    )
    per_statement = b["ReadingResult"](
        request=b["ReadingRequest"](
            query=STATEMENTS[0], categories=[b["Category"].FACT_CHECK], language_code="pl"
        ),
        results=[ok],
        items=[item],
        categories_without_source=[],
        fetched_at=now,
        duration_ms=10,
    )
    failed = b["ReadingResult"](
        request=b["ReadingRequest"](
            query=STATEMENTS[1], categories=[b["Category"].FACT_CHECK], language_code="pl"
        ),
        results=[
            b["FetchOutcome"](
                source="google_fact_check",
                error=b["ApiAuthError"](
                    "google_fact_check", "API key is required", status_code=401
                ),
            )
        ],
        items=[],
        categories_without_source=[],
        fetched_at=now,
        duration_ms=1,
    )
    full_text = b["ReadingResult"](
        request=b["ReadingRequest"](
            query=FULL_TEXT,
            categories=[b["Category"].FACT_CHECK],
            language_code="pl",
            metadata={"analysis_category": "Zdrowie i Medycyna", "truncated": True},
        ),
        results=[ok],
        items=[item],
        categories_without_source=[],
        fetched_at=now,
        duration_ms=12,
    )
    return analysis, [per_statement, failed, full_text]


def dump(analysis, results) -> dict:
    return {
        "analysis": analysis.to_dict(),
        "reading_results": [r.model_dump(mode="json") for r in results],
    }


if __name__ == "__main__":
    DATA_DIR.mkdir(exist_ok=True)
    FIXTURE.write_text(
        json.dumps(dump(*build()), ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"Zapisano {FIXTURE}")
