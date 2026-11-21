"""Klient LLM bez sieci: httpx.MockTransport zamiast serwera."""

import json

import httpx
import pytest

from prawdowid_analysis.verdict.llm import LLMError, LLMSettings, OpenAIChatClient

SETTINGS = LLMSettings(base_url="http://llm.test/v1", model="model-testowy", api_key="k")


def _client(handler) -> OpenAIChatClient:
    http = httpx.Client(base_url=SETTINGS.base_url, transport=httpx.MockTransport(handler))
    return OpenAIChatClient(SETTINGS, http=http)


def test_chat_returns_text_tokens_and_sends_json_mode():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "model": "model-testowy",
                "choices": [{"message": {"content": '{"stance": "neutral"}'}}],
                "usage": {"prompt_tokens": 12, "completion_tokens": 5},
            },
        )

    result = _client(handler).chat([{"role": "user", "content": "x"}], json_mode=True)
    assert seen["path"] == "/v1/chat/completions"
    assert seen["body"]["model"] == "model-testowy"
    assert seen["body"]["response_format"] == {"type": "json_object"}
    assert result.text == '{"stance": "neutral"}'
    assert (result.tokens_in, result.tokens_out) == (12, 5)
    assert result.as_run_model() == {"name": "model-testowy", "tokens_in": 12, "tokens_out": 5}


@pytest.mark.parametrize(
    "response",
    [httpx.Response(500, json={}), httpx.Response(200, json={"choices": []})],
)
def test_provider_failure_is_llm_error(response):
    with pytest.raises(LLMError):
        _client(lambda request: response).chat([{"role": "user", "content": "x"}])


def test_network_failure_is_llm_error():
    def handler(request):
        raise httpx.ConnectError("odmowa połączenia")

    with pytest.raises(LLMError):
        _client(handler).chat([{"role": "user", "content": "x"}])


def test_missing_config_is_llm_error(monkeypatch):
    monkeypatch.setattr("prawdowid_analysis.verdict.llm._ENV_PATH", "nie-istnieje.env")
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    monkeypatch.delenv("LLM_MODEL", raising=False)
    with pytest.raises(LLMError, match="LLM_MODEL"):
        LLMSettings.from_env()
