"""Backend panelu admina: logi zapytań użytkowników, luki informacyjne, alerty
bezpieczeństwa (treści niebezpieczne, możliwe ataki dezinformacyjne) i zmiana modeli oraz
kluczowych API w trakcie działania.

Integracja z potokiem (np. bot WhatsApp)::

    from admin import ClaimInput, get_monitor

    monitor = get_monitor()
    decision = monitor.screen(text=text, channel="whatsapp")  # anonimowo: bez numeru nadawcy
    if not decision.allowed:
        reply(decision.message)
    else:
        ...  # textAnalysis -> apiReading -> werdykt
        result = monitor.complete(decision.query_id, claims=[ClaimInput(...)], verdict=...)

API HTTP: ``uvicorn admin.api:create_app --factory`` (z katalogu ``backend/``).
"""

from __future__ import annotations

import threading

from .monitor import ClaimInput, ClaimState, CompletionResult, Monitor, ScreenDecision
from .runtime import RuntimeConfig, RuntimeConfigStore, apply_runtime_overrides
from .settings import AdminSettings
from .store import AdminStore, PostgresAdminStore, open_store

__all__ = [
    "AdminSettings",
    "AdminStore",
    "PostgresAdminStore",
    "ClaimInput",
    "ClaimState",
    "CompletionResult",
    "Monitor",
    "RuntimeConfig",
    "RuntimeConfigStore",
    "ScreenDecision",
    "apply_runtime_overrides",
    "get_monitor",
]

_monitor: Monitor | None = None
_lock = threading.Lock()


def get_monitor() -> Monitor:
    """Wspólny monitor procesu (PostgreSQL z ``DATABASE_URL`` albo SQLite ``ADMIN_DB_PATH``)."""
    global _monitor
    with _lock:
        if _monitor is None:
            settings = AdminSettings.from_environment()
            _monitor = Monitor(open_store(settings), settings, RuntimeConfigStore())
        return _monitor
