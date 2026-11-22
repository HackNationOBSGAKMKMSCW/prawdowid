"""EUvsDisinfo check: MCP client, case parsing, matching rules (no network)."""

import json
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
import respx

import knownDisinfo
from knownDisinfo import DisinfoCase, DisinfoSettings, EUvsDisinfoMcp, McpDisinfoStore, McpError
from knownDisinfo.matching import check, parse_json

URL = "https://mcp.test/mcp"
KEY = "secret-key-123"
SETTINGS = DisinfoSettings(api_key=KEY, mcp_url=URL, timeout=5)
SSE = (Path(__file__).parent / "fixtures" / "search_sse.txt").read_text(encoding="utf-8")


def sse(payload: dict) -> httpx.Response:
    body = f"event: message\ndata: {json.dumps(payload)}\n\n"
    return httpx.Response(200, text=body, headers={"content-type": "text/event-stream"})


# --- MCP client ---------------------------------------------------------------------------------


@respx.mock
async def test_search_parses_real_sse_response_and_keeps_only_claim_reviews():
    route = respx.post(URL).mock(
        return_value=httpx.Response(200, text=SSE, headers={"content-type": "text/event-stream"})
    )
    async with EUvsDisinfoMcp(SETTINGS) as mcp:
        cases = await McpDisinfoStore(mcp).search("NATO attack Russia", 5)

    assert [c.title for c in cases] == [
        "Russia is at war with NATO and the Pentagon; only the soldiers are Ukrainians",
        "NATO prepares to attack Russia",
        "NATO is practicing an invasion of the CSTO countries",
    ]
    nato = cases[1]
    assert (
        nato.case_id == nato.url == "https://euvsdisinfo.eu/report/nato-prepares-to-attack-russia"
    )
    assert nato.summary.startswith("The Alliance prepares to attack Russia.")
    assert "SUMMARY" not in nato.summary and "<" not in nato.summary
    assert nato.disproof == ""

    request = route.calls.last.request
    assert request.headers["X-API-Key"] == KEY
    assert KEY not in str(request.url)
    assert request.headers["Accept"] == "application/json, text/event-stream"
    assert request.headers["mcp-session-id"]
    body = json.loads(request.content)
    assert body["method"] == "tools/call"
    assert body["params"] == {"name": "search", "arguments": {"query": "NATO attack Russia"}}


@respx.mock
async def test_plain_json_text_result_is_parsed():
    result = {"content": [{"type": "text", "text": json.dumps({"results": []})}]}
    respx.post(URL).mock(
        return_value=httpx.Response(200, json={"jsonrpc": "2.0", "id": 1, "result": result})
    )
    async with EUvsDisinfoMcp(SETTINGS) as mcp:
        assert await mcp.call_tool("search", {"query": "abc"}) == {"results": []}


@respx.mock
async def test_unauthorized_error_never_contains_the_key():
    respx.post(URL).mock(
        return_value=httpx.Response(
            401, json={"jsonrpc": "2.0", "error": {"code": -32001, "message": "Invalid API key"}}
        )
    )
    async with EUvsDisinfoMcp(SETTINGS) as mcp:
        with pytest.raises(McpError) as caught:
            await mcp.call_tool("search", {"query": "abc"})
    assert caught.value.code == 401
    assert "Invalid API key" in str(caught.value) and KEY not in str(caught.value)


@respx.mock
async def test_jsonrpc_and_tool_errors_raise():
    respx.post(URL).mock(
        side_effect=[
            sse({"jsonrpc": "2.0", "id": 1, "error": {"code": -32602, "message": "bad date"}}),
            sse(
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "result": {"isError": True, "content": [{"type": "text", "text": "x"}]},
                }
            ),
            sse({"jsonrpc": "2.0", "id": 1, "result": {"structuredContent": {"oops": 1}}}),
        ]
    )
    async with EUvsDisinfoMcp(SETTINGS) as mcp:
        with pytest.raises(McpError, match="bad date"):
            await mcp.call_tool("search", {"query": "abc"})
        with pytest.raises(McpError, match="tool_error"):
            await mcp.call_tool("search", {"query": "abc"})
        with pytest.raises(McpError, match="results"):
            await McpDisinfoStore(mcp).search("abc", 5)


async def test_short_query_is_not_sent():
    class NoCalls:
        async def call_tool(self, *args):
            raise AssertionError("must not be called")

    assert await McpDisinfoStore(NoCalls()).search(" ab ", 5) == []  # type: ignore[arg-type]


