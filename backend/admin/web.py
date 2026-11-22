"""Dziennik panelu admina dla API strony (``GET /api/check``, ``POST /api/check/{id}/report``).

Każde sprawdzenie ze strony trafia do tego samego rejestru co wiadomości z bota WhatsApp
(kanał ``web``), więc panel widzi je w historii weryfikacji, statystykach, lukach
informacyjnych, alertach dezinformacji i u użytkowników serwisu. Zgłoszenie błędu
w wyniku dopisuje się do tego samego wpisu (identyfikator wyniku = identyfikator zapytania).

Zalogowany użytkownik strony (token z ``/api/auth``) jest rozpoznawany po koncie: wpis dostaje
``account_id`` (historia w ``GET /api/auth/me/queries``), a blokada w panelu dotyczy konta.
Anonimowy użytkownik to HMAC adresu IP (``AdminSettings.user_key``); w panelu widać tylko
końcówkę adresu. Za proxy adres klienta podaje uvicorn (``--proxy-headers --forwarded-allow-ips=...``).
Nieważny lub wygasły token nie blokuje sprawdzenia: jest wtedy anonimowe.

Błąd monitora nigdy nie psuje sprawdzenia: zapis jest pomijany i zostaje ostrzeżenie w logach.
Jedyny wyjątek to świadoma odmowa (zablokowany użytkownik, prośba o instrukcje przemocy).
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from typing import Any

from starlette.concurrency import run_in_threadpool

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


def client_id(request: Any) -> str:
    client = getattr(request, "client", None)
    host = getattr(client, "host", None) or "nieznany"
    return f"web:{host}"


def bearer_token(request: Any) -> str | None:
    scheme, _, token = (request.headers.get("authorization") or "").partition(" ")
    if scheme.lower() != "bearer":
        return None
    return token.strip() or None


class CheckJournal:
    """Zapis sprawdzeń ze strony w dzienniku panelu; bezpieczny przy awarii monitora.

    ``accounts`` (``AccountService``, gdy jest baza): sprawdzenia zalogowanych trafiają na konto.
    """

    def __init__(self, monitor: Monitor, accounts: Any = None) -> None:
        self.monitor = monitor
        self.accounts = accounts

    def identify(self, request: Any) -> tuple[str, int | None]:
        """``(identyfikator dla monitora, id konta)``; bez ważnego tokenu: adres IP."""
        token = bearer_token(request) if self.accounts is not None else None
        if token:
            try:
                auth = self.accounts.authenticate(token)
            except Exception as exc:  # noqa: BLE001 - błąd bazy: sprawdzenie anonimowe
                logger.warning("admin_journal_auth_failed error_type=%s", type(exc).__name__)
                auth = None
            if auth is not None:
                return f"konto:{auth.user.id}", auth.user.id
        return client_id(request), None

    async def screen(
        self, request: Any, text: str, *, query_id: str, request_id: str | None = None
    ) -> ScreenDecision | None:
        """``None``: monitor niedostępny (sprawdzamy dalej, bez wpisu w dzienniku)."""
        try:
            user_id, account_id = await run_in_threadpool(self.identify, request)
            return await run_in_threadpool(
                self.monitor.screen,
                user_id=user_id,
                text=text,
                channel=CHANNEL,
                request_id=request_id,
                query_id=query_id,
                account_id=account_id,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("admin_journal_failed step=screen error_type=%s", type(exc).__name__)
            return None

    async def complete(self, query_id: str, response: Any) -> None:
        claims, verdict, sources = claims_from_response(response)
        await self._call(
            "complete",
            query_id,
            claims=claims,
            verdict=verdict,
            sources_count=sources if claims else None,
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
