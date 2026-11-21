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
    keywords: list[str] = field(default_factory=list)
    source_text: str = ""


def claims_from_analysis(analysis: Any) -> AnalysisClaims:
    """Wyciąga stwierdzenia, słowa kluczowe i tekst z wyniku `textAnalysis.run()`.

    `keywords` to lista `KeywordItem` (pole `term`) albo słowników po `to_dict()`.
    """
    statements = [_clean(s) for s in (_get(analysis, "statements") or [])]
    warnings = [str(w) for w in (_get(analysis, "security_warnings") or [])]
    keywords = [_clean(_get(k, "term")) for k in (_get(analysis, "keywords") or [])]
    return AnalysisClaims(
        statements=[s for s in statements if s],
        language_code=_get(analysis, "language_code"),
        category=_get(analysis, "category") or None,
        warnings=warnings,
        keywords=[k for k in keywords if k],
        source_text=str(_get(analysis, "source_text") or ""),
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


def _google_sources(payload: Any) -> list[ReferenceSource]:
    """Google Fact Check: `payload` to surowy obiekt `claims[]` (claimReview na recenzję)."""
    sources = []
    for review in _get(payload, "claimReview") or []:
        text = _fact_check_text(payload, review)
        rating = _clean(_get(review, "textualRating")) or None
        if not text or rating is None:
            continue  # bez oceny wpis nic nie rozstrzyga
        publisher = _get(review, "publisher") or {}
        url = _clean(_get(review, "url")) or None
        sources.append(
            ReferenceSource(
                source_id=_source_id("FC", url or "", text),
                kind="fact_check",
                title=_clean(_get(review, "title")),
                publisher=_clean(_get(publisher, "name")) or _clean(_get(publisher, "site")),
                url=url,
                published_at=_clean(_get(review, "reviewDate"))[:10] or None,
                text=text,
                rating=rating,
                language=_clean(_get(review, "languageCode")) or None,
                provider="google_fact_check",
            )
        )
    return sources


def _euvsdisinfo_sources(payload: Any) -> list[ReferenceSource]:
    """EUvsDisinfo: znormalizowany `payload` wg docs/plans/...-004 (pola wstępne,
    do potwierdzenia, gdy klient powstanie). Każdy wpis to udokumentowany przypadek
    dezinformacji, więc jego ocena to zawsze „dezinformacja”."""
    summary = _clean(_get(payload, "summary"))
    title = _clean(_get(payload, "title"))
    if not (summary or title):
        return []
    disproof = _get(payload, "disproof")
    if isinstance(disproof, Mapping):
        disproof = _get(disproof, "text") or _get(disproof, "url")
    rating = _clean(_get(payload, "rating")) or "disinformation"
    lines = [
        ("Przypadek dezinformacji", title),
        ("Opis przekazu", summary),
        ("Ocena EUvsDisinfo", rating),
        ("Sprostowanie", _clean(disproof)),
        ("Kraje", ", ".join(map(_clean, _get(payload, "countries") or []))),
    ]
    languages = [_clean(code) for code in _get(payload, "languages_of_outlet") or []]
    url = _clean(_get(payload, "url")) or None
    text = "\n".join(f"{label}: {value}" for label, value in lines if value)
    return [
        ReferenceSource(
            source_id=_source_id("EUVD", url or "", text),
            kind="fact_check",
            title=title,
            publisher=_clean(_get(payload, "source_name")) or "EUvsDisinfo",
            url=url,
            published_at=_clean(_get(payload, "published_at"))[:10] or None,
            text=text,
            rating=rating,
            language=languages[0] if len(languages) == 1 else None,
            provider="euvsdisinfo",
        )
    ]


_PROVIDER_PARSERS = {
    "google_fact_check": _google_sources,
    "euvsdisinfo": _euvsdisinfo_sources,
}


def _provider(item: Any) -> str | None:
    provider = _clean(_get(item, "source")) or None
    if provider is None and _get(_get(item, "payload"), "claimReview") is not None:
        return "google_fact_check"  # starsze dane bez pola source
    return provider


def fact_check_sources(items: Iterable[Any]) -> list[ReferenceSource]:
    """Zamienia elementy `Item` z `apiReading` na źródła wzorcowe.

    Format `payload` zależy od dostawcy (`item.source`); wpisy od dostawcy bez
    parsera są pomijane i zgłaszane przez `reading_warnings`.
    """
    sources: dict[str, ReferenceSource] = {}
    for item in items:
        parser = _PROVIDER_PARSERS.get(_provider(item) or "")
        if parser is None:
            continue
        for source in parser(_get(item, "payload") or {}):
            sources.setdefault(source.source_id, source)
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


def reading_warnings(results: Iterable[Any]) -> list[str]:
    """Wszystkie ostrzeżenia z wyników `apiReading`: błędy dostawców, obcięte
    zapytania pełnym tekstem i wpisy od dostawców bez parsera."""
    results = list(results or [])
    warnings = reading_errors(results)
    truncated = sum(
        1
        for result in results
        if _get(_get(_get(result, "request"), "metadata") or {}, "truncated") is True
    )
    if truncated:
        warnings.append(
            "Wyszukiwanie fact-checków pełnym tekstem objęło tylko początek tekstu "
            "(backend obcina zapytanie do 1000 znaków); dalsza część nie była wyszukiwana."
        )
    unsupported: dict[str, int] = {}
    for result in results:
        for item in _get(result, "items") or []:
            provider = _provider(item) or "nieznany"
            if provider not in _PROVIDER_PARSERS:
                unsupported[provider] = unsupported.get(provider, 0) + 1
    for provider, count in sorted(unsupported.items()):
        warnings.append(
            f"Pominięto {count} wpisów od dostawcy „{provider}”: brak obsługi jego formatu danych."
        )
    return warnings
