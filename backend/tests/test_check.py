import pytest
from fastapi.testclient import TestClient

from main import app


@pytest.fixture
def client():
    return TestClient(app)


def test_text_input_returns_status_and_passages(client):
    r = client.post("/api/check", json={"input": "Czy opłata za paszport wzrośnie trzykrotnie?"})
    assert r.status_code == 200
    body = r.json()
    assert body["input_type"] == "text"
    assert body["retriever"] == "mock_retrieve"
    assert 3 <= len(body["passages"]) <= 4
    assert len(body["claims"]) == 1
    verdict = body["verdicts"][0]
    # Bez logiki werdyktu nigdy nie zwracamy pozornego werdyktu.
    assert verdict["outcome_class"] == "status"
    assert verdict["outcome"] == "cannot_check"
    assert verdict["claim_id"] == body["claims"][0]["claim_id"]


def test_url_is_detected_and_returns_status(client):
    r = client.post("/api/check", json={"input": "https://example.org/artykul"})
    assert r.status_code == 200
    body = r.json()
    assert body["input_type"] == "url"
    assert body["verdicts"][0]["outcome"] == "cannot_check"
    assert body["passages"] == []


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"input": ""},
        {"input": "  a "},
        {"input": "x" * 10_001},
        {"input": "tekst\x00ze znakiem sterującym"},
        {"input": "poprawny tekst", "channel": "telegraf"},
        {"input": "poprawny tekst", "extra": 1},
        {"input": "ftp://example.org/plik", "input_type": "url"},
        {"input": "http://localhost:8000/admin", "input_type": "url"},
        {"input": "http://127.0.0.1/", "input_type": "url"},
        {"input": "http://10.0.0.5/", "input_type": "url"},
        {"input": "http://169.254.169.254/latest/meta-data", "input_type": "url"},
        {"input": "https://user:pass@example.org/", "input_type": "url"},
    ],
)
def test_invalid_input_is_rejected_with_polish_error(client, payload):
    r = client.post("/api/check", json=payload)
    assert r.status_code == 422
    error = r.json()["error"]
    assert error["code"] == "invalid_input"
    assert error["message_pl"]


def test_forced_text_type_keeps_url_as_text(client):
    r = client.post("/api/check", json={"input": "https://example.org/", "input_type": "text"})
    assert r.status_code == 200
    assert r.json()["input_type"] == "text"


def test_oversized_body_is_rejected(client):
    r = client.post(
        "/api/check",
        content=b'{"input": "' + b"a" * 70_000 + b'"}',
        headers={"content-type": "application/json"},
    )
    assert r.status_code == 413
    assert r.json()["error"]["code"] == "payload_too_large"
