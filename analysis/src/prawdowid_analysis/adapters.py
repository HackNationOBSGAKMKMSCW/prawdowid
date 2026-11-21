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


def reading_errors(results: Iterable[Any]) -> list[str]:
    """Błędy dostawców z wyników `apiReading` (do ostrzeżeń w raporcie)."""
    errors: list[str] = []
    for result in results or []:
        for outcome in _get(result, "results") or []:
            error = _get(outcome, "error")
            if error is not None:
                kind = _get(error, "type") or type(error).__name__
                errors.append(f"Źródło {_get(outcome, 'source')}: {kind}")
    return errors
