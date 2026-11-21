from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from openai import APIConnectionError

import llm
from main import app

SETTINGS = llm.LLMSettings(
    base_url="http://llm.invalid/v1", api_key="x", model="test-model", timeout_s=5
)


class FakeCompletions:
    def __init__(self, response=None, error=None):
        self.response, self.error, self.calls = response, error, []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return self.response


def fake_client(completions):
    return SimpleNamespace(chat=SimpleNamespace(completions=completions))


def test_chat_returns_text_usage_and_json_mode():
    response = SimpleNamespace(
        model="test-model",
        choices=[SimpleNamespace(message=SimpleNamespace(content='{"ok": true}'))],
        usage=SimpleNamespace(prompt_tokens=12, completion_tokens=3),
    )
    completions = FakeCompletions(response=response)
    result = llm.chat(
        [{"role": "user", "content": "hej"}],
        json_mode=True,
        client=fake_client(completions),
        settings=SETTINGS,
    )
    assert result.text == '{"ok": true}'
    assert result.as_run_model() == {"name": "test-model", "tokens_in": 12, "tokens_out": 3}
    assert completions.calls[0]["response_format"] == {"type": "json_object"}
    assert completions.calls[0]["model"] == "test-model"


def test_provider_failure_becomes_llm_error():
    error = APIConnectionError(request=SimpleNamespace(method="POST", url="x"))
    with pytest.raises(llm.LLMError):
        llm.chat([], client=fake_client(FakeCompletions(error=error)), settings=SETTINGS)


def test_missing_config_is_reported(monkeypatch):
    monkeypatch.delenv("LLM_MODEL", raising=False)
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    with pytest.raises(llm.LLMError, match="LLM_MODEL"):
        llm.LLMSettings.from_env()
    body = TestClient(app).get("/api/llm/health").json()
    assert body["status"] == "not_configured"


def test_health_reports_unreachable_server(monkeypatch):
    # Port 9 (discard) na localhoście: połączenie odrzucone od razu.
    monkeypatch.setenv("OPENAI_BASE_URL", "http://127.0.0.1:9/v1")
    monkeypatch.setenv("LLM_MODEL", "test-model")
    monkeypatch.setenv("LLM_TIMEOUT_S", "2")
    assert llm.health()["status"] == "unreachable"
