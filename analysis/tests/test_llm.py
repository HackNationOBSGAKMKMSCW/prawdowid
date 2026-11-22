import asyncio
from types import SimpleNamespace

import httpx
import pytest
from openai import APIConnectionError, RateLimitError

from prawdowid_analysis.config import Settings
from prawdowid_analysis.llm import RATE_LIMIT_RETRIES, LLMError, OpenAIChatClient

SETTINGS = Settings(
    api_key="x",
    base_url=None,
    model="m",
    timeout=1,
    max_retries=0,
    json_mode=False,
    concurrency=1,
)
REQUEST = httpx.Request("POST", "http://test/v1/chat/completions")


def rate_limit(retry_after: str | None = None) -> RateLimitError:
    headers = {"retry-after": retry_after} if retry_after else {}
    response = httpx.Response(429, headers=headers, request=REQUEST)
    return RateLimitError("limit", response=response, body=None)


def ok_response(text: str = "{}"):
    return SimpleNamespace(
        model="m", choices=[SimpleNamespace(message=SimpleNamespace(content=text))]
    )


class ScriptedCompletions:
    def __init__(self, *outcomes):
        self.outcomes = list(outcomes)
        self.calls = 0

    async def create(self, **kwargs):
        self.calls += 1
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def make_client(*outcomes):
    completions = ScriptedCompletions(*outcomes)
    fake = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    client = OpenAIChatClient(SETTINGS, client=fake)
    delays: list[float] = []

    async def fake_sleep(delay):
        delays.append(delay)

    client._sleep = fake_sleep
    return client, completions, delays


def test_rate_limit_is_retried_with_backoff_and_retry_after():
    client, completions, delays = make_client(rate_limit(), rate_limit("2"), ok_response("ok"))
    reply = asyncio.run(client.complete([{"role": "user", "content": "x"}]))
    assert reply.content == "ok"
    assert completions.calls == 3
    assert delays == [5.0, 2.0]


def test_rate_limit_gives_up_after_limit():
    outcomes = [rate_limit() for _ in range(RATE_LIMIT_RETRIES + 1)]
    client, completions, _ = make_client(*outcomes)
    with pytest.raises(LLMError, match="RateLimitError"):
        asyncio.run(client.complete([{"role": "user", "content": "x"}]))
    assert completions.calls == RATE_LIMIT_RETRIES + 1


def test_other_api_errors_are_not_retried():
    client, completions, _ = make_client(APIConnectionError(request=REQUEST))
    with pytest.raises(LLMError, match="APIConnectionError"):
        asyncio.run(client.complete([{"role": "user", "content": "x"}]))
    assert completions.calls == 1
