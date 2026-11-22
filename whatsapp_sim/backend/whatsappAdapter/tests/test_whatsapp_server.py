import json

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402
from whatsappAdapter.bot import WELCOME_TEXT, SprawdzToBot  # noqa: E402
from whatsappAdapter.pipeline import (  # noqa: E402
    DemoPipeline,
    LivePipeline,
    VerificationPipeline,
)
from whatsappAdapter.server import create_app, pipeline_from_environment  # noqa: E402


def payload(message: dict) -> dict:
    return {
        "object": "whatsapp_business_account",
        "entry": [{"changes": [{"field": "messages", "value": {"messages": [message]}}]}],
    }


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app(SprawdzToBot(DemoPipeline(delay_seconds=0))))


def test_health_reports_mode(client: TestClient) -> None:
    response = client.get("/api/whatsapp/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "mode": "demo", "contact": {"name": "SprawdzTo"}}


def test_webhook_answers_welcome_and_text(client: TestClient) -> None:
    welcome = client.post(
        "/api/whatsapp/webhook",
        json=payload({"from": "48500", "id": "wamid.1", "type": "request_welcome"}),
    )
    check = client.post(
        "/api/whatsapp/webhook",
        json=payload(
            {
                "from": "48500",
                "id": "wamid.2",
                "type": "text",
                "text": {"body": "Maszty 5G roznoszą koronawirusa"},
            }
        ),
    )

    assert welcome.status_code == 200
    assert welcome.json()["messages"][0]["text"]["body"] == WELCOME_TEXT
    assert check.status_code == 200
    card, details = check.json()["messages"]
    assert card["to"] == details["to"] == "48500"
    assert card["interactive"]["type"] == "cta_url"
    assert card["interactive"]["header"]["text"] == "Prawdopodobnie FAŁSZ"
    assert card["interactive"]["action"]["parameters"]["url"].startswith("https://example.org/")
    assert details["type"] == "text"


def test_webhook_streams_statuses_then_messages(client: TestClient) -> None:
    response = client.post(
        "/api/whatsapp/webhook?stream=true",
        json=payload(
            {
                "from": "48500",
                "id": "wamid.3",
                "type": "text",
                "text": {"body": "Szczepionki powodują autyzm"},
            }
        ),
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/x-ndjson")
    events = [json.loads(line) for line in response.text.splitlines()]
    assert [event["type"] for event in events] == ["status", "status", "messages"]
    assert events[0]["to"] == "48500"
    assert events[-1]["messages"][0]["interactive"]["type"] == "cta_url"


def test_streaming_rejects_invalid_payload_before_streaming(client: TestClient) -> None:
    response = client.post("/api/whatsapp/webhook?stream=true", json={"object": "page"})

    assert response.status_code == 422


def test_webhook_rejects_invalid_payloads(client: TestClient) -> None:
    assert client.post("/api/whatsapp/webhook", json={"object": "page"}).status_code == 422
    assert client.post("/api/whatsapp/webhook", json={"entry": "x"}).status_code == 422
    too_many = payload({"from": "1", "id": "w", "type": "request_welcome"})
    too_many["entry"][0]["changes"][0]["value"]["messages"] *= 11
    assert client.post("/api/whatsapp/webhook", json=too_many).status_code == 413


def test_pipeline_from_environment(monkeypatch) -> None:
    monkeypatch.setenv("SPRAWDZTO_MODE", "demo")
    assert isinstance(pipeline_from_environment(), DemoPipeline)
    monkeypatch.setenv("SPRAWDZTO_MODE", "factcheck")
    assert isinstance(pipeline_from_environment(), LivePipeline)
    monkeypatch.delenv("SPRAWDZTO_MODE")
    assert isinstance(pipeline_from_environment(), VerificationPipeline)
    monkeypatch.setenv("SPRAWDZTO_MODE", "nope")
    with pytest.raises(ValueError):
        pipeline_from_environment()
