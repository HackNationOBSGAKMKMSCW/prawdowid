"""HTTP API panelu admina (``/api/admin``).

Uruchomienie z katalogu ``backend/``::

    ADMIN_API_TOKEN=... uvicorn admin.api:create_app --factory --port 8100

Każdy endpoint poza ``/health`` wymaga nagłówka ``Authorization: Bearer <ADMIN_API_TOKEN>``.
Bez ustawionego tokenu panel odpowiada 503 (jest wyłączony, a nie otwarty).
Opcjonalny nagłówek ``X-Admin-User`` trafia do audytu zmian konfiguracji.
"""

from __future__ import annotations

import contextlib
import os
from collections import deque
from datetime import timedelta
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Query
from pydantic import BaseModel, Field

from .monitor import ADMIN_GAP_STATUSES, ALERT_STATUSES, ALERT_TYPES, Monitor, iso
from .runtime import RuntimeConfigStore, apply_config, public_view
from .settings import AdminSettings
from .store import AdminStore, PostgresAdminStore

GAP_FILTERS = ("podejrzenie", "aktywna", "w_uzupelnianiu", "zamknieta", "odrzucona")


class AlertUpdate(BaseModel):
    status: Literal["otwarty", "w_analizie", "rozwiazany", "falszywy_alarm"]
    note: str | None = Field(default=None, max_length=1000)


class GapUpdate(BaseModel):
    status: Literal["aktywna", "w_uzupelnianiu", "zamknieta", "odrzucona"]
    note: str | None = Field(default=None, max_length=1000)


class BlockRequest(BaseModel):
    hours: int | None = Field(default=24, ge=1, le=24 * 3650, description="None = bezterminowo")
    reason: str | None = Field(default=None, max_length=500)


class PurgeRequest(BaseModel):
    older_than_days: int | None = Field(default=None, ge=1, le=3650)


def known_api_clients() -> list[str]:
    from apiReading.clients import CLIENT_CLASSES

    return [client.name for client in CLIENT_CLASSES]


