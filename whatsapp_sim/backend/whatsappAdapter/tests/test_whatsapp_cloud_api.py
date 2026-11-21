import pytest
from pydantic import ValidationError
from whatsappAdapter.cloud_api import (
    MAX_TEXT_BODY_CHARS,
    IncomingKind,
    ReplyButton,
    button_message,
    parse_webhook,
    split_text,
    text_message,
)


def webhook(*messages: dict) -> dict:
    return {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "WABA",
                "changes": [
                    {
                        "field": "messages",
                        "value": {"messaging_product": "whatsapp", "messages": list(messages)},
                    }
                ],
            }
        ],
    }


def test_parse_webhook_reads_text_button_and_welcome_messages() -> None:
    payload = webhook(
        {"from": "48500", "id": "wamid.1", "type": "text", "text": {"body": "Ziemia jest płaska"}},
        {
            "from": "48500",
            "id": "wamid.2",
            "type": "interactive",
            "interactive": {
                "type": "button_reply",
                "button_reply": {"id": "help", "title": "Jak to działa?"},
            },
        },
        {"from": "48500", "id": "wamid.3", "type": "request_welcome"},
        {"from": "48500", "id": "wamid.4", "type": "image", "image": {"id": "media"}},
    )

    messages = parse_webhook(payload)

    assert [m.kind for m in messages] == [
        IncomingKind.TEXT,
        IncomingKind.BUTTON,
        IncomingKind.WELCOME,
        IncomingKind.UNSUPPORTED,
    ]
    assert messages[0].text == "Ziemia jest płaska"
    assert messages[0].sender == "48500"
    assert messages[1].button_id == "help"
    assert messages[3].raw_type == "image"


def test_parse_webhook_ignores_status_updates() -> None:
    payload = webhook()
    payload["entry"][0]["changes"][0]["value"]["statuses"] = [{"id": "wamid.1", "status": "read"}]

    assert parse_webhook(payload) == []


def test_parse_webhook_rejects_other_objects() -> None:
    with pytest.raises(ValidationError):
        parse_webhook({"object": "page", "entry": []})


def test_text_message_uses_cloud_api_shape() -> None:
    assert text_message("48500", "Cześć") == {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": "48500",
        "type": "text",
        "text": {"preview_url": False, "body": "Cześć"},
    }
    with pytest.raises(ValueError):
        text_message("48500", "x" * (MAX_TEXT_BODY_CHARS + 1))


def test_button_message_enforces_whatsapp_limits() -> None:
    message = button_message("48500", "Wybierz", [ReplyButton("a", "Opcja A")])
    assert message["interactive"]["action"]["buttons"] == [
        {"type": "reply", "reply": {"id": "a", "title": "Opcja A"}}
    ]
    with pytest.raises(ValueError):
        ReplyButton("a", "x" * 21)
    with pytest.raises(ValueError):
        button_message("48500", "Wybierz", [ReplyButton(str(i), "Opcja") for i in range(4)])


def test_split_text_keeps_short_text_and_splits_long_text_at_paragraphs() -> None:
    assert split_text("  krótko  ") == ["krótko"]

    paragraphs = ["a" * 30, "b" * 30, "c" * 30]
    chunks = split_text("\n\n".join(paragraphs), limit=70)
    assert chunks == ["a" * 30 + "\n\n" + "b" * 30, "c" * 30]

    hard = split_text("x" * 25, limit=10)
    assert hard == ["x" * 10, "x" * 10, "x" * 5]
    assert all(len(chunk) <= 10 for chunk in hard)


def test_parse_webhook_reads_forwarded_context() -> None:
    payload = webhook(
        {
            "from": "48500",
            "id": "wamid.1",
            "type": "text",
            "text": {"body": "Łańcuszek"},
            "context": {"forwarded": True},
        },
        {
            "from": "48500",
            "id": "wamid.2",
            "type": "text",
            "text": {"body": "Łańcuszek"},
            "context": {"frequently_forwarded": True},
        },
        {"from": "48500", "id": "wamid.3", "type": "text", "text": {"body": "Własny tekst"}},
    )

    first, second, third = parse_webhook(payload)

    assert first.forwarded and not first.frequently_forwarded
    assert second.forwarded and second.frequently_forwarded
    assert not third.forwarded
