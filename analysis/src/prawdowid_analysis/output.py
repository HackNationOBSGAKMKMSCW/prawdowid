"""Skrócona postać wyniku (JSON odpowiedzi programu).

`TextVerdict` w pamięci zawiera wszystko (do kontroli, testów i trybu `--pelny`).
Odpowiedź dla użytkownika pomija powtórzenia i pola puste:

1. `sources[]` bez pełnej treści źródła (`text`) – cytowany fragment jest w dowodach;
2. `claims[].sources_reviewed[]` tylko `source_id`, `relevant`, `why` – metadane źródła
   są w `sources[]` pod tym samym `source_id`;
3. `claims[].source_freshness[]` tylko źródła z flagą aktualności, z wiekiem i flagą
   (daty publikacji i pobrania są w `sources[]`);
4. bez `claims[].context` (fragment tekstu wysłanego przez użytkownika);
5. bez drobnych duplikatów: `verdict_label`, `source_ids`, `model` przy twierdzeniu,
   `model_verdict` równego `verdict`, a w dowodach `fetched_at`, `age_days`,
   `freshness_flags`;
6. bez pól pustych (`null`, `""`, `[]`, `{}`).

Zasada nienaruszalna: tytuł, wydawca, data publikacji, link i cytowany fragment
(`title`/`source_title`, `publisher`, `published_at`, `url`, `quote`) są zawsze obecne
tam, gdzie opisują źródło – także jako `null`, gdy źródło ich nie ma.
"""

from typing import Any

from .schemas import TextVerdict

REQUIRED_SOURCE_KEYS = frozenset(
    {"title", "source_title", "publisher", "published_at", "url", "quote"}
)
_REVIEW_KEYS = ("source_id", "relevant", "why")
_FRESHNESS_KEYS = ("source_id", "age_days", "freshness_flags")
_CLAIM_DROP = ("context", "verdict_label", "source_ids", "model")
_EVIDENCE_DROP = ("fetched_at", "age_days", "freshness_flags")


def _is_empty(value: Any) -> bool:
    return value is None or value == "" or value == [] or value == {}


def _prune(value: Any) -> Any:
    """Usuwa puste pola (rekurencyjnie), z wyjątkiem wymaganych metadanych źródła."""
    if isinstance(value, dict):
        pruned = {}
        for key, item in value.items():
            item = _prune(item)
            if key in REQUIRED_SOURCE_KEYS or not _is_empty(item):
                pruned[key] = item
        return pruned
    if isinstance(value, list):
        return [_prune(item) for item in value]
    return value


def compact(verdict: TextVerdict) -> dict[str, Any]:
    """Skrócony wynik jako słownik gotowy do serializacji JSON."""
    data = verdict.model_dump(mode="json")
    for source in data.get("sources", []):
        source.pop("text", None)
    for claim in data.get("claims", []):
        for key in _CLAIM_DROP:
            claim.pop(key, None)
        if claim.get("model_verdict") == claim.get("verdict"):
            claim.pop("model_verdict", None)
        claim["sources_reviewed"] = [
            {key: review.get(key) for key in _REVIEW_KEYS}
            for review in claim.get("sources_reviewed", [])
        ]
        claim["source_freshness"] = [
            {key: entry.get(key) for key in _FRESHNESS_KEYS}
            for entry in claim.get("source_freshness", [])
            if entry.get("freshness_flags")
        ]
        for evidence in claim.get("evidence", []):
            for key in _EVIDENCE_DROP:
                evidence.pop(key, None)
    return _prune(data)
