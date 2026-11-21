"""HTTP API panelu admina (``/api/admin``).

Uruchomienie z katalogu ``backend/``::

    ADMIN_API_TOKEN=... uvicorn admin.api:create_app --factory --port 8100

Każdy endpoint poza ``/health`` wymaga nagłówka ``Authorization: Bearer <ADMIN_API_TOKEN>``.
Bez ustawionego tokenu panel odpowiada 503 (jest wyłączony, a nie otwarty).
Opcjonalny nagłówek ``X-Admin-User`` trafia do audytu zmian konfiguracji.
"""

from __future__ import annotations

import hmac
import os
from collections import deque
from datetime import timedelta
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, Depends, FastAPI, Header, HTTPException, Query
from pydantic import BaseModel, Field

from .monitor import ADMIN_GAP_STATUSES, ALERT_STATUSES, ALERT_TYPES, Monitor, iso
from .runtime import RuntimeConfigStore, apply_config, public_view
from .settings import AdminSettings
from .store import AdminStore

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
) -> APIRouter:
    router = APIRouter(prefix="/api/admin")

    def require_admin(
        authorization: str | None = Header(default=None),
        x_admin_user: str | None = Header(default=None),
    ) -> str:
        if not settings.api_token:
            raise HTTPException(503, "Panel admina jest wyłączony: ustaw ADMIN_API_TOKEN.")
        scheme, _, token = (authorization or "").partition(" ")
        if scheme.lower() != "bearer" or not hmac.compare_digest(
            token.strip().encode(), settings.api_token.encode()
        ):
            raise HTTPException(401, "Nieprawidłowy token administratora.")
        return (x_admin_user or "admin").strip()[:64] or "admin"

    admin = [Depends(require_admin)]

    def log_path() -> Path:
        """Ten sam plik, do którego pisze observability (``LOG_FILE`` albo domyślny)."""
        from observability.logconfig import DEFAULT_LOG_FILE

        return log_file or Path(os.getenv("LOG_FILE") or DEFAULT_LOG_FILE)

    def not_found(what: str) -> HTTPException:
        return HTTPException(404, f"Nie znaleziono: {what}")

    @router.get("/health")
    def health() -> dict[str, Any]:
        return {"status": "ok", "enabled": bool(settings.api_token)}

    # --- przegląd ----------------------------------------------------------------------

    @router.get("/dashboard", dependencies=admin)
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

    @router.get("/queries", dependencies=admin)
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

    @router.get("/queries/{query_id}", dependencies=admin)
    def query(query_id: str) -> dict[str, Any]:
        item = monitor.store.get_query(query_id)
        if item is None:
            raise not_found(f"zapytanie {query_id}")
        return item

    @router.get("/events", dependencies=admin)
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

    @router.get("/events/summary", dependencies=admin)
    def events_summary(since: str | None = None) -> dict[str, Any]:
        from observability.report import iter_events, summarize

        return summarize(iter_events(log_path(), since))

    # --- użytkownicy -------------------------------------------------------------------

    @router.get("/users", dependencies=admin)
    def users(
        flagged: bool = False, blocked: bool = False, limit: int = Query(100, ge=1, le=1000)
    ) -> dict[str, Any]:
        items = monitor.store.list_users(
            flagged=flagged, blocked_at=iso(monitor.now()) if blocked else None, limit=limit
        )
        return {"items": items}

    @router.get("/users/{user_key}", dependencies=admin)
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

    @router.post("/users/{user_key}/block", dependencies=admin)
    def block(user_key: str, body: BlockRequest) -> dict[str, Any]:
        try:
            return monitor.block_user(user_key, body.hours, body.reason)
        except KeyError:
            raise not_found(f"użytkownik {user_key}") from None

    @router.post("/users/{user_key}/unblock", dependencies=admin)
    def unblock(user_key: str) -> dict[str, Any]:
        try:
            return monitor.unblock_user(user_key)
        except KeyError:
            raise not_found(f"użytkownik {user_key}") from None

    # --- alerty ------------------------------------------------------------------------

    @router.get("/alerts", dependencies=admin)
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

    @router.get("/alerts/{alert_id}", dependencies=admin)
    def alert(alert_id: str) -> dict[str, Any]:
        item = monitor.store.get_alert(alert_id)
        if item is None:
            raise not_found(f"alert {alert_id}")
        if item["type"] in ("luka_informacyjna", "kampania_dezinformacyjna"):
            item["topic"] = monitor.store.get_topic(item["subject"])
        return item

    @router.post("/alerts/{alert_id}", dependencies=admin)
    def update_alert(alert_id: str, body: AlertUpdate) -> dict[str, Any]:
        try:
            return monitor.set_alert_status(alert_id, body.status, body.note)
        except KeyError:
            raise not_found(f"alert {alert_id}") from None

    # --- luki informacyjne -------------------------------------------------------------

    @router.get("/info-gaps", dependencies=admin)
    def info_gaps(
        status: list[str] = Query(default=["aktywna", "w_uzupelnianiu"]),  # noqa: B008
        limit: int = Query(100, ge=1, le=1000),
        offset: int = Query(0, ge=0),
    ) -> dict[str, Any]:
        unknown = sorted(set(status) - set(GAP_FILTERS))
        if unknown:
            raise HTTPException(422, f"nieznany status luki: {', '.join(unknown)}")
        return {"items": monitor.store.list_gaps(status, limit=limit, offset=offset)}

    @router.get("/topics/{topic_id}", dependencies=admin)
    def topic(topic_id: str) -> dict[str, Any]:
        item = monitor.store.get_topic(topic_id)
        if item is None:
            raise not_found(f"temat {topic_id}")
        return item

    @router.post("/info-gaps/{topic_id}", dependencies=admin)
    def update_gap(topic_id: str, body: GapUpdate) -> dict[str, Any]:
        try:
            return monitor.set_gap_status(topic_id, body.status, body.note)
        except KeyError:
            raise not_found(f"temat {topic_id}") from None

    # --- konfiguracja: modele i kluczowe API --------------------------------------------

    @router.get("/config", dependencies=admin)
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
        patch: dict[str, dict[str, Any]], actor: str = Depends(require_admin)
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
            monitor.store.add_audit(iso(monitor.now()), actor, changes)
        return {"changes": changes, "config": public_view(config)}

    @router.get("/config/audit", dependencies=admin)
    def audit(limit: int = Query(100, ge=1, le=1000)) -> dict[str, Any]:
        return {"items": monitor.store.list_audit(limit)}

    @router.get("/config/models", dependencies=admin)
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

    @router.post("/maintenance/purge", dependencies=admin)
    def purge(body: PurgeRequest) -> dict[str, Any]:
        days = body.older_than_days or monitor.config.retention_days
        before = iso(monitor.now() - timedelta(days=days))
        return {"before": before, "deleted": monitor.store.purge(before)}

    return router


def create_app(
    settings: AdminSettings | None = None,
    *,
    monitor: Monitor | None = None,
    runtime: RuntimeConfigStore | None = None,
    log_file: Path | None = None,
) -> FastAPI:
    settings = settings or AdminSettings.from_environment()
    runtime = runtime or RuntimeConfigStore()
    monitor = monitor or Monitor(AdminStore(settings.db_path), settings, runtime)
    apply_config(runtime.load())
    monitor.purge_expired()

    app = FastAPI(title="Prawdowid — panel admina", docs_url="/api/admin/docs")
    try:
        from observability import ObservabilityMiddleware

        app.add_middleware(ObservabilityMiddleware, skip_paths=("/api/admin/health",))
    except ImportError:  # pragma: no cover - observability jest częścią backendu
        pass
    app.include_router(create_router(monitor, runtime, settings, log_file=log_file))
    app.state.monitor = monitor
    return app
