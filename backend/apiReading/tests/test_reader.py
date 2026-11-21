import asyncio
from datetime import UTC, datetime
from typing import Any

import httpx
import pytest
import respx
from apiReading import registry
from apiReading.base import BaseApiClient, RequestSpec
from apiReading.clients import (
    DaneGovClient,
    EurLexClient,
    GoogleFactCheckClient,
    SejmApiClient,
    SejmEliClient,
)
from apiReading.exceptions import ApiHttpError, InvalidFiltersError, NoSourcesAvailableError
from apiReading.models import Category, FetchResult, Item, ReadingRequest
from apiReading.reader import read
from apiReading.registry import CLIENTS_BY_CATEGORY, clients_for_categories

OTHER_API_URL = "https://api.other.invalid/search"
GOOGLE_API_URL = "https://factchecktools.googleapis.com/v1alpha1/claims:search"
SEJM_ELI_DETAIL_URL = "https://api.sejm.gov.pl/eli/acts/DU/2024/1984"
SEJM_ELI_SEARCH_URL = "https://api.sejm.gov.pl/eli/acts/search"
SEJM_PROCESS_URL = "https://api.sejm.gov.pl/sejm/term10/processes"
EURLEX_SPARQL_URL = "https://publications.europa.eu/webapi/rdf/sparql"
DANE_GOV_URL = "https://api.dane.gov.pl/datasets"


@pytest.mark.asyncio
async def test_article_extract_category_is_internal_and_not_searchable() -> None:
    assert clients_for_categories([Category.ARTICLE_EXTRACT]) == ([], [Category.ARTICLE_EXTRACT])
    assert CLIENTS_BY_CATEGORY[Category.FACT_CHECK] == (GoogleFactCheckClient,)
    assert CLIENTS_BY_CATEGORY[Category.LEGAL_ACT] == (SejmEliClient, EurLexClient)
    assert CLIENTS_BY_CATEGORY[Category.LEGISLATIVE_PROCESS] == (SejmApiClient,)
    assert CLIENTS_BY_CATEGORY[Category.OPEN_DATA] == (DaneGovClient,)

    with pytest.raises(NoSourcesAvailableError):
        await read(
            ReadingRequest(query="article", categories=[Category.ARTICLE_EXTRACT]),
            api_keys={"diffbot_article": "not-a-search-key"},
        )


class _OtherClient(BaseApiClient):
    name = "other"
    base_url = "https://api.other.invalid"
    supported_categories = frozenset({Category.FACT_CHECK})

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(max_retries=0, **kwargs)

    def filters_from_request(self, request: ReadingRequest) -> dict[str, Any]:
        return {"query": request.query}

    def build_request(self, filters: dict[str, Any]) -> RequestSpec:
        return RequestSpec("GET", "/search", params=filters)

    def parse_response(self, response: httpx.Response) -> FetchResult:
        payload = response.json()
        return FetchResult(
            source=self.name,
            items=[Item(id=str(item["id"]), source=self.name, payload=item) for item in payload],
            fetched_at=datetime.now(UTC),
        )


class _KeylessClient(_OtherClient):
    name = "keyless"
    base_url = "https://api.keyless.invalid"
    supported_categories = frozenset({Category.LEGAL_ACT})
    requires_api_key = False


def test_reading_request_validates_and_is_immutable() -> None:
    request = ReadingRequest(
        query="claim",
        categories=[Category.FACT_CHECK],
        metadata={"record_id": 42},
    )

    assert request.query == "claim"
    assert request.categories == [Category.FACT_CHECK]
    assert request.metadata == {"record_id": 42}
    with pytest.raises(ValueError):
        request.query = "changed"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload",
    [
        {"query": "  ", "categories": ["fact_check"]},
        {"query": "claim", "categories": []},
        {"query": "claim", "categories": ["fact_check", "fact_check"]},
        {"query": "claim", "categories": ["unknown"]},
    ],
)
async def test_invalid_requests_raise_typed_error_before_http(payload) -> None:
    client = httpx.AsyncClient(transport=httpx.MockTransport(lambda _: pytest.fail("HTTP called")))
    with pytest.raises(InvalidFiltersError):
        await read(payload, api_keys={"google_fact_check": "key"}, http_client=client)
    assert not client.is_closed
    await client.aclose()


