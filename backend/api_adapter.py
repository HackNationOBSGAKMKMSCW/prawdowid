"""Allowlisted conversion from internal verification events to the UI contract."""

from collections.abc import Mapping
from typing import Any

from api_models import (
    CheckResponse,
    ClaimResponse,
    DateIssueResponse,
    DatesResponse,
    ExtractedDateResponse,
    ManipulationFragmentResponse,
    ManipulationResponse,
    SourceResponse,
    TextAnalysisResponse,
)

VERDICT_MAP = {
    "prawda": "confirmed",
    "prawdziwy": "confirmed",
    "falsz": "false",
    "falszywy": "false",
    "zawiera_falsz": "misleading",
    "czesciowo_potwierdzony": "misleading",
    "brak_wystarczajacych_danych": "insufficient",
    "nieweryfikowalny": "unverifiable",
    "blad_analizy": "insufficient",
}


class InvalidVerificationResult(ValueError):
    """The internal result cannot be represented by the documented UI schema."""


class VerificationFailed(RuntimeError):
    def __init__(self, part: str, kind: str):
        super().__init__(part)
        self.part = part
        self.kind = kind


def _as_dict(value: Any) -> dict[str, Any]:
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    if not isinstance(value, Mapping):
        raise InvalidVerificationResult("Expected a verification report object")
    return dict(value)


def _event_data(report: dict[str, Any], part: str) -> dict[str, Any]:
    event = report.get(part)
    if not isinstance(event, Mapping):
        raise InvalidVerificationResult(f"Missing {part} event")
    if event.get("status") != "ok":
        error = event.get("error") or {}
        kind = error.get("kind", "VerificationError") if isinstance(error, Mapping) else "VerificationError"
        raise VerificationFailed(part, str(kind))
    data = event.get("data")
    if not isinstance(data, Mapping):
        raise InvalidVerificationResult(f"Missing {part} event data")
    return dict(data)


def _map_source(raw: Mapping[str, Any]) -> SourceResponse:
    published_at = raw.get("published_at")
    return SourceResponse(
        quote=str(raw.get("quote") or ""),
        publisher=str(raw.get("publisher") or raw.get("source_title") or "Źródło"),
        url=raw.get("url"),
        year=str(published_at)[:4] if published_at else None,
        lang=raw.get("language"),
    )


def _map_claim(raw: Mapping[str, Any], fallback_explanation: str) -> ClaimResponse:
    verdict = VERDICT_MAP.get(str(raw.get("verdict", "")))
    if verdict is None:
        raise InvalidVerificationResult("Unsupported claim verdict")

    sources = [
        _map_source(source)
        for source in raw.get("evidence", [])
        if isinstance(source, Mapping)
    ]
    return ClaimResponse(
        verdict=verdict,
        text=str(raw.get("claim") or raw.get("text") or ""),
        explanation=str(raw.get("explanation") or fallback_explanation),
        sources=sources or None,
    )


def _map_input_analysis(data: dict[str, Any]) -> TextAnalysisResponse:
    manipulation_data = data.get("manipulation")
    manipulation = None
    if isinstance(manipulation_data, Mapping):
        fragments = [
            ManipulationFragmentResponse(
                quote=str(fragment.get("quote") or ""),
                start=int(fragment.get("start") or 0),
                end=int(fragment.get("end") or 0),
                category=str(fragment.get("category") or "OTHER"),
                explanation=str(fragment.get("explanation") or ""),
                confidence=float(fragment.get("confidence") or 0),
            )
            for fragment in manipulation_data.get("fragments", [])
            if isinstance(fragment, Mapping)
        ]
        manipulation = ManipulationResponse(
            manipulation_detected=bool(manipulation_data.get("manipulation_detected")),
            score=int(manipulation_data.get("score") or 0),
            fragments=fragments,
        )

    dates_data = data.get("dates")
    dates = None
    if isinstance(dates_data, Mapping):
        issues = [
            DateIssueResponse(
                code=str(issue.get("code") or "UNKNOWN"),
                severity=issue.get("severity", "low"),
                start=int(issue["start"]),
                source_id=issue.get("source_id"),
                delta_days=issue.get("delta_days"),
                description=issue.get("description"),
            )
            for issue in dates_data.get("issues", [])
            if isinstance(issue, Mapping) and issue.get("start") is not None
        ]
        extracted = [
            ExtractedDateResponse(
                start=int(item.get("start") or 0),
                what=str(item.get("what") or ""),
                source_date_from=item.get("source_date_from"),
            )
            for item in dates_data.get("extracted", [])
            if isinstance(item, Mapping)
        ]
        dates = DatesResponse(
            dates_consistent=bool(dates_data.get("dates_consistent")),
            article_date=dates_data.get("article_date"),
            issues=issues,
            extracted=extracted,
        )

    return TextAnalysisResponse(manipulation=manipulation, dates=dates)


def to_check_response(report: Any, *, result_id: str, input_type: str) -> CheckResponse:
    raw_report = _as_dict(report)
    _event_data(raw_report, "evidence")
    input_analysis = _event_data(raw_report, "input_analysis")
    claims_verdict = _event_data(raw_report, "claims_verdict")

    overall_verdict = claims_verdict.get("verdict")
    if overall_verdict == "blad_analizy":
        raise VerificationFailed("claims_verdict", "AnalysisError")

    summary = str(claims_verdict.get("summary") or "")
    claims = [
        _map_claim(claim, summary)
        for claim in claims_verdict.get("claims", [])
        if isinstance(claim, Mapping)
    ]

    source_names: dict[str, str] = {}
    for source in [*claims_verdict.get("sources", []), *claims_verdict.get("input_sources", [])]:
        if not isinstance(source, Mapping):
            continue
        source_id = source.get("source_id")
        source_name = source.get("publisher") or source.get("title")
        if source_id and source_name:
            source_names[str(source_id)] = str(source_name)

    return CheckResponse(
        id=result_id,
        input_type=input_type,
        claims=claims,
        analysis=_map_input_analysis(input_analysis),
        source_names=source_names or None,
    )