def create_router(
    monitor: Monitor,
    runtime: RuntimeConfigStore,
    settings: AdminSettings,
    *,
    log_file: Path | None = None,
    guard: Any = None,
    activity: Any = None,
) -> APIRouter:
    from accounts.api import Guard, Principal

    router = APIRouter(prefix="/api/admin")
    guard = guard or Guard(None, settings.api_token)

    def need(permission: str) -> Any:
        return Depends(guard.require(permission))

    def record(
        principal: Principal, action: str, subject_type: str, subject_id: str, **details: Any
    ) -> None:
        """Wpis w dzienniku działań (gdy jest baza); błąd dziennika nie psuje operacji."""
        if activity is None:
            return
        with contextlib.suppress(Exception):
            activity.record(
                action,
                principal.actor(),
                subject_type=subject_type,
                subject_id=subject_id,
                details=details,
            )

    def log_path() -> Path:
        """Ten sam plik, do którego pisze observability (``LOG_FILE`` albo domyślny)."""
        from observability.logconfig import DEFAULT_LOG_FILE

        return log_file or Path(os.getenv("LOG_FILE") or DEFAULT_LOG_FILE)

    def not_found(what: str) -> HTTPException:
        return HTTPException(404, f"Nie znaleziono: {what}")

    @router.get("/health")
    def health() -> dict[str, Any]:
        """Bez logowania: czy panel działa, czy ma konta i gdzie zapisuje dziennik zapytań."""
        database = getattr(monitor.store, "db", None)
        status = {"status": "ok", "enabled": guard.enabled, "store": "sqlite"}
        if database is not None:
            status["store"] = "postgres"
            try:
                database.fetch_value("SELECT 1")
                status["database"] = "ok"
            except Exception:  # noqa: BLE001 - szczegóły błędu zostają w logach serwera
                status["status"] = status["database"] = "error"
        return status

    # --- przegląd ----------------------------------------------------------------------

    @router.get("/dashboard", dependencies=[need("dashboard:read")])
    def dashboard(hours: int = Query(24, ge=1, le=24 * 365)) -> dict[str, Any]:
        now = monitor.now()
        since = iso(now - timedelta(hours=hours))
        return {
            "generated_at": iso(now),
            "window_hours": hours,
            **monitor.store.stats(since, iso(now)),
            "latest_alerts": monitor.store.list_alerts(status="otwarty", limit=10),
        }

    # --- logi użytkowników -------------------------------------------------------------

    @router.get("/queries", dependencies=[need("checks:read")])
    def queries(
        user: str | None = None,
        flag: str | None = Query(None, description="np. niebezpieczne, luka_informacyjna, falsz"),
        verdict: str | None = None,
        status: str | None = None,
        since: str | None = None,
        until: str | None = None,
        q: str | None = Query(None, max_length=200),
        limit: int = Query(50, ge=1, le=500),
        offset: int = Query(0, ge=0),
    ) -> dict[str, Any]:
        items, total = monitor.store.list_queries(
            user_key=user,
            flag=flag,
            verdict=verdict,
            status=status,
            since=since,
            until=until,
            search=q,
            limit=limit,
            offset=offset,
        )
        return {"total": total, "limit": limit, "offset": offset, "items": items}

    @router.get("/queries/{query_id}", dependencies=[need("checks:read")])
    def query(query_id: str) -> dict[str, Any]:
        item = monitor.store.get_query(query_id)
        if item is None:
            raise not_found(f"zapytanie {query_id}")
        return item

    @router.get("/events", dependencies=[need("security:read")])
    def events(
        event: str | None = None,
        request_id: str | None = None,
        level: str | None = None,
        since: str | None = None,
        limit: int = Query(200, ge=1, le=2000),
    ) -> dict[str, Any]:
        """Techniczne logi observability (JSON Lines), najnowsze na końcu."""
        from observability.report import iter_events

        path = log_path()
        tail: deque[dict[str, Any]] = deque(maxlen=limit)
        for item in iter_events(path, since):
            if event and item.get("event") != event:
                continue
            if request_id and item.get("request_id") != request_id:
                continue
            if level and str(item.get("level", "")).lower() != level.lower():
                continue
            tail.append(item)
        return {"file": str(path), "count": len(tail), "items": list(tail)}

    @router.get("/events/summary", dependencies=[need("security:read")])
    def events_summary(since: str | None = None) -> dict[str, Any]:
        from observability.report import iter_events, summarize

        return summarize(iter_events(log_path(), since))

    # --- użytkownicy -------------------------------------------------------------------

    @router.get("/users", dependencies=[need("endusers:read")])
    def users(
        flagged: bool = False, blocked: bool = False, limit: int = Query(100, ge=1, le=1000)
    ) -> dict[str, Any]:
        items = monitor.store.list_users(
            flagged=flagged, blocked_at=iso(monitor.now()) if blocked else None, limit=limit
        )
        return {"items": items}

    @router.get("/users/{user_key}", dependencies=[need("endusers:read")])
    def user(user_key: str) -> dict[str, Any]:
        item = monitor.store.get_user(user_key)
        if item is None:
            raise not_found(f"użytkownik {user_key}")
        recent, total = monitor.store.list_queries(user_key=user_key, limit=50)
        alerts = [
            alert
            for alert in monitor.store.list_alerts(alert_type="niebezpieczny_uzytkownik")
            if alert["subject"] == user_key
        ]
        return {**item, "total_queries": total, "recent_queries": recent, "alerts": alerts}

    @router.post("/users/{user_key}/block")
    def block(
        user_key: str, body: BlockRequest, principal: Principal = need("endusers:write")
    ) -> dict[str, Any]:
        try:
            result = monitor.block_user(user_key, body.hours, body.reason)
        except KeyError:
            raise not_found(f"użytkownik {user_key}") from None
        record(
            principal, "enduser.blocked", "end_user", user_key, hours=body.hours, reason=body.reason
        )
        return result

    @router.post("/users/{user_key}/unblock")
    def unblock(user_key: str, principal: Principal = need("endusers:write")) -> dict[str, Any]:
        try:
            result = monitor.unblock_user(user_key)
        except KeyError:
            raise not_found(f"użytkownik {user_key}") from None
        record(principal, "enduser.unblocked", "end_user", user_key)
        return result

    # --- alerty ------------------------------------------------------------------------

    @router.get("/alerts", dependencies=[need("alerts:read")])
    def alerts(
        type: str | None = Query(None, description=", ".join(ALERT_TYPES)),  # noqa: A002
        status: str | None = Query(None, description=", ".join(ALERT_STATUSES)),
        limit: int = Query(100, ge=1, le=1000),
        offset: int = Query(0, ge=0),
    ) -> dict[str, Any]:
        items = monitor.store.list_alerts(
            alert_type=type, status=status, limit=limit, offset=offset
        )
        return {"items": items}

    @router.get("/alerts/{alert_id}", dependencies=[need("alerts:read")])
    def alert(alert_id: str) -> dict[str, Any]:
        item = monitor.store.get_alert(alert_id)
        if item is None:
            raise not_found(f"alert {alert_id}")
        if item["type"] in ("luka_informacyjna", "kampania_dezinformacyjna"):
            item["topic"] = monitor.store.get_topic(item["subject"])
        return item

    @router.post("/alerts/{alert_id}")
    def update_alert(
        alert_id: str, body: AlertUpdate, principal: Principal = need("alerts:write")
    ) -> dict[str, Any]:
        try:
            result = monitor.set_alert_status(alert_id, body.status, body.note)
        except KeyError:
            raise not_found(f"alert {alert_id}") from None
        record(
            principal, "alert.status_changed", "alert", alert_id, status=body.status, note=body.note
        )
        return result

    # --- luki informacyjne -------------------------------------------------------------

    @router.get("/info-gaps", dependencies=[need("clusters:read")])
    def info_gaps(
        status: list[str] = Query(default=["aktywna", "w_uzupelnianiu"]),  # noqa: B008
        limit: int = Query(100, ge=1, le=1000),
        offset: int = Query(0, ge=0),
    ) -> dict[str, Any]:
        unknown = sorted(set(status) - set(GAP_FILTERS))
        if unknown:
            raise HTTPException(422, f"nieznany status luki: {', '.join(unknown)}")
        return {"items": monitor.store.list_gaps(status, limit=limit, offset=offset)}

    @router.get("/topics/{topic_id}", dependencies=[need("clusters:read")])
    def topic(topic_id: str) -> dict[str, Any]:
        item = monitor.store.get_topic(topic_id)
        if item is None:
            raise not_found(f"temat {topic_id}")
        return item

    @router.post("/info-gaps/{topic_id}")
    def update_gap(
        topic_id: str, body: GapUpdate, principal: Principal = need("alerts:write")
    ) -> dict[str, Any]:
        try:
            result = monitor.set_gap_status(topic_id, body.status, body.note)
        except KeyError:
            raise not_found(f"temat {topic_id}") from None
        record(
            principal, "info_gap.status_changed", "topic", topic_id, status=body.status, note=body.note
        )
        return result

    # --- konfiguracja: modele i kluczowe API --------------------------------------------

    @router.get("/config", dependencies=[need("settings:read")])
    def get_config() -> dict[str, Any]:
        config = runtime.load()
        apply_config(config)
        return {
            **public_view(config),
            "api_clients": known_api_clients(),
            "gap_statuses": list(ADMIN_GAP_STATUSES),
            "file": str(runtime.path),
        }

    @router.patch("/config")
    def patch_config(
        patch: dict[str, dict[str, Any]], principal: Principal = need("settings:write")
    ) -> dict[str, Any]:
        disabled = (patch.get("apis") or {}).get("disabled_clients")
        if disabled:
            unknown = sorted({str(n).strip().lower() for n in disabled} - set(known_api_clients()))
            if unknown:
                raise HTTPException(422, f"nieznani klienci API: {', '.join(unknown)}")
        try:
            config, changes = runtime.update(patch)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from None
        apply_config(config)
        if changes:
            monitor.store.add_audit(iso(monitor.now()), principal.label, changes)
            record(principal, "config.updated", "config", "runtime", changes=changes)
        return {"changes": changes, "config": public_view(config)}

    @router.get("/config/audit", dependencies=[need("audit:read")])
    def audit(limit: int = Query(100, ge=1, le=1000)) -> dict[str, Any]:
        return {"items": monitor.store.list_audit(limit)}

    @router.get("/config/models", dependencies=[need("models:read")])
    async def available_models() -> dict[str, Any]:
        """Modele zgłaszane przez skonfigurowany endpoint (``GET /models``)."""
        from openai import AsyncOpenAI

        apply_config(runtime.load())
        base_url = os.getenv("FREELLM_BASE_URL")
        try:
            client = AsyncOpenAI(
                api_key=os.getenv("FREELLM_API_KEY") or "brak",
                base_url=base_url,
                timeout=10,
                max_retries=0,
            )
            page = await client.models.list()
            models = sorted(model.id for model in page.data)
        except Exception as exc:  # dostawca niedostępny: panel ma pokazać przyczynę
            return {"base_url": base_url, "models": [], "error": type(exc).__name__}
        return {"base_url": base_url, "current": os.getenv("FREELLM_MODEL"), "models": models}

    # --- retencja ----------------------------------------------------------------------

    # --- strony zaufane: stan w rejestrze wyszukiwania ---------------------------------

    @router.get("/sources/status", dependencies=[need("sources:read")])
    def sources_status() -> list[dict[str, Any]]:
        """Jak weryfikacja widzi listę: wykryty sposób przeszukiwania i ostatnie sprawdzenie."""
        from trustedSources.registry import default_registry

        return [_registry_view(source) for source in default_registry().list()]

    @router.post("/sources/check")
    async def check_source(
        url: str = Query(..., min_length=8, max_length=2048),
        principal: Principal = need("sources:write"),
    ) -> dict[str, Any]:
        """Wykryj ponownie, jak przeszukiwać stronę (pobiera ją; może użyć modelu)."""
        from trustedSources.registry import RegistryError, default_registry
        from trustedSources.service import ensure_detected, search_context

        registry = default_registry()
        try:
            source = registry.find_by_url(url)
        except RegistryError as exc:
            raise HTTPException(400, str(exc)) from None
        if source is None:
            raise not_found(f"strona {url} w rejestrze")
        async with search_context() as ctx:
            [source] = await ensure_detected(registry, ctx, [source], force=True)
        check = source.last_check
        record(
            principal,
            "source.checked",
            "trusted_source",
            source.url,
            ok=bool(check and check.ok),
            adapter=source.adapter,
        )
        return _registry_view(source)

    @router.post("/maintenance/purge")
    def purge(body: PurgeRequest, principal: Principal = need("settings:write")) -> dict[str, Any]:
        days = body.older_than_days or monitor.config.retention_days
        before = iso(monitor.now() - timedelta(days=days))
        deleted = monitor.store.purge(before)
        record(principal, "maintenance.purged", "user_queries", before, deleted=deleted)
        return {"before": before, "deleted": deleted}

    return router