@pytest.mark.asyncio
async def test_read_fans_out_once_per_client_and_aggregates_partial_failure(monkeypatch) -> None:
    monkeypatch.setitem(
        registry.CLIENTS_BY_CATEGORY,
        Category.FACT_CHECK,
        (GoogleFactCheckClient, _OtherClient),
    )
    both_started = asyncio.Event()
    started = 0
    seen_requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal started
        started += 1
        seen_requests.append(request)
        if started == 2:
            both_started.set()
        await asyncio.wait_for(both_started.wait(), timeout=1)
        if request.url.host == "api.other.invalid":
            return httpx.Response(503)
        return httpx.Response(200, json={"claims": [{"text": "claim"}]})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as shared_client:
        request = ReadingRequest(
            query="claim",
            categories=[Category.FACT_CHECK],
            language_code="pl",
            max_age_days=30,
            page_size=3,
            metadata={"record_id": 42},
        )
        result = await read(
            request,
            api_keys={"google_fact_check": "key", "other": "other-key"},
            http_client=shared_client,
        )
        assert not shared_client.is_closed

    assert result.request == request
    assert result.request.metadata == {"record_id": 42}
    assert len(result.results) == 2
    assert result.results[0].result is not None
    assert result.results[1].error is not None
    assert isinstance(result.results[1].error, ApiHttpError)
    assert [item.source for item in result.items] == ["google_fact_check"]
    assert result.categories_without_source == []
    assert result.duration_ms >= 0
    google_params = next(
        request.url.params
        for request in seen_requests
        if request.url.host == "factchecktools.googleapis.com"
    )
    assert google_params["query"] == "claim"
    assert google_params["languageCode"] == "pl"
    assert google_params["maxAgeDays"] == "30"
    assert google_params["pageSize"] == "3"
    assert "metadata" not in google_params


@pytest.mark.asyncio
async def test_read_missing_key_returns_auth_outcome_without_request() -> None:
    calls = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json={"claims": []})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as shared_client:
        result = await read(
            ReadingRequest(query="claim", categories=[Category.FACT_CHECK]),
            http_client=shared_client,
        )
        assert not shared_client.is_closed

    assert calls == 0
    assert result.results[0].error is not None
    assert result.results[0].error.source == "google_fact_check"
    assert result.items == []


@pytest.mark.asyncio
async def test_read_allows_client_without_api_key(monkeypatch) -> None:
    monkeypatch.setitem(registry.CLIENTS_BY_CATEGORY, Category.LEGAL_ACT, (_KeylessClient,))
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda _: httpx.Response(200, json=[{"id": "act-1", "title": "Act"}])
        )
    )

    try:
        result = await read(
            ReadingRequest(query="Act", categories=[Category.LEGAL_ACT]),
            http_client=client,
        )
    finally:
        await client.aclose()

    assert result.results[0].error is None
    assert result.results[0].result is not None
    assert [item.id for item in result.items] == ["act-1"]


