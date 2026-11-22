"""HTTP endpoints of the WhatsApp adapter, used by the browser simulator.

``POST /api/whatsapp/webhook`` accepts a WhatsApp Cloud API webhook payload and
answers with the Cloud API message bodies the bot would send back. The real
WhatsApp transport would instead POST those bodies to the Graph API.
"""

import asyncio
import contextlib
import json
import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import Body, FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from observability import ObservabilityMiddleware
from pydantic import ValidationError
from trustedSources.api import router as trusted_sources_router

from .admin_bridge import monitor_from_environment
from .bot import BOT_NAME, SprawdzToBot
from .cloud_api import parse_webhook
from .pipeline import DemoPipeline, FactCheckPipeline, LivePipeline

PROJECT_ROOT = Path(__file__).resolve().parents[3]
load_dotenv(PROJECT_ROOT / ".env", override=False)
load_dotenv(PROJECT_ROOT / "backend" / ".env", override=False)

MODE_ENV = "SPRAWDZTO_MODE"
MAX_PAYLOAD_MESSAGES = 10
WARM_ENV = "TRUSTED_SOURCES_WARM"
logger = logging.getLogger(__name__)


def pipeline_from_environment() -> FactCheckPipeline:
    mode = os.getenv(MODE_ENV, "live").strip().lower()
    if mode == "demo":
        return DemoPipeline()
    if mode != "live":
        raise ValueError(f"{MODE_ENV} must be 'live' or 'demo'")
    return LivePipeline()


def create_app(bot: SprawdzToBot | None = None) -> FastAPI:
    bot = bot or SprawdzToBot(pipeline_from_environment(), monitor=monitor_from_environment())

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        task = None
        if bot.mode == "live" and os.getenv(WARM_ENV, "true").lower() not in {"0", "false", "no"}:
            task = asyncio.create_task(_warm_trusted_sources())
        try:
            yield
        finally:
            if task is not None and not task.done():
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task

    app = FastAPI(
        title="SprawdzTo WhatsApp adapter", docs_url="/api/whatsapp/docs", lifespan=lifespan
    )
    app.add_middleware(ObservabilityMiddleware, skip_paths=("/api/whatsapp/health",))
    app.include_router(trusted_sources_router)

    @app.get("/api/whatsapp/health")
    async def health() -> dict[str, Any]:
        return {"status": "ok", "mode": bot.mode, "contact": {"name": BOT_NAME}}

    @app.post("/api/whatsapp/webhook", response_model=None)
    async def webhook(
        payload: dict[str, Any] = Body(...),  # noqa: B008
        stream: bool = False,
    ) -> dict[str, Any] | StreamingResponse:
        try:
            entries = payload.get("entry") or []
            count = sum(
                len((change.get("value") or {}).get("messages") or [])
                for entry in entries
                if isinstance(entry, dict)
                for change in entry.get("changes") or []
                if isinstance(change, dict)
            )
        except (AttributeError, TypeError):
            raise HTTPException(status_code=422, detail="invalid webhook payload") from None
        if count > MAX_PAYLOAD_MESSAGES:
            raise HTTPException(status_code=413, detail="too many messages in one payload")
        try:
            parse_webhook(payload)
        except ValidationError:
            raise HTTPException(status_code=422, detail="invalid webhook payload") from None
        if stream:
            return StreamingResponse(
                _stream_events(bot, payload), media_type="application/x-ndjson"
            )
        return {"messages": await bot.handle_webhook(payload)}

    return app


async def _warm_trusted_sources() -> None:
    """Detect new whitelist entries and prefetch listing/feed pages in the background."""

    import trustedSources

    try:
        logger.info("trusted sources warmed: %s", await trustedSources.warm())
    except asyncio.CancelledError:
        raise
    except Exception:
        logger.exception("trusted source warm-up failed")


async def _stream_events(bot: SprawdzToBot, payload: dict[str, Any]) -> AsyncIterator[str]:
    """Yield NDJSON events: ``status`` lines while checking, then ``messages``.

    Status lines are a simulator feature; on real WhatsApp they would be sent
    as ordinary messages or replaced by the typing indicator.
    """

    queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()

    async def status(to: str, text: str) -> None:
        await queue.put({"type": "status", "to": to, "text": text})

    async def run() -> None:
        try:
            messages = await bot.handle_webhook(payload, status=status)
            await queue.put({"type": "messages", "messages": messages})
        except Exception as exc:  # noqa: BLE001 - reported to the client as an event
            await queue.put({"type": "error", "detail": type(exc).__name__})
        finally:
            await queue.put(None)

    task = asyncio.create_task(run())
    try:
        while (event := await queue.get()) is not None:
            yield json.dumps(event, ensure_ascii=False) + "\n"
    finally:
        if not task.done():
            task.cancel()
