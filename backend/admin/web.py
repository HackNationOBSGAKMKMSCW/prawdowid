"""Dziennik panelu admina dla API strony (``GET /api/check``, ``POST /api/check/{id}/report``).

Każde sprawdzenie ze strony trafia do tego samego rejestru co wiadomości z bota WhatsApp
(kanał ``web``), więc panel widzi je w historii weryfikacji, statystykach, lukach
informacyjnych i alertach. Zgłoszenie błędu w wyniku dopisuje się do tego samego wpisu
(identyfikator wyniku = identyfikator zapytania).

Zapytania są anonimowe: do dziennika nie trafia adres IP ani żaden wyliczony z niego
pseudonim. Adres klienta (``client_ip.request_address``) monitor dostaje tylko po to, żeby
odrzucić zapytanie z adresu zablokowanego po prompt injection, a przy próbie prompt injection
zapisać go w blokadach jako klucz HMAC z maską.

Błąd monitora nigdy nie psuje sprawdzenia: zapis jest pomijany i zostaje ostrzeżenie w logach.
Jedyny wyjątek to świadoma odmowa (adres zablokowany, prośba o instrukcje przemocy).
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from typing import Any

from starlette.concurrency import run_in_threadpool

from .checks import known_disinfo_matches
from .client_ip import request_address
from .monitor import ClaimInput, Monitor, ScreenDecision

logger = logging.getLogger(__name__)

CHANNEL = "web"

# Werdykty API strony (api_models.ClaimResponse) → słownik monitora.
API_TO_MONITOR = {
    "false": "falsz",
    "confirmed": "prawda",
    "misleading": "czesciowo_potwierdzony",
    "insufficient": "brak_wystarczajacych_danych",
    "unverifiable": "nieweryfikowalny",
}


def query_id_for(result_id: Any) -> str:
    """Identyfikator wpisu w dzienniku dla wyniku z ``/api/check`` (UUID bez myślników)."""
    return getattr(result_id, "hex", None) or str(result_id).replace("-", "")


def overall_verdict(verdicts: Iterable[str]) -> str | None:
    """Werdykt całości: fałsz wygrywa, prawda tylko gdy wszystko potwierdzone."""
    found = [v for v in verdicts if v]
    if not found:
        return None
    if "false" in found:
        return API_TO_MONITOR["false"]
    if all(v == "confirmed" for v in found):
        return API_TO_MONITOR["confirmed"]
    if "misleading" in found:
        return API_TO_MONITOR["misleading"]
    return API_TO_MONITOR["insufficient"]


def claims_from_response(response: Any) -> tuple[list[ClaimInput], str | None, int]:
    """Twierdzenia, werdykt całości i liczba cytowanych źródeł z ``CheckResponse``."""
    claims: list[ClaimInput] = []
    total = 0
    for claim in response.claims:
        sources = len(claim.sources or [])
        total += sources
        claims.append(ClaimInput(claim.text, API_TO_MONITOR.get(claim.verdict), sources))
    return claims, overall_verdict(c.verdict for c in response.claims), total


class CheckJournal:
    """Zapis sprawdzeń ze strony w dzienniku panelu; bezpieczny przy awarii monitora."""

    def __init__(self, monitor: Monitor) -> None:
        self.monitor = monitor

    async def screen(
        self, request: Any, text: str, *, query_id: str, request_id: str | None = None
    ) -> ScreenDecision | None:
        """``None``: monitor niedostępny (sprawdzamy dalej, bez wpisu w dzienniku)."""
        try:
            return await run_in_threadpool(
                self.monitor.screen,
                text=text,
                channel=CHANNEL,
                request_id=request_id,
                query_id=query_id,
                client_ip=request_address(request) if request is not None else None,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("admin_journal_failed step=screen error_type=%s", type(exc).__name__)
            return None

    async def complete(self, query_id: str, response: Any, report: Any = None) -> None:
        """Wynik do dziennika; ``report`` (surowy raport ``verification``): trafienia w bazie
        EUvsDisinfo dają alert ``rosyjska_dezinformacja``."""
        claims, verdict, sources = claims_from_response(response)
        await self._call(
            "complete",
            query_id,
            claims=claims,
            verdict=verdict,
            sources_count=sources if claims else None,
        )
        matches = known_disinfo_matches(report)
        if matches:
            await self._call(
                "register_known_disinformation", query_id, matches, channel=CHANNEL
            )

    async def fail(self, query_id: str, code: str) -> None:
        await self._call("complete", query_id, error=code)

    async def report(self, query_id: str, reason: str, comment: str | None) -> None:
        await self._call("add_report", query_id, reason=reason, comment=comment)

    async def _call(self, method: str, *args: Any, **kwargs: Any) -> None:
        try:
            await run_in_threadpool(getattr(self.monitor, method), *args, **kwargs)
        except Exception as exc:  # noqa: BLE001
            logger.warning("admin_journal_failed step=%s error_type=%s", method, type(exc).__name__)
