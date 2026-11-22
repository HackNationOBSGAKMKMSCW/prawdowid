"""Production FastAPI application for the Prawdowid browser API."""

from __future__ import annotations

import asyncio
import os
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
    """
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        owns_store = store is None
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
    if _admin_panel_enabled(admin_panel):
        from admin.api import mount_admin
        from admin.web import CheckJournal

        app.state.journal = CheckJournal(mount_admin(app, monitor=monitor))
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
        skip_paths=("/health", "/api/health", "/docs", "/openapi.json"),
    )
    install_error_handlers(app)
    return app


app = create_app()
