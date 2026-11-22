import json
from pathlib import Path

import pytest
import respx
from apiReading.clients.eurlex import EurLexClient, _sparql_literal
from apiReading.exceptions import ApiResponseError, InvalidFiltersError

EURLEX_URL = "https://publications.europa.eu/webapi/rdf/sparql"
FIXTURE_PATH = Path(__file__).parent / "fixtures" / "eurlex_sparql.json"


def _fixture_payload() -> dict:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


@pytest.mark.asyncio
async def test_search_uses_fixture_and_normalizes_legal_act() -> None:
    with respx.mock(assert_all_called=True) as router:
        route = router.get(EURLEX_URL).respond(200, json=_fixture_payload())
        result = await EurLexClient().fetch_data(
            {
                "query": "corrigendum to commission implementing regulation",
                "language_code": "en",
                "page_size": 5,
            }
        )

    request = route.calls[0].request
    params = request.url.params
    assert request.method == "GET"
    assert params["format"] == "application/sparql-results+json"
    assert "cdm:resource_legal_id_celex" in params["query"]
    assert "cdm:work_title" in params["query"]
    assert "cdm:work_date_document" in params["query"]
    assert "cdm:work_has_resource-type" in params["query"]
    assert 'FILTER(LANG(?title) = "en")' in params["query"]
    assert "LIMIT 5" in params["query"]
    assert "OFFSET 0" in params["query"]
    assert result.source == "eurlex"
    assert result.next_cursor is None
    assert result.items[0].id == "eurlex_32020R0270R(05)"
    assert result.items[0].payload == {
        "celex": "32020R0270R(05)",
        "title": "Corrigendum to Commission Implementing Regulation (EU) 2020/270 of 25 February 2020 amending Regulation (EU) No 1321/2014 as regards transitional measures for organisations involved in the continuing airworthiness for general aviation and continuing airworthiness management and correcting that Regulation (OJ L 56, 27.2.2020)",
        "doc_type": "http://publications.europa.eu/resource/authority/resource-type/REG_IMPL",
        "date": "2026-03-23",
        "in_force": None,
        "url_eurlex": "https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32020R0270R%2805%29",
    }


@pytest.mark.asyncio
async def test_search_escapes_user_text_as_a_sparql_literal() -> None:
    injected_text = 'law "); } UNION { ?s ?p ?o } # \\\nnext'
    with respx.mock(assert_all_called=True) as router:
        route = router.get(EURLEX_URL).respond(
            200,
            json={
                "head": {"vars": ["celex", "title", "docType", "date"]},
                "results": {"bindings": []},
            },
        )
        await EurLexClient().fetch_data({"query": injected_text})

    sparql_query = route.calls[0].request.url.params["query"]
    escaped_literal = _sparql_literal(injected_text)
    assert escaped_literal in sparql_query
    assert r'"' in escaped_literal
    assert r"\\\n" in escaped_literal
    assert injected_text not in sparql_query


@pytest.mark.asyncio
async def test_empty_result_is_valid() -> None:
    with respx.mock(assert_all_called=True) as router:
        router.get(EURLEX_URL).respond(
            200,
            json={
                "head": {"vars": ["celex", "title", "docType", "date"]},
                "results": {"bindings": []},
            },
        )
        result = await EurLexClient().fetch_data({"query": "no matching act"})

    assert result.items == []
    assert result.next_cursor is None


@pytest.mark.asyncio
async def test_page_token_maps_to_offset_and_returns_next_cursor() -> None:
    payload = _fixture_payload()
    payload["results"]["bindings"] *= 2
    with respx.mock(assert_all_called=True) as router:
        route = router.get(EURLEX_URL).respond(200, json=payload)
        result = await EurLexClient().fetch_data(
            {"query": "regulation", "page_size": 2, "page_token": "20"}
        )

    query = route.calls[0].request.url.params["query"]
    assert "LIMIT 2" in query
    assert "OFFSET 20" in query
    assert result.next_cursor == "22"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "filters",
    [
        {},
        {"query": " "},
        {"query": "x" * 501},
        {"query": "x", "page_size": True},
        {"query": "x", "page_size": 0},
        {"query": "x", "page_size": 101},
        {"query": "x", "page_token": True},
        {"query": "x", "page_token": "-1"},
        {"query": "x", "language_code": "bad tag"},
        {"query": "x", "api_key": "secret"},
    ],
)
async def test_bad_filters_are_rejected_before_http(filters: dict) -> None:
    with respx.mock(assert_all_called=False) as router:
        router.get(EURLEX_URL)
        with pytest.raises(InvalidFiltersError):
            await EurLexClient().fetch_data(filters)

    assert router.calls.call_count == 0


@pytest.mark.asyncio
async def test_client_does_not_put_credentials_in_url() -> None:
    with respx.mock(assert_all_called=True) as router:
        route = router.get(EURLEX_URL).respond(
            200,
            json={
                "head": {"vars": ["celex", "title", "docType", "date"]},
                "results": {"bindings": []},
            },
        )
        await EurLexClient(api_key="must-not-appear").fetch_data({"query": "law"})

    request_url = str(route.calls[0].request.url)
    assert "must-not-appear" not in request_url
    assert "key=" not in request_url
    assert EurLexClient.requires_api_key is False


@pytest.mark.asyncio
async def test_malformed_json_raises_api_response_error() -> None:
    with respx.mock(assert_all_called=True) as router:
        router.get(EURLEX_URL).respond(200, text="not json")
        with pytest.raises(ApiResponseError):
            await EurLexClient().fetch_data({"query": "law"})


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload",
    [
        [],
        {"head": {}, "results": {"bindings": []}},
        {
            "head": {"vars": ["celex", "title", "docType", "date"]},
            "results": {"bindings": ["not a row"]},
        },
        {
            "head": {"vars": ["celex", "title", "docType", "date"]},
            "results": {"bindings": [{"celex": {"type": "literal", "value": "123"}}]},
        },
        {
            "head": {"vars": ["celex", "title", "docType", "date"]},
            "results": {
                "bindings": [
                    {
                        "celex": {"type": "literal", "value": "123"},
                        "title": {"type": "literal", "value": 42},
                    }
                ]
            },
        },
    ],
)
async def test_malformed_sparql_data_raises_api_response_error(payload: object) -> None:
    with respx.mock(assert_all_called=True) as router:
        router.get(EURLEX_URL).respond(200, json=payload)
        with pytest.raises(ApiResponseError):
            await EurLexClient().fetch_data({"query": "law"})