def mount_admin(
    app: FastAPI,
    settings: AdminSettings | None = None,
    *,
    monitor: Monitor | None = None,
    runtime: RuntimeConfigStore | None = None,
    log_file: Path | None = None,
    database: Any = None,
) -> Monitor:
    """Podepnij panel admina (``/api/admin``) pod aplikację; zwraca monitor zapytań.

    Używa tego samodzielny backend panelu (``create_app``) i API strony (``server.py``):
    wtedy ``/api/check`` zapisuje się w tym samym dzienniku, a zmiany modeli i źródeł z
    panelu działają od razu w procesie, który sprawdza informacje.

    Z bazą (``DATABASE_URL``): konta, logowanie, strony zaufane i dziennik działań.
    Bez bazy: rejestr w SQLite i dostęp tylko ``ADMIN_API_TOKEN``.
    ``ADMIN_STORE=sqlite`` wymusza tryb bez bazy (testy, praca lokalna).
    """
    settings = settings or AdminSettings.from_environment()
    runtime = runtime or RuntimeConfigStore()
    if database is None and monitor is None and os.getenv("ADMIN_STORE", "").lower() != "sqlite":
        from database import database_url, get_database

        if database_url():
            database = get_database()
    if monitor is None:
        store = PostgresAdminStore(database) if database is not None else AdminStore(settings.db_path)
        monitor = Monitor(store, settings, runtime)
    apply_config(runtime.load())
    monitor.purge_expired()

    from accounts.api import Guard

    accounts = activity = None
    if database is not None:
        from accounts import AccountService, ActivityLog, TrustedSourceRepository
        from accounts.api import create_auth_router, create_management_router

        activity = ActivityLog(database)
        accounts = AccountService(database, activity=activity)
        accounts.purge_expired_tokens()
        app.include_router(create_auth_router(accounts, prefix="/api/admin/auth", panel=True))
        app.include_router(
            create_management_router(
                Guard(accounts, settings.api_token),
                accounts,
                TrustedSourceRepository(database, activity),
                activity,
                on_sources_changed=_refresh_trusted_sources,
            )
        )
    guard = Guard(accounts, settings.api_token)
    app.include_router(
        create_router(monitor, runtime, settings, log_file=log_file, guard=guard, activity=activity)
    )
    app.state.monitor = monitor
    app.state.database = database
    return monitor


