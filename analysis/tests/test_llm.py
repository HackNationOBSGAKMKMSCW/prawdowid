"""Klient FreeLLMAPI bez sieci: SDK OpenAI na httpx.MockTransport udającym serwer."""

import json

import httpx
import pytest

from prawdowid_analysis.verdict.llm import (
    ROUTER_MODEL,
    FreeLLMClient,
    LLMError,
    LLMSettings,
    is_router_model,
)

SETTINGS = LLMSettings(
    base_url="http://llm.test/v1",
    api_key="freellmapi-test",
    retry_backoff_s=0.0,
    rate_limit_wait_s=0.0,
)


def _completion(content='{"stance": "neutral"}', model="auto") -> dict:
    return {
        "id": "chatcmpl-1",
        "object": "chat.completion",
        "created": 0,
        "model": model,
        "choices": [
            {
                "index": 0,
                "finish_reason": "stop",
                "message": {"role": "assistant", "content": content},
            }
        ],
        "usage": {"prompt_tokens": 12, "completion_tokens": 5, "total_tokens": 17},
    }


def _client(handler) -> FreeLLMClient:
    return FreeLLMClient(SETTINGS, http_client=httpx.Client(transport=httpx.MockTransport(handler)))


def _chat(handler, **kwargs):
    return _client(handler).chat([{"role": "user", "content": "x"}], **kwargs)


def test_default_model_is_router_auto():
    assert SETTINGS.model == ROUTER_MODEL == "auto"


def test_chat_follows_readme_pattern_and_reads_routed_via():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["auth"] = request.headers.get("authorization")
        seen["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json=_completion(),
            headers={"x-routed-via": "groq/llama-3.3-70b", "x-fallback-attempts": "2"},
        )

    result = _chat(handler, json_mode=True)
    assert seen["url"] == "http://llm.test/v1/chat/completions"
    assert seen["auth"] == "Bearer freellmapi-test"
    assert seen["body"]["model"] == "auto"
    assert seen["body"]["response_format"] == {"type": "json_object"}
    assert result.text == '{"stance": "neutral"}'
    assert result.routed_via == result.model == "groq/llama-3.3-70b"  # nie "auto"
    assert result.requested_model == "auto" and result.fallback_attempts == 2
    assert result.as_run_model() == {"name": "groq/llama-3.3-70b", "tokens_in": 12, "tokens_out": 5}


def test_percent_encoded_routed_via_is_decoded():
    headers = {"x-routed-via": "custom/mod%C3%A9l"}
    result = _chat(lambda r: httpx.Response(200, json=_completion(), headers=headers))
    assert result.model == "custom/modél"


def test_without_routed_via_uses_model_from_body():
    result = _chat(lambda r: httpx.Response(200, json=_completion(model="qwen2.5:7b")))
    assert result.model == "qwen2.5:7b" and result.routed_via is None


def test_json_mode_rejected_by_provider_is_retried_without_response_format():
    bodies = []

    def handler(request):
        body = json.loads(request.content)
        bodies.append(body)
        if "response_format" in body:
            return httpx.Response(400, json={"error": {"message": "unsupported response_format"}})
        return httpx.Response(200, json=_completion())

    assert _chat(handler, json_mode=True).text == '{"stance": "neutral"}'
    assert len(bodies) == 2 and "response_format" not in bodies[1]


def test_bad_request_without_json_mode_is_not_retried():
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(400, json={"error": {"message": "x"}})

    with pytest.raises(LLMError) as exc:
        _chat(handler)
    assert exc.value.kind == "bad_request" and len(calls) == 1


def test_quota_exceeded_is_not_retried_and_keeps_retry_after():
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(
            429,
            json={"error": {"code": "quota_exceeded", "message": "budget"}},
            headers={"retry-after": "3600"},
        )

    with pytest.raises(LLMError) as exc:
        _chat(handler)
    assert exc.value.kind == "quota_exceeded" and len(calls) == 1
    assert exc.value.status_code == 429 and exc.value.retry_after_s == 3600.0


