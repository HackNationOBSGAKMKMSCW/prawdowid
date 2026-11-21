"""Klient LLM bez sieci: httpx.MockTransport udaje FreeLLMAPI (i zwykłe API OpenAI)."""

import json

import httpx
import pytest

from prawdowid_analysis.verdict.llm import (
    LLMError,
    LLMSettings,
    OpenAIChatClient,
    is_router_model,
)

SETTINGS = LLMSettings(base_url="http://llm.test/v1", model="auto", api_key="freellmapi-test")
OK_BODY = {
    "model": "auto",
    "choices": [{"message": {"content": '{"stance": "neutral"}'}}],
    "usage": {"prompt_tokens": 12, "completion_tokens": 5},
}


def _client(handler) -> OpenAIChatClient:
    http = httpx.Client(base_url=SETTINGS.base_url, transport=httpx.MockTransport(handler))
    return OpenAIChatClient(SETTINGS, http=http)


def _chat(handler, **kwargs):
    return _client(handler).chat([{"role": "user", "content": "x"}], **kwargs)


def test_chat_sends_request_and_reads_routing_headers():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json=OK_BODY,
            headers={"X-Routed-Via": "groq/llama-3.3-70b", "X-Fallback-Attempts": "2"},
        )

    result = _chat(handler, json_mode=True)
    assert seen["path"] == "/v1/chat/completions"
    assert seen["body"]["model"] == "auto"
    assert seen["body"]["response_format"] == {"type": "json_object"}
    assert result.text == '{"stance": "neutral"}'
    assert result.model == "groq/llama-3.3-70b"  # model faktyczny, nie "auto"
    assert result.requested_model == "auto"
    assert result.fallback_attempts == 2
    assert result.as_run_model() == {"name": "groq/llama-3.3-70b", "tokens_in": 12, "tokens_out": 5}


def test_percent_encoded_routed_via_is_decoded():
    headers = {"X-Routed-Via": "custom/mod%C3%A9l"}
    assert _chat(lambda r: httpx.Response(200, json=OK_BODY, headers=headers)).model == (
        "custom/modél"
    )


def test_without_freellmapi_headers_falls_back_to_body_model():
    body = {**OK_BODY, "model": "qwen2.5:7b"}
    result = _chat(lambda r: httpx.Response(200, json=body))
    assert result.model == "qwen2.5:7b" and result.fallback_attempts == 0


def test_json_mode_rejected_by_provider_is_retried_without_response_format():
    bodies = []

    def handler(request):
        body = json.loads(request.content)
        bodies.append(body)
        if "response_format" in body:
            return httpx.Response(400, json={"error": {"message": "unsupported response_format"}})
        return httpx.Response(200, json=OK_BODY)

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


def test_quota_exceeded_has_kind_and_retry_after():
    resp = httpx.Response(
        429,
        json={"error": {"code": "quota_exceeded", "message": "budget"}},
        headers={"Retry-After": "3600"},
    )
    with pytest.raises(LLMError) as exc:
        _chat(lambda r: resp)
    assert exc.value.kind == "quota_exceeded"
    assert exc.value.status_code == 429 and exc.value.retry_after_s == 3600.0


@pytest.mark.parametrize(
    "response, kind",
    [
        (httpx.Response(429, text="slow down"), "rate_limited"),
        (httpx.Response(503, json={}), "provider_error"),
        (httpx.Response(504, json={}), "timeout"),
        (httpx.Response(200, json={"choices": []}), "bad_response"),
        (httpx.Response(200, text="<html>"), "bad_response"),
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


def test_list_models_asks_for_available_only():
    seen = {}

    def handler(request):
        seen["query"] = dict(request.url.params)
        return httpx.Response(200, json={"data": [{"id": "b"}, {"id": "a"}]})

    assert _client(handler).list_models() == ["a", "b"]
    assert seen["query"] == {"available": "true"}


def test_router_models():
    assert all(is_router_model(m) for m in ("auto", "AUTO:fast", "auto:smart", "fusion"))
    assert not any(is_router_model(m) for m in ("gemini-2.5-flash", "automata-7b"))


def test_missing_config_is_llm_error(monkeypatch):
    monkeypatch.setattr("prawdowid_analysis.verdict.llm._ENV_PATH", "nie-istnieje.env")
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    monkeypatch.delenv("LLM_MODEL", raising=False)
    with pytest.raises(LLMError, match="LLM_MODEL") as exc:
        LLMSettings.from_env()
    assert exc.value.kind == "config"
