"""WhatsApp Cloud API message shapes used by the adapter.

Incoming payloads follow the Cloud API webhook format and outgoing messages
follow the body of ``POST /{phone-number-id}/messages``. Keeping these shapes
means the simulator can later be replaced by the real WhatsApp transport
without touching the bot logic.
"""

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

# Limits documented by the WhatsApp Cloud API.
MAX_TEXT_BODY_CHARS = 4096
MAX_REPLY_BUTTONS = 3
MAX_BUTTON_TITLE_CHARS = 20
MAX_BUTTON_ID_CHARS = 256


class _Lenient(BaseModel):
    model_config = ConfigDict(extra="ignore")


class _TextContent(_Lenient):
    body: str


class _Reply(_Lenient):
    id: str
    title: str = ""


class _InteractiveContent(_Lenient):
    type: str
    button_reply: _Reply | None = None
    list_reply: _Reply | None = None


class _ButtonContent(_Lenient):
    # Quick-reply buttons of template messages arrive as ``type: "button"``.
    payload: str | None = None
    text: str = ""


class WebhookMessage(_Lenient):
    sender: str = Field(alias="from", min_length=1, max_length=64)
    id: str = Field(min_length=1, max_length=256)
    timestamp: str | None = None
    type: str
    text: _TextContent | None = None
    interactive: _InteractiveContent | None = None
    button: _ButtonContent | None = None


class _ChangeValue(_Lenient):
    messaging_product: str | None = None
    messages: list[WebhookMessage] = Field(default_factory=list)


class _Change(_Lenient):
    field: str = "messages"
    value: _ChangeValue


class _Entry(_Lenient):
    id: str | None = None
    changes: list[_Change] = Field(default_factory=list)


class WebhookPayload(_Lenient):
    object: str = Field(pattern="^whatsapp_business_account$")
    entry: list[_Entry] = Field(default_factory=list)


class IncomingKind(StrEnum):
    TEXT = "text"
    BUTTON = "button"
    WELCOME = "welcome"
    UNSUPPORTED = "unsupported"


@dataclass(frozen=True)
class IncomingMessage:
    """A user message reduced to what the bot needs."""

    sender: str
    message_id: str
    kind: IncomingKind
    text: str = ""
    button_id: str | None = None
    raw_type: str = ""


def parse_webhook(payload: dict[str, Any]) -> list[IncomingMessage]:
    """Extract user messages from a webhook payload.

    Status updates (delivery and read receipts) carry no ``messages`` and are
    skipped. Raises ``pydantic.ValidationError`` for malformed payloads.
    """

    parsed = WebhookPayload.model_validate(payload)
    incoming: list[IncomingMessage] = []
    for entry in parsed.entry:
        for change in entry.changes:
            if change.field != "messages":
                continue
            incoming.extend(_to_incoming(message) for message in change.value.messages)
    return incoming


def _to_incoming(message: WebhookMessage) -> IncomingMessage:
    common = {"sender": message.sender, "message_id": message.id, "raw_type": message.type}
    if message.type == "text" and message.text is not None:
        return IncomingMessage(kind=IncomingKind.TEXT, text=message.text.body, **common)
    if message.type == "interactive" and message.interactive is not None:
        reply = message.interactive.button_reply or message.interactive.list_reply
        if reply is not None:
            return IncomingMessage(
                kind=IncomingKind.BUTTON, text=reply.title, button_id=reply.id, **common
            )
    if message.type == "button" and message.button is not None:
        return IncomingMessage(
            kind=IncomingKind.BUTTON,
            text=message.button.text,
            button_id=message.button.payload,
            **common,
        )
    if message.type == "request_welcome":
        return IncomingMessage(kind=IncomingKind.WELCOME, **common)
    return IncomingMessage(kind=IncomingKind.UNSUPPORTED, **common)


@dataclass(frozen=True)
class ReplyButton:
    id: str
    title: str

    def __post_init__(self) -> None:
        if not 1 <= len(self.title) <= MAX_BUTTON_TITLE_CHARS:
            raise ValueError(f"button title must be 1-{MAX_BUTTON_TITLE_CHARS} characters")
        if not 1 <= len(self.id) <= MAX_BUTTON_ID_CHARS:
            raise ValueError(f"button id must be 1-{MAX_BUTTON_ID_CHARS} characters")


def text_message(to: str, body: str) -> dict[str, Any]:
    """Build a Cloud API text message; ``body`` must fit one WhatsApp message."""

    if not body.strip():
        raise ValueError("message body must not be empty")
    if len(body) > MAX_TEXT_BODY_CHARS:
        raise ValueError(f"message body exceeds {MAX_TEXT_BODY_CHARS} characters")
    return {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to,
        "type": "text",
        "text": {"preview_url": False, "body": body},
    }


def button_message(to: str, body: str, buttons: list[ReplyButton]) -> dict[str, Any]:
    """Build a Cloud API interactive message with up to three reply buttons."""

    if not 1 <= len(buttons) <= MAX_REPLY_BUTTONS:
        raise ValueError(f"interactive messages need 1-{MAX_REPLY_BUTTONS} buttons")
    if not body.strip() or len(body) > 1024:
        raise ValueError("interactive body must be 1-1024 characters")
    return {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to,
        "type": "interactive",
        "interactive": {
            "type": "button",
            "body": {"text": body},
            "action": {
                "buttons": [
                    {"type": "reply", "reply": {"id": button.id, "title": button.title}}
                    for button in buttons
                ]
            },
        },
    }


def split_text(body: str, limit: int = MAX_TEXT_BODY_CHARS) -> list[str]:
    """Split a long reply into WhatsApp-sized chunks at paragraph or line breaks."""

    body = body.strip()
    if len(body) <= limit:
        return [body] if body else []

    chunks: list[str] = []
    current = ""
    for paragraph in body.split("\n\n"):
        candidate = f"{current}\n\n{paragraph}" if current else paragraph
        if len(candidate) <= limit:
            current = candidate
            continue
        if current:
            chunks.append(current)
        current = ""
        for line in paragraph.split("\n"):
            candidate = f"{current}\n{line}" if current else line
            if len(candidate) <= limit:
                current = candidate
                continue
            if current:
                chunks.append(current)
            while len(line) > limit:
                chunks.append(line[:limit])
                line = line[limit:]
            current = line
    if current:
        chunks.append(current)
    return [chunk.strip() for chunk in chunks if chunk.strip()]
