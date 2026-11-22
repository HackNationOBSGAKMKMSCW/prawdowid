"""Production FastAPI application for the Prawdowid browser API."""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager
from pathlib import Path

from api_routes import (
    UrlValidator,
    _run_verification,
    _validate_public_url,
    install_error_handlers,
    router,
)
from api_store import PostgresStore
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from observability.middleware import ObservabilityMiddleware
from public_sources import router as trusted_sources_router
from request_limits import RequestSizeLimitMiddleware

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env", override=False)
load_dotenv(PROJECT_ROOT / "backend" / ".env", override=False)

StoreFactory = Callable[[], Awaitable[PostgresStore]]

# Kanał WhatsApp (whatsapp_sim/backend/whatsappAdapter) działa w tym samym backendzie:
# /api/whatsapp/* korzysta z tej samej weryfikacji co /api/check.
WHATSAPP_BACKEND = PROJECT_ROOT / "whatsapp_sim" / "backend"


def _whatsapp_router(monitor: object | None = None):
    if os.getenv("WHATSAPP_ENABLED", "true").strip().lower() in {"0", "false", "no", "off"}:
        return None
    if WHATSAPP_BACKEND.is_dir() and str(WHATSAPP_BACKEND) not in sys.path:
        sys.path.append(str(WHATSAPP_BACKEND))
    from whatsappAdapter.server import create_router

    return create_router(monitor=monitor)


def init_logging() -> None:
    """Logi serwera: ``backend/logs/app.jsonl`` (``LOG_FILE``) i ostrzeżenia na konsoli.

    ``LOG_CONSOLE=true`` wypisuje na konsolę wszystko (etapy, wywołania modeli, czasy).
    Plik czyta też panel admina (Logi techniczne). Bez tego wywołania serwer nie zapisywał
    żadnych logów, a zdarzenia poziomu INFO nigdzie się nie pojawiały.
    """
    import observability
    from verification import _analysis

    _analysis.add_paths()  # przed init(): etapy z analysis/ też dostają pomiar czasu
    if observability.init():
        logging.getLogger(__name__).info(
            "server_logging log_file=%s console=%s",
            os.getenv("LOG_FILE") or "backend/logs/app.jsonl",
            os.getenv("LOG_CONSOLE") or "false",
        )


def _cors_origins() -> list[str]:
    return [origin.strip() for origin in os.getenv("CORS_ORIGINS", "").split(",") if origin.strip()]


def _admin_panel_enabled(flag: bool | None) -> bool:
    if flag is not None:
        return flag
    return os.getenv("ADMIN_PANEL", "on").strip().lower() not in {"0", "off", "false", "no"}


def create_app(
    *,
    store: object | None = None,
    store_factory: StoreFactory | None = None,
    verification_runner: Callable | None = None,
    url_validator: UrlValidator | None = None,
    admin_panel: bool | None = None,
    monitor: object | None = None,
) -> FastAPI:
    """API strony; ``admin_panel`` (domyślnie ``ADMIN_PANEL``, włączony): ``/api/admin``.

    Z panelem każde ``/api/check`` i zgłoszenie trafia do dziennika zapytań panelu
    (``admin.web.CheckJournal``). ``monitor``: gotowy monitor (testy).
    Prawdziwy serwer (bez ``store``) zapisuje logi (``init_logging``): z nich panel buduje raport
    zagrożeń (``/api/admin/threats``), w tym próby prompt injection.
    """
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        owns_store = store is None
        if owns_store:  # prawdziwy serwer (testy podają własny store i nie piszą logów)
            init_logging()
        active_store = (
            await (store_factory or PostgresStore.connect_from_environment)()
            if owns_store
            else store
        )
        app.state.store = active_store
        try:
            yield
        finally:
            if owns_store:
                await active_store.close()

    app = FastAPI(
        title="Prawdowid API",
        version="1.0.0",
        lifespan=lifespan,
    )
    app.state.verification_runner = verification_runner or _run_verification
    app.state.url_validator = url_validator or _validate_public_url
    max_concurrent_checks = int(os.getenv("MAX_CONCURRENT_CHECKS", "4"))
    if max_concurrent_checks < 1:
        raise ValueError("MAX_CONCURRENT_CHECKS must be at least 1")
    app.state.check_semaphore = asyncio.Semaphore(max_concurrent_checks)
    app.include_router(router)
    app.include_router(trusted_sources_router)
    app.state.journal = None
    panel_monitor = monitor
    if _admin_panel_enabled(admin_panel):
        from admin.api import mount_admin
        from admin.web import CheckJournal

        panel_monitor = mount_admin(app, monitor=monitor)
        app.state.journal = CheckJournal(panel_monitor)
    # WhatsApp pisze do tego samego dziennika panelu co /api/check (jeden monitor w procesie).
    whatsapp = _whatsapp_router(panel_monitor)
    if whatsapp is not None:
        app.include_router(whatsapp)
    app.add_middleware(RequestSizeLimitMiddleware, max_body_bytes=96 * 1024)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_origins(),
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type", "X-Request-ID"],
        expose_headers=["X-Request-ID"],
    )
    app.add_middleware(
        ObservabilityMiddleware,
        skip_paths=("/health", "/api/health", "/api/whatsapp/health", "/docs", "/openapi.json"),
    )
    install_error_handlers(app)
    return app


app = create_app()