def test_settings_hide_the_key_and_disable_without_it(monkeypatch):
    assert KEY not in repr(SETTINGS) and KEY not in repr(EUvsDisinfoMcp(SETTINGS))
    for name in ("EUvsDisinfo_API_KEY", "EUVSDISINFO_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    assert DisinfoSettings.from_environment().configured is False
    monkeypatch.setenv("EUvsDisinfo_API_KEY", f' "{KEY}" ')
    settings = DisinfoSettings.from_environment()
    assert settings.configured and settings.api_key == KEY


async def test_run_without_key_is_disabled_not_an_error():
    result = await knownDisinfo.run(
        SimpleNamespace(statements=["x"]), settings=DisinfoSettings(api_key=None)
    )
    assert result.status == "disabled" and result.matches == []


# --- matching -------------------------------------------------------------------------------


def case(slug: str, title: str) -> DisinfoCase:
    return DisinfoCase(
        case_id=f"https://euvsdisinfo.eu/report/{slug}",
        title=title,
        url=f"https://euvsdisinfo.eu/report/{slug}",
        summary=title,
    )


NATO = case("nato-prepares-to-attack-russia", "NATO prepares to attack Russia")
BIOLAB = case("us-biolabs-in-ukraine", "US biolabs in Ukraine")


class FakeStore:
    def __init__(self, by_query=None, error=None):
        self.by_query, self.error, self.queries = by_query or {}, error, []

    async def search(self, query, limit):
        self.queries.append(query)
        if self.error:
            raise self.error
        return self.by_query.get(query, [])[:limit]


class FakeLLM:
    def __init__(self, queries, judge=None):
        self.queries_reply, self.judge_reply, self.judged = queries, judge, []

    async def complete_json(self, system, user):
        if "Przygotowujesz zapytania" in system:
            if isinstance(self.queries_reply, Exception):
                raise self.queries_reply
            return self.queries_reply
        self.judged.append(json.loads(user))
        if isinstance(self.judge_reply, Exception):
            raise self.judge_reply
        return self.judge_reply


STATEMENTS = ["NATO szykuje atak na Rosję.", "Ziemia jest płaska."]


async def test_match_confirmed_by_judge():
    store = FakeStore({"NATO attack Russia": [NATO, BIOLAB], "NATO Russia war": [NATO]})
    llm = FakeLLM(
        {"queries": [["NATO attack Russia", "NATO Russia war"], ["flat earth"]]},
        {"match": "C1", "reason": "Ta sama teza."},
    )
    result = await check(STATEMENTS, store, llm, SETTINGS)

    assert result.status == "ok"
    first, second = result.statements
    assert first.match == NATO and first.reason == "Ta sama teza." and first.index == 1
    assert [c.case_id for c in first.candidates] == [NATO.case_id, BIOLAB.case_id]  # de-duplicated
    assert second.candidates == [] and second.match is None
    assert len(llm.judged) == 1  # no candidates -> no judge call
    assert llm.judged[0]["twierdzenie"] == STATEMENTS[0]
    assert [m.index for m in result.matches] == [1]


@pytest.mark.parametrize(
    ("reply", "warned"),
    [
        ({"match": None, "reason": "Inny temat."}, False),
        ({"match": "C9", "reason": "?"}, True),
        ("nie-json", True),
        (TimeoutError("slow"), True),
    ],
)
async def test_anything_doubtful_is_no_match(reply, warned):
    llm = FakeLLM({"queries": [["NATO attack Russia"]]}, reply)
    result = await check(STATEMENTS[:1], FakeStore({"NATO attack Russia": [NATO]}), llm, SETTINGS)
    assert result.status == "ok" and result.matches == []
    assert bool(result.warnings) is warned


async def test_query_model_failure_falls_back_to_statement_text():
    store = FakeStore()
    result = await check(STATEMENTS[:1], store, FakeLLM(RuntimeError("down")), SETTINGS)
    assert store.queries == [STATEMENTS[0]]
    assert result.status == "ok" and "Zapytania z treści" in result.warnings[0]


async def test_database_down_is_an_error():
    llm = FakeLLM({"queries": [["NATO attack Russia"], ["flat earth"]]})
    result = await check(STATEMENTS, FakeStore(error=McpError(500, "Elasticsearch")), llm, SETTINGS)
    assert result.status == "error" and result.matches == []
    assert "2/2" in result.warnings[0]


def test_parse_json_strips_thinking_and_fences():
    raw = '<think>hmm {"no": 1}</think>\n```json\n{"match": null, "reason": "x"}\n```'
    assert parse_json(raw) == {"match": None, "reason": "x"}
    assert parse_json('Odpowiedź: {"queries": [["a b c"]]} koniec') == {"queries": [["a b c"]]}


async def test_llm_drops_reasoning_effort_when_the_endpoint_rejects_it():
    from openai import BadRequestError

    from knownDisinfo.matching import OpenAIJsonLLM

    sent = []
    message = SimpleNamespace(content='<think>x</think>{"match": null}')

    async def create(**kwargs):
        sent.append(kwargs)
        if "reasoning_effort" in kwargs:
            raise BadRequestError.__new__(BadRequestError)  # endpoint rejects the parameter
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])

    llm = OpenAIJsonLLM(
        api_key="k", base_url="https://llm.test/v1", model="m", timeout=5, reasoning_effort="none"
    )
    llm._client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    assert await llm.complete_json("s", "u") == {"match": None}
    assert await llm.complete_json("s", "u") == {"match": None}
    assert [k.get("reasoning_effort") for k in sent] == ["none", None, None]
    assert sent[1]["temperature"] == 0
