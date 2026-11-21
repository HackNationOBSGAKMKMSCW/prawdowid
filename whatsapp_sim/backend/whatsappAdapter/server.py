"""HTTP endpoints of the WhatsApp adapter, used by the browser simulator.

``POST /api/whatsapp/webhook`` accepts a WhatsApp Cloud API webhook payload and
answers with the Cloud API message bodies the bot would send back. The real
WhatsApp transport would instead POST those bodies to the Graph API.
"""

import os
from typing import Any

from fastapi import Body, FastAPI, HTTPException
from pydantic import ValidationError

from .bot import BOT_NAME, SprawdzToBot
from .pipeline import DemoPipeline, FactCheckPipeline, LivePipeline

MODE_ENV = "SPRAWDZTO_MODE"
MAX_PAYLOAD_MESSAGES = 10


def pipeline_from_environment() -> FactCheckPipeline:
    mode = os.getenv(MODE_ENV, "live").strip().lower()
    if mode == "demo":
        return DemoPipeline()
    if mode != "live":
        raise ValueError(f"{MODE_ENV} must be 'live' or 'demo'")
    return LivePipeline()


def create_app(bot: SprawdzToBot | None = None) -> FastAPI:
    bot = bot or SprawdzToBot(pipeline_from_environment())
    app = FastAPI(title="SprawdzTo WhatsApp adapter", docs_url="/api/whatsapp/docs")

    @app.get("/api/whatsapp/health")
    async def health() -> dict[str, Any]:
        return {"status": "ok", "mode": bot.mode, "contact": {"name": BOT_NAME}}

    @app.post("/api/whatsapp/webhook")
    async def webhook(payload: dict[str, Any] = Body(...)) -> dict[str, Any]:  # noqa: B008
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
            messages = await bot.handle_webhook(payload)
        except ValidationError:
            raise HTTPException(status_code=422, detail="invalid webhook payload") from None
        return {"messages": messages}

    return app
