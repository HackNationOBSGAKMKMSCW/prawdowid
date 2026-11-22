"""Most między stroną (``GET /api/check``, raport ``verification``) a monitorem panelu.

Każde udane sprawdzenie ze strony trafia do rejestru zapytań, a jego twierdzenia do tematów.
Twierdzenie bez pokrycia w danych (werdykt ``brak_wystarczajacych_danych`` albo
``nieweryfikowalny``) zwiększa licznik luki informacyjnej tematu; po przekroczeniu progu
admin dostaje alert ``luka_informacyjna`` (zob. ``monitor.Monitor._update_gap``).

Strona nie ma logowania, więc zapis jest anonimowy (``Monitor.screen(anonymous=True)``):
liczymy zapytania, a nie osoby, i nie stosujemy blokad użytkowników.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from typing import Any

from .monitor import ClaimInput, CompletionResult, Monitor

MONITOR_ENV = "ADMIN_MONITOR"
WEB_USER = "web"


def monitor_enabled() -> bool:
    """``ADMIN_MONITOR=off`` wyłącza rejestr (jak w bocie WhatsApp)."""
    return os.getenv(MONITOR_ENV, "on").strip().lower() not in {"0", "off", "false", "no"}


def _as_dict(value: Any) -> dict[str, Any]:
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    return dict(value) if isinstance(value, Mapping) else {}


def claims_from_report(report: Any) -> tuple[list[ClaimInput], str | None, int | None]:
    """Twierdzenia z werdyktem, werdykt całego tekstu i łączna liczba dowodów.

    Bierze ocenę tez (``claims_verdict``). Gdy ta ocena się nie udała, nie ma czego liczyć:
    awaria analizy to nie brak danych.
    """
    event = _as_dict(_as_dict(report).get("claims_verdict"))
    data = event.get("data")
    if event.get("status") != "ok" or not isinstance(data, Mapping):
        return [], None, None
    claims: list[ClaimInput] = []
    total = 0
    for raw in data.get("claims") or []:
        if not isinstance(raw, Mapping):
            continue
        text = str(raw.get("claim") or raw.get("text") or "").strip()
        if not text:
            continue
        evidence = raw.get("evidence") or []
        sources = len(evidence) if isinstance(evidence, list) else 0
        total += sources
        verdict = raw.get("verdict")
        claims.append(ClaimInput(text=text, verdict=str(verdict) if verdict else None, sources_count=sources))
    verdict = data.get("verdict")
    return claims, (str(verdict) if verdict else None), total


def record_check(
    text: str,
    report: Any,
    *,
    channel: str = WEB_USER,
    monitor: Monitor | None = None,
) -> CompletionResult | None:
    """Zapisz sprawdzenie ze strony w rejestrze panelu. Synchroniczne (baza), więc z kodu
    asynchronicznego wołaj przez ``asyncio.to_thread``. Zwraca ``None``, gdy rejestr jest
    wyłączony albo raport nie ma oceny tez.
    """
    if monitor is None:
        if not monitor_enabled():
            return None
        from . import get_monitor

        monitor = get_monitor()
    claims, verdict, sources = claims_from_report(report)
    if not claims and verdict is None:
        return None
    decision, result = monitor.record(
        user_id=WEB_USER,
        text=text,
        channel=channel,
        claims=claims,
        verdict=verdict,
        sources_count=sources,
        anonymous=True,
    )
    matches = known_disinfo_matches(report)
    if matches:
        monitor.register_known_disinformation(decision.query_id, matches, channel=channel)
    return result


def known_disinfo_matches(report: Any) -> list[dict[str, Any]]:
    """Trafienia w bazie EUvsDisinfo: ``claims_verdict.data.known_disinfo.matches``."""
    data = _as_dict(_as_dict(report).get("claims_verdict")).get("data")
    known = data.get("known_disinfo") if isinstance(data, Mapping) else None
    matches = known.get("matches") if isinstance(known, Mapping) else None
    return [dict(m) for m in matches or [] if isinstance(m, Mapping)]
