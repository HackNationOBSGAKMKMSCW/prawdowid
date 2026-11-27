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


def _client(reject):
    """Atrapa klienta: ``reject(kwargs)`` zwraca błąd 400 albo ``None`` (odpowiedź)."""
    sent: list[dict] = []

    async def create(**kwargs):
        sent.append(dict(kwargs))
        error = reject(kwargs)
        if error is not None:
            raise error
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="{}"))])

    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    return client, sent


def _effort_error(value):
    return _bad_request(
        f"Unsupported value: 'reasoning_effort' does not support '{value}' with this model.",
        "reasoning_effort",
    )


_TEMPERATURE_ERROR = _bad_request(
    "Unsupported value: 'temperature' does not support 0 with this model.", "temperature"
)


@pytest.fixture(autouse=True)
def _reset():
    llm_compat.reset()
    yield
    llm_compat.reset()


async def test_gpt_6_2_sol_steps_up_to_low_and_remembers_it_per_model():
    # gpt-6.2-sol: "none" (i "minimal") odrzucone, najniższy poziom to "low"; bez temperature.
    def reject(kwargs):
        if kwargs.get("reasoning_effort") in {"none", "minimal"}:
            return _effort_error(kwargs["reasoning_effort"])
        if "temperature" in kwargs:
            return _TEMPERATURE_ERROR
        return None

    client, sent = _client(reject)
    kwargs = {"model": "gpt-6.2-sol", "messages": [], "temperature": 0, "reasoning_effort": "none"}
    await llm_compat.create_chat_completion(client, **kwargs)
    assert [k.get("reasoning_effort") for k in sent] == ["none", "minimal", "low", "low"]
    assert sent[-1] == {"model": "gpt-6.2-sol", "messages": [], "reasoning_effort": "low"}

    sent.clear()
    await llm_compat.create_chat_completion(client, **kwargs)
    assert sent == [{"model": "gpt-6.2-sol", "messages": [], "reasoning_effort": "low"}]

    sent.clear()
    await llm_compat.create_chat_completion(client, **{**kwargs, "model": "inny"})
    assert len(sent) == 4  # inny model sprawdzany od nowa


async def test_explicit_higher_effort_is_kept():
    def reject(kwargs):
        return _effort_error("none") if kwargs.get("reasoning_effort") == "none" else None

    client, sent = _client(reject)
    await llm_compat.create_chat_completion(client, model="m", messages=[], reasoning_effort="none")
    await llm_compat.create_chat_completion(client, model="m", messages=[], reasoning_effort="high")
    assert [k["reasoning_effort"] for k in sent] == ["none", "minimal", "high"]


async def test_effort_is_dropped_when_no_level_is_accepted():
    # gpt-4o: żadna wartość reasoning_effort nie przechodzi.
    def reject(kwargs):
        return _effort_error(kwargs["reasoning_effort"]) if "reasoning_effort" in kwargs else None

    client, sent = _client(reject)
    await llm_compat.create_chat_completion(
        client, model="gpt-4o", messages=[], temperature=0, reasoning_effort="none"
    )
    assert [k.get("reasoning_effort") for k in sent] == ["none", "minimal", "low", None]
    assert sent[-1]["temperature"] == 0


async def test_message_without_param_field_is_recognised():
    error = _bad_request("Unrecognized request argument supplied: reasoning_effort")
    client, sent = _client(lambda kwargs: error if "reasoning_effort" in kwargs else None)
    await llm_compat.create_chat_completion(
        client, model="gpt-4o-mini", messages=[], temperature=0, reasoning_effort="high"
    )
    assert sent[-1] == {"model": "gpt-4o-mini", "messages": [], "temperature": 0}


async def test_other_bad_requests_are_raised():
    error = _bad_request("Invalid 'messages'.", "messages")
    client, sent = _client(lambda kwargs: error)
    with pytest.raises(openai.BadRequestError):
        await llm_compat.create_chat_completion(
            client, model="m", messages=[], reasoning_effort="none"
        )
    assert len(sent) == 1


async def test_none_values_are_not_sent():
    client, sent = _client(lambda kwargs: None)
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