@pytest.mark.asyncio
async def test_read_fans_out_to_real_clients_and_preserves_partial_success() -> None:
    with respx.mock(assert_all_called=True) as router:
        google = router.get(GOOGLE_API_URL).respond(200, json={"claims": [{"text": "claim"}]})
        sejm_eli = router.get(SEJM_ELI_DETAIL_URL).respond(500)
        eurlex = router.get(EURLEX_SPARQL_URL).respond(
            200,
            json={
                "head": {"vars": ["celex", "title", "docType", "date"]},
                "results": {"bindings": []},
            },
        )
        result = await read(
            ReadingRequest(
                query="Dz.U. 2024 poz. 1984",
                categories=[Category.FACT_CHECK, Category.LEGAL_ACT],
            ),
            api_keys={"google_fact_check": "google-key"},
        )

    assert google.called
    assert sejm_eli.called
    assert eurlex.called
    assert [outcome.source for outcome in result.results] == [
        "google_fact_check",
        "sejm_eli",
        "eurlex",
    ]
    assert result.results[0].result is not None
    assert result.results[1].error is not None
    assert isinstance(result.results[1].error, ApiHttpError)
    assert result.results[2].error is None
    assert [item.source for item in result.items] == ["google_fact_check"]


@pytest.mark.asyncio
async def test_read_runs_all_keyless_sources_for_their_categories() -> None:
    with respx.mock(assert_all_called=True) as router:
        router.get(SEJM_ELI_SEARCH_URL).respond(
            200,
            json={
                "items": [
                    {
                        "publisher": "DU",
                        "year": 2024,
                        "pos": 5,
                        "title": "Example act",
                    }
                ],
                "totalCount": 1,
            },
        )
        router.get(SEJM_PROCESS_URL).respond(
            200,
            json=[{"number": "5", "title": "Example bill"}],
        )
        router.get(EURLEX_SPARQL_URL).respond(
            200,
            json={
                "head": {"vars": ["celex", "title", "docType", "date"]},
                "results": {"bindings": []},
            },
        )
        router.get(DANE_GOV_URL).respond(
            200,
            json={"data": [], "links": {"next": None}, "meta": {"count": 0}},
        )
        result = await read(
            ReadingRequest(
                query="public policy",
                categories=[
                    Category.LEGAL_ACT,
                    Category.LEGISLATIVE_PROCESS,
                    Category.OPEN_DATA,
                ],
            )
        )

    assert [outcome.source for outcome in result.results] == [
        "sejm_eli",
        "eurlex",
        "sejm",
        "dane_gov",
    ]
    assert all(outcome.error is None for outcome in result.results)
    assert [item.id for item in result.items] == ["eli_du_2024_5", "sejm_10_5"]


@pytest.mark.asyncio
async def test_read_with_only_unregistered_categories_raises_without_http(monkeypatch) -> None:
    monkeypatch.setitem(registry.CLIENTS_BY_CATEGORY, Category.FACT_CHECK, ())
    client = httpx.AsyncClient(transport=httpx.MockTransport(lambda _: pytest.fail("HTTP called")))

    with pytest.raises(NoSourcesAvailableError):
        await read(
            ReadingRequest(query="claim", categories=[Category.FACT_CHECK]),
            api_keys={"google_fact_check": "key"},
            http_client=client,
        )

    assert not client.is_closed
    await client.aclose()


@pytest.mark.asyncio
async def test_owned_http_client_closes_when_read_is_cancelled(monkeypatch) -> None:
    from importlib import import_module

    reader_module = import_module("apiReading.reader")
    real_async_client = httpx.AsyncClient
    request_started = asyncio.Event()
    tracked_client: httpx.AsyncClient | None = None

    async def handler(_: httpx.Request) -> httpx.Response:
        request_started.set()
        await asyncio.Event().wait()
        raise AssertionError("unreachable")

    def create_client() -> httpx.AsyncClient:
        nonlocal tracked_client
        tracked_client = real_async_client(transport=httpx.MockTransport(handler))
        return tracked_client

    monkeypatch.setattr(reader_module.httpx, "AsyncClient", create_client)
    task = asyncio.create_task(
        read(
            ReadingRequest(query="claim", categories=[Category.FACT_CHECK]),
            api_keys={"google_fact_check": "key"},
        )
    )
    await asyncio.wait_for(request_started.wait(), timeout=1)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert tracked_client is not None and tracked_client.is_closed