def create_app(
    settings: AdminSettings | None = None,
    *,
    monitor: Monitor | None = None,
    runtime: RuntimeConfigStore | None = None,
    log_file: Path | None = None,
    database: Any = None,
) -> FastAPI:
    """Samodzielny backend panelu (``uvicorn admin.api:create_app --factory --port 8100``).

    Zwykle panel działa w API strony (``server.py``) — ten tryb jest dla pracy nad samym
    panelem bez modeli i bez potoku weryfikacji.
    """
    app = FastAPI(title="Prawdowid — panel admina", docs_url="/api/admin/docs")
    try:
        from observability import ObservabilityMiddleware

        app.add_middleware(ObservabilityMiddleware, skip_paths=("/api/admin/health",))
    except ImportError:  # pragma: no cover - observability jest częścią backendu
        pass
    mount_admin(
        app, settings, monitor=monitor, runtime=runtime, log_file=log_file, database=database
    )
    return app


def _registry_view(source: Any) -> dict[str, Any]:
    check = source.last_check
    return {
        "id": source.id,
        "url": source.url,
        "name": source.name,
        "adapter": source.adapter,
        "trust": source.trust,
        "enabled": source.enabled,
        "domains": list(source.domains),
        "last_check": None
        if check is None
        else {
            "at": check.at.isoformat().replace("+00:00", "Z"),
            "ok": check.ok,
            "error": check.error,
        },
    }


def _refresh_trusted_sources() -> None:
    """Zmiana listy w panelu: rejestr weryfikacji i publiczna lista w tym procesie od razu."""
    try:
        from trustedSources.registry import default_registry

        default_registry().refresh()
    except Exception:  # noqa: BLE001, S110 - inne procesy przeładują listę same (co 5 min)
        pass
    try:
        import public_sources

        public_sources.reload()
    except Exception:  # noqa: BLE001, S110 - poza server.py modułu nie ma; lista odświeży się sama
        pass