def test_transient_503_is_retried_then_succeeds():
    calls = []

    def handler(request):
        calls.append(1)
        if len(calls) == 1:
            return httpx.Response(503, json={})
        return httpx.Response(200, json=_completion())

    assert _chat(handler).text == '{"stance": "neutral"}'
    assert len(calls) == 2


def test_persistent_503_gives_up_after_retries():
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(503, json={})

    with pytest.raises(LLMError) as exc:
        _chat(handler)
    assert exc.value.kind == "provider_error" and len(calls) == SETTINGS.retries + 1


def test_short_rate_limit_is_retried_once_then_succeeds():
    calls = []

    def handler(request):
        calls.append(1)
        if len(calls) == 1:
            return httpx.Response(429, json={"error": {"message": "slow"}})
        return httpx.Response(200, json=_completion())

    assert _chat(handler).text == '{"stance": "neutral"}'
    assert len(calls) == 2


def test_persistent_rate_limit_gives_up_after_one_retry():
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(429, json={"error": {"message": "slow"}})

    with pytest.raises(LLMError) as exc:
        _chat(handler)
    assert exc.value.kind == "rate_limited" and len(calls) == SETTINGS.rate_limit_retries + 1


def test_long_retry_after_is_not_waited_for():
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(
            429, json={"error": {"message": "slow"}}, headers={"retry-after": "60"}
        )

    with pytest.raises(LLMError) as exc:
        _chat(handler)
    assert exc.value.kind == "rate_limited" and len(calls) == 1


def test_list_models_strips_gemini_prefix():
    def handler(request):
        return httpx.Response(200, json={"object": "list", "data": [{"id": "models/g-flash"}]})

    assert _client(handler).list_models() == ["g-flash"]


@pytest.mark.parametrize(
    "response, kind",
    [
        (httpx.Response(429, json={"error": {"message": "slow"}}), "rate_limited"),
        (httpx.Response(503, json={}), "provider_error"),
        (httpx.Response(504, json={}), "timeout"),
        (httpx.Response(200, json={**_completion(), "choices": []}), "bad_response"),
    ],
)
def test_provider_failures_are_llm_errors(response, kind):
    with pytest.raises(LLMError) as exc:
        _chat(lambda r: response)
    assert exc.value.kind == kind


@pytest.mark.parametrize(
    "error, kind",
    [(httpx.ConnectError("odmowa"), "connection"), (httpx.ReadTimeout("wolno"), "timeout")],
)
def test_network_failures_are_llm_errors(error, kind):
    def handler(request):
        raise error

    with pytest.raises(LLMError) as exc:
        _chat(handler)
    assert exc.value.kind == kind


def test_list_models():
    def handler(request):
        assert request.url.path == "/v1/models"
        return httpx.Response(
            200, json={"object": "list", "data": [{"id": "b", "object": "model"}, {"id": "a"}]}
        )

    assert _client(handler).list_models() == ["a", "b"]


def test_router_models():
    assert all(is_router_model(m) for m in ("auto", "AUTO:fast", "auto:smart", "fusion"))
    assert not any(is_router_model(m) for m in ("gemini-2.5-flash", "automata-7b"))


def _isolated_env(monkeypatch, **values):
    monkeypatch.setattr("prawdowid_analysis.verdict.llm._ENV_PATH", "nie-istnieje.env")
    for name in ("OPENAI_BASE_URL", "OPENAI_API_KEY", "LLM_MODEL", "LLM_TIMEOUT_S"):
        monkeypatch.delenv(name, raising=False)
    for name, value in values.items():
        monkeypatch.setenv(name, value)


def test_missing_config_is_llm_error(monkeypatch):
    _isolated_env(monkeypatch, OPENAI_BASE_URL="http://llm.test/v1")
    with pytest.raises(LLMError, match="OPENAI_API_KEY") as exc:
        LLMSettings.from_env()
    assert exc.value.kind == "config"


def test_empty_llm_model_means_router_and_quotes_are_stripped(monkeypatch):
    _isolated_env(
        monkeypatch, OPENAI_BASE_URL='"http://llm.test/v1/"', OPENAI_API_KEY='"freellmapi-x"'
    )
    s = LLMSettings.from_env()
    assert (s.base_url, s.api_key, s.model) == ("http://llm.test/v1", "freellmapi-x", "auto")
