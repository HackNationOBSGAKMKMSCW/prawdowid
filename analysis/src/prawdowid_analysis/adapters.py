"""Adapter wyników pakietów `backend/textAnalysis` i `backend/apiReading`.

Moduł nie importuje backendu: czyta pola obiektów (lub słowników po `model_dump()`
/ `to_dict()`), dzięki czemu `analysis/` nie zależy od kodu backendu.

- `claims_from_analysis(analysis)`: stwierdzenia i ostrzeżenia z `AnalysisDataContainer`.
- `sources_from_reading_results(results)`: źródła wzorcowe z `ReadingResult`
  pogrupowane po stwierdzeniu (`request.query`). Każda recenzja (`claimReview`)
  z Google Fact Check to osobne źródło.
"""

import hashlib
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

from .schemas import ReferenceSource


def _get(obj: Any, name: str, default: Any = None) -> Any:
    if obj is None:
        return default
    if isinstance(obj, Mapping):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _clean(value: Any) -> str:
    return " ".join(str(value).split()) if value not in (None, "") else ""


@dataclass
class AnalysisClaims:
    statements: list[str]
    language_code: str | None = None
    category: str | None = None
    warnings: list[str] = field(default_factory=list)


def claims_from_analysis(analysis: Any) -> AnalysisClaims:
    """Wyciąga stwierdzenia z obiektu zwróconego przez `textAnalysis.run()`."""
    statements = [_clean(s) for s in (_get(analysis, "statements") or [])]
    warnings = [str(w) for w in (_get(analysis, "security_warnings") or [])]
    return AnalysisClaims(
        statements=[s for s in statements if s],
        language_code=_get(analysis, "language_code"),
        category=_get(analysis, "category") or None,
        warnings=warnings,
    )


def _fact_check_text(claim: Any, review: Any) -> str:
    lines = [
        ("Sprawdzane twierdzenie", _clean(_get(claim, "text"))),
        ("Autor twierdzenia", _clean(_get(claim, "claimant"))),
        ("Data twierdzenia", _clean(_get(claim, "claimDate"))[:10]),
        ("Ocena fact-checkera", _clean(_get(review, "textualRating"))),
        ("Tytuł weryfikacji", _clean(_get(review, "title"))),
    ]
    return "\n".join(f"{label}: {value}" for label, value in lines if value)


def _source_id(prefix: str, *parts: str) -> str:
    digest = hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()[:8]
    return f"{prefix}-{digest}"


def fact_check_sources(items: Iterable[Any]) -> list[ReferenceSource]:
    """Zamienia elementy `Item` z Google Fact Check na źródła wzorcowe."""
    sources: dict[str, ReferenceSource] = {}
    for item in items:
        claim = _get(item, "payload") or {}
        for review in _get(claim, "claimReview") or []:
            text = _fact_check_text(claim, review)
            rating = _clean(_get(review, "textualRating")) or None
            if not text or rating is None:
                continue  # bez oceny wpis nic nie rozstrzyga
            publisher = _get(review, "publisher") or {}
            url = _clean(_get(review, "url")) or None
            source_id = _source_id("FC", url or "", text)
            sources[source_id] = ReferenceSource(
                source_id=source_id,
                kind="fact_check",
                title=_clean(_get(review, "title")),
                publisher=_clean(_get(publisher, "name")) or _clean(_get(publisher, "site")),
                url=url,
                published_at=_clean(_get(review, "reviewDate"))[:10] or None,
                text=text,
                rating=rating,
            )
    return list(sources.values())


def sources_from_reading_results(results: Iterable[Any]) -> dict[str, list[ReferenceSource]]:
    """Grupuje źródła z wyników `apiReading.run()` według stwierdzenia (`request.query`)."""
    grouped: dict[str, list[ReferenceSource]] = {}
    for result in results or []:
        query = _clean(_get(_get(result, "request"), "query"))
        if not query:
            continue
        bucket = grouped.setdefault(query, [])
        known = {s.source_id for s in bucket}
        bucket.extend(
            s for s in fact_check_sources(_get(result, "items") or []) if s.source_id not in known
        )
    return grouped


@dataclass
class FactCheckPools:
    """Wpisy fact-checkingowe rozdzielone wg tego, czego dotyczyło zapytanie.

    - `per_statement`: wyniki `apiReading.run()` – zapytanie = jedno stwierdzenie;
    - `shared`: wyniki, których zapytanie nie jest żadnym ze stwierdzeń, np.
      `apiReading.run_full_text()` (zapytanie = cały tekst). Potok dobiera z tej
      puli wpisy pasujące do każdego twierdzenia osobno.
    """

    per_statement: dict[str, list[ReferenceSource]] = field(default_factory=dict)
    shared: list[ReferenceSource] = field(default_factory=list)


def partition_fact_checks(results: Iterable[Any], statements: Iterable[str]) -> FactCheckPools:
    known_statements = {_clean(s) for s in statements}
    pools = FactCheckPools()
    shared_ids: set[str] = set()
    for query, sources in sources_from_reading_results(results).items():
        if query in known_statements:
            pools.per_statement[query] = sources
            continue
        for source in sources:
            if source.source_id not in shared_ids:
                shared_ids.add(source.source_id)
                pools.shared.append(source)
    return pools


_ERROR_MESSAGES: dict[str, str] = {
    "ApiAuthError": (
        "brak lub nieprawidłowy klucz API (np. GOOGLE_FACT_CHECK_API_KEY) – "
        "wpisy fact-checkingowe nie zostały pobrane"
    ),
    "ApiRateLimitError": "przekroczono limit zapytań dostawcy",
    "ApiTimeoutError": "przekroczono czas oczekiwania na odpowiedź",
    "ApiConnectionError": "brak połączenia z dostawcą",
    "ApiHttpError": "błąd HTTP po stronie dostawcy",
    "ApiResponseError": "dostawca zwrócił odpowiedź w nieoczekiwanym formacie",
    "InvalidFiltersError": "nieprawidłowe parametry zapytania",
    "NoSourcesAvailableError": "brak skonfigurowanego dostawcy",
}


def _error_kind(error: Any) -> str:
    if isinstance(error, Mapping):  # wynik po model_dump(): {"type", "message", ...}
        return str(error.get("type") or "Błąd")
    return type(error).__name__


def reading_errors(results: Iterable[Any]) -> list[str]:
    """Czytelne ostrzeżenia o błędach dostawców z wyników `apiReading`.

    Ten sam błąd powtarza się zwykle dla każdego zapytania (np. brak klucza API),
    więc jest zgłaszany raz, z liczbą zapytań, których dotyczy.
    """
    results = list(results or [])
    counts: dict[tuple[str, str], int] = {}
    missing_categories: set[str] = set()
    for result in results:
        for outcome in _get(result, "results") or []:
            error = _get(outcome, "error")
            if error is not None:
                key = (str(_get(outcome, "source") or "nieznane"), _error_kind(error))
                counts[key] = counts.get(key, 0) + 1
        for category in _get(result, "categories_without_source") or []:
            missing_categories.add(str(getattr(category, "value", category)))

    warnings = []
    for (source, kind), count in counts.items():
        description = _ERROR_MESSAGES.get(kind, "błąd dostawcy")
        warnings.append(
            f"Fact-checki ({source}): {description} [{kind}; zapytań: {count} z {len(results)}]."
        )
    if missing_categories:
        warnings.append(
            "Brak dostawcy danych dla kategorii: " + ", ".join(sorted(missing_categories)) + "."
        )
    return warnings
