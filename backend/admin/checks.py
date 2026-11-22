"""Pomocnicze odczyty raportu strony (``GET /api/check``, raport ``verification``) dla panelu.

Sam zapis sprawdzeń w dzienniku panelu robi ``admin.web.CheckJournal``; stąd bierze
trafienia w bazie EUvsDisinfo, z których powstaje alert ``rosyjska_dezinformacja``.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from typing import Any

MONITOR_ENV = "ADMIN_MONITOR"


def monitor_enabled() -> bool:
    """``ADMIN_MONITOR=off`` wyłącza rejestr (jak w bocie WhatsApp)."""
    return os.getenv(MONITOR_ENV, "on").strip().lower() not in {"0", "off", "false", "no"}


def _as_dict(value: Any) -> dict[str, Any]:
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    return dict(value) if isinstance(value, Mapping) else {}


def known_disinfo_matches(report: Any) -> list[dict[str, Any]]:
    """Trafienia w bazie EUvsDisinfo: ``claims_verdict.data.known_disinfo.matches``."""
    data = _as_dict(_as_dict(report).get("claims_verdict")).get("data")
    known = data.get("known_disinfo") if isinstance(data, Mapping) else None
    matches = known.get("matches") if isinstance(known, Mapping) else None
    return [dict(m) for m in matches or [] if isinstance(m, Mapping)]
