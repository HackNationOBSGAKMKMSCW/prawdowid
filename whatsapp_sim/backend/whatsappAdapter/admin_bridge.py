"""Most między botem a monitorem panelu admina (``backend/admin``).

Bot przed sprawdzeniem pyta monitor, czy wolno przetwarzać wiadomość (prośby o instrukcje
przemocy są odrzucane), a po sprawdzeniu zapisuje wynik. Numer telefonu nadawcy nie trafia
do monitora: rejestr panelu jest anonimowy. Na tej podstawie monitor
wykrywa luki informacyjne i możliwe ataki dezinformacyjne. Awaria monitora nigdy nie
przerywa rozmowy: bot wtedy działa dalej bez rejestru.
"""

from __future__ import annotations

import contextlib
import os
from typing import Any, Protocol

from apiReading.models import ReadingResult

from .formatting import _result_failed, _reviews_of
from .pipeline import CheckReport, VerifiedReport
from .verdicts import OverallVerdict, overall_verdict

MONITOR_ENV = "ADMIN_MONITOR"

# Werdykt fact-checków -> słownik monitora (jak w werdykcie analysis/).
_MONITOR_VERDICT: dict[OverallVerdict, str | None] = {
    OverallVerdict.FALSE: "falsz",
    OverallVerdict.TRUE: "prawda",
    OverallVerdict.MISLEADING: "czesciowo_potwierdzony",
    OverallVerdict.CONFLICTING: "sprzeczne_zrodla",
    OverallVerdict.UNVERIFIED: "brak_wystarczajacych_danych",
    OverallVerdict.NO_DATA: None,  # brak źródeł: monitor liczy to jako lukę
}


class AdminMonitor(Protocol):
    def screen(self, *, text: str, channel: str = ...) -> Any: ...

    def complete(self, query_id: str, **kwargs: Any) -> Any: ...


def monitor_from_environment() -> AdminMonitor | None:
    """Monitor procesu; ``ADMIN_MONITOR=off`` wyłącza rejestr."""
    if os.getenv(MONITOR_ENV, "on").strip().lower() in {"0", "off", "false", "no"}:
        return None
    try:
        from admin import get_monitor

        return get_monitor()
    except Exception as exc:  # noqa: BLE001 - bot ma działać także bez panelu
        print(f"[whatsappAdapter] Monitor admina niedostępny ({type(exc).__name__}).", flush=True)
        return None


def _result_verdict(result: ReadingResult) -> tuple[str | None, int | None]:
    if _result_failed(result):  # awaria źródeł to nie luka informacyjna
        return "blad_analizy", None
    reviews = [review for item in result.items for review in _reviews_of(item.payload)]
    overall = overall_verdict(review.verdict for review in reviews)
    return _MONITOR_VERDICT[overall], len(result.items)


# Werdykt strony (api_models.ClaimResponse) -> słownik monitora (jak api_adapter.VERDICT_MAP).
_WEB_TO_MONITOR = {
    "confirmed": "prawda",
    "false": "falsz",
    "misleading": "czesciowo_potwierdzony",
    "insufficient": "brak_wystarczajacych_danych",
    "unverifiable": "nieweryfikowalny",
}
# Kolejność ważności przy różnych werdyktach twierdzeń (najgorszy wygrywa).
_SEVERITY = (
    "falsz",
    "czesciowo_potwierdzony",
    "brak_wystarczajacych_danych",
    "nieweryfikowalny",
    "prawda",
)


def claims_from_verified(report: VerifiedReport) -> tuple[list[Any], str | None, int]:
    """Twierdzenia z wyniku strony: werdykt każdego, werdykt całości, liczba źródeł."""
    from admin import ClaimInput

    claims = []
    total_sources = 0
    for claim in getattr(report.response, "claims", None) or []:
        sources = len(claim.sources or [])
        total_sources += sources
        verdict = _WEB_TO_MONITOR.get(claim.verdict)
        claims.append(ClaimInput(text=claim.text, verdict=verdict, sources_count=sources))
    verdicts = {claim.verdict for claim in claims}
    overall = next((v for v in _SEVERITY if v in verdicts), None)
    return claims, overall, total_sources


def claims_from_report(report: CheckReport | VerifiedReport) -> tuple[list[Any], str | None, int]:
    """Twierdzenia z werdyktem, werdykt całości i liczba znalezionych źródeł."""
    if isinstance(report, VerifiedReport):
        return claims_from_verified(report)
    from admin import ClaimInput

    statements = [s for s in report.analysis.statements if s.strip()]
    claims = []
    all_reviews = []
    total_sources = 0
    for index, result in enumerate(report.results):
        verdict, sources = _result_verdict(result)
        total_sources += sources or 0
        all_reviews.extend(r for item in result.items for r in _reviews_of(item.payload))
        if report.searched_full_text or index >= len(statements):
            text = result.request.query or report.analysis.source_text
        else:
            text = statements[index]
        claims.append(ClaimInput(text=text, verdict=verdict, sources_count=sources))
    overall = _MONITOR_VERDICT[overall_verdict(review.verdict for review in all_reviews)]
    return claims, overall, total_sources


class AdminSession:
    """Rejestracja jednej wiadomości; każdy krok jest odporny na błędy monitora."""

    def __init__(self, monitor: AdminMonitor | None) -> None:
        self.monitor = monitor
        self.query_id: str | None = None
        self.completed = False

    def screen(self, user_id: str, text: str) -> str | None:
        """Zwraca komunikat odmowy albo ``None``, gdy wiadomość można sprawdzić.

        ``user_id`` (numer nadawcy) służy tylko rozmowie — do monitora go nie przekazujemy.
        """
        del user_id
        if self.monitor is None:
            return None
        try:
            decision = self.monitor.screen(text=text, channel="whatsapp")
        except Exception as exc:  # noqa: BLE001
            print(f"[whatsappAdapter] Monitor admina: błąd ({type(exc).__name__}).", flush=True)
            return None
        self.query_id = decision.query_id
        return None if decision.allowed else decision.message

    def complete(
        self, report: CheckReport | VerifiedReport | None = None, error: str | None = None
    ) -> str | None:
        """Zapisz wynik; zwraca komunikat o luce informacyjnej do dołączenia."""
        if self.monitor is None or self.query_id is None or self.completed:
            return None
        self.completed = True
        with contextlib.suppress(Exception):
            if report is None:
                self.monitor.complete(self.query_id, error=error or "brak_wyniku")
                return None
            claims, verdict, sources = claims_from_report(report)
            result = self.monitor.complete(
                self.query_id, claims=claims, verdict=verdict, sources_count=sources
            )
            return result.message
        return None
