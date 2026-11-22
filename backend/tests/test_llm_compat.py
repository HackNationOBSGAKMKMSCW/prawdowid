"""llm_compat: parametry odrzucane przez model są usuwane i zapamiętywane."""

from types import SimpleNamespace

import httpx
import llm_compat
import openai
import pytest


def _bad_request(message: str, param: str | None = None) -> openai.BadRequestError:
    request = httpx.Request("POST", "https://api.openai.com/v1/chat/completions")
    body = {"error": {"message": message, "type": "invalid_request_error", "param": param}}
    return openai.BadRequestError(
        message, response=httpx.Response(400, request=request), body=body["error"]
    )


def _client(reject: dict[str, openai.BadRequestError]):
    sent: list[dict] = []

    async def create(**kwargs):
        sent.append(dict(kwargs))
        for name, error in reject.items():
            if name in kwargs:
                raise error
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="{}"))])

    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    return client, sent


@pytest.fixture(autouse=True)
def _reset():
    llm_compat.reset()
    yield
    llm_compat.reset()


async def test_drops_unsupported_params_and_remembers_them_per_model():
    # gpt-5-mini: "none" i temperature != 1 są odrzucane.
    client, sent = _client(
        {
            "reasoning_effort": _bad_request(
                "Unsupported value: 'reasoning_effort' does not support 'none'.",
                "reasoning_effort",
            ),
            "temperature": _bad_request(
                "Unsupported value: 'temperature' does not support 0 with this model.",
                "temperature",
            ),
        }
    )
    kwargs = {"model": "gpt-5-mini", "messages": [], "temperature": 0, "reasoning_effort": "none"}
    await llm_compat.create_chat_completion(client, **kwargs)
    assert len(sent) == 3
    assert "reasoning_effort" not in sent[-1] and "temperature" not in sent[-1]

    sent.clear()
    await llm_compat.create_chat_completion(client, **kwargs)
    assert len(sent) == 1  # zapamiętane: od razu bez odrzuconych parametrów

    sent.clear()
    await llm_compat.create_chat_completion(client, **{**kwargs, "model": "inny"})
    assert len(sent) == 3  # inny model sprawdzany od nowa


async def test_message_without_param_field_is_recognised():
    client, sent = _client(
        {
            "reasoning_effort": _bad_request(
                "Unrecognized request argument supplied: reasoning_effort"
            )
        }
    )
    await llm_compat.create_chat_completion(
        client, model="gpt-4o-mini", messages=[], temperature=0, reasoning_effort="none"
    )
    assert sent[-1] == {"model": "gpt-4o-mini", "messages": [], "temperature": 0}


async def test_other_bad_requests_are_raised():
    client, sent = _client({"messages": _bad_request("Invalid 'messages'.", "messages")})
    with pytest.raises(openai.BadRequestError):
        await llm_compat.create_chat_completion(
            client, model="m", messages=[], reasoning_effort="none"
        )
    assert len(sent) == 1


async def test_none_values_are_not_sent():
    client, sent = _client({})
    await llm_compat.create_chat_completion(client, model="m", messages=[], reasoning_effort=None)
    assert "reasoning_effort" not in sent[0]


@pytest.mark.parametrize(
    ("value", "expected"), [(None, "none"), ("low", "low"), ("off", None), ("", None)]
)
def test_reasoning_effort_from_environment(monkeypatch, value, expected):
    if value is None:
        monkeypatch.delenv("LLM_REASONING_EFFORT", raising=False)
    else:
        monkeypatch.setenv("LLM_REASONING_EFFORT", value)
    assert llm_compat.reasoning_effort() == expected
