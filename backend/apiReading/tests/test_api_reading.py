import asyncio
import inspect
from datetime import UTC, datetime

import httpx
import pytest
import respx
from apiReading.aggregator import fetch_all
from apiReading.base import BaseApiClient, RequestSpec
from apiReading.clients import GoogleFactCheckClient
from apiReading.exceptions import (
    ApiAuthError,
    ApiConnectionError,
    ApiHttpError,
    ApiRateLimitError,
    ApiResponseError,
    ApiTimeoutError,
    InvalidFiltersError,
)
from apiReading.models import (
    Category,
    FetchResult,
    Item,
    ReadingRequest,
)

TEST_API_A_URL = "https://api.test-a.invalid/items"
TEST_API_B_URL = "https://api.test-b.invalid/records"
GOOGLE_FACT_CHECK_URL = "https://factchecktools.googleapis.com/v1alpha1/claims:search"


class _TestApiClient(BaseApiClient):
    name = "test_api_a"
    base_url = "https://api.test-a.invalid"
    supported_categories = frozenset({Category.FACT_CHECK})

    def filters_from_request(self, request: ReadingRequest) -> dict:
        return {"category": request.query}

    def build_request(self, filters):
        allowed = {"category", "page"}
        if set(filters) - allowed:
            raise InvalidFiltersError(self.name, "unsupported filter")
        page = filters.get("page", 1)
        if not isinstance(page, int) or isinstance(page, bool) or page < 1:
            raise InvalidFiltersError(self.name, "page must be a positive integer")
        return RequestSpec("GET", "/items", params=filters)

    def parse_response(self, response):
        payload = response.json()
        if not isinstance(payload, dict) or not isinstance(payload.get("items"), list):
            raise ApiResponseError(self.name, "expected an items list")
        items = [
            Item(id=str(item["id"]), source=self.name, payload=item) for item in payload["items"]
        ]
        return FetchResult(
            source=self.name,
            items=items,
            fetched_at=datetime.now(UTC),
            total=payload.get("total"),
        )


class _TestApiClientB(BaseApiClient):
    name = "test_api_b"
    base_url = "https://api.test-b.invalid"
    supported_categories = frozenset({Category.FACT_CHECK})

    def filters_from_request(self, request: ReadingRequest) -> dict:
        return {"query": request.query}

    def build_request(self, filters):
        return RequestSpec("GET", "/records", params=filters)

    def parse_response(self, response):
        payload = response.json()
        return FetchResult(
            source=self.name,
            items=[
                Item(id=str(item["id"]), source=self.name, payload=item)
                for item in payload["items"]
            ],
            fetched_at=datetime.now(UTC),
        )


def test_base_client_is_abstract_and_clients_share_fetch_signature() -> None:
    with pytest.raises(TypeError):
        BaseApiClient()

    class IncompleteClient(BaseApiClient):
        name = "incomplete"
        base_url = "https://incomplete.invalid"
        supported_categories = frozenset({Category.FACT_CHECK})

    with pytest.raises(TypeError):
        IncompleteClient()

    signature = inspect.signature(BaseApiClient.fetch_data)
    assert signature.return_annotation is FetchResult
    assert "filters" in signature.parameters
    assert inspect.signature(_TestApiClient.fetch_data) == signature
    assert inspect.signature(_TestApiClientB.fetch_data) == signature


@pytest.mark.asyncio
async def test_fetch_maps_response_and_preserves_raw_payload() -> None:
    with respx.mock(assert_all_called=True) as router:
        router.get(TEST_API_A_URL).mock(
            return_value=httpx.Response(
                200, json={"items": [{"id": 12, "title": "News"}], "total": 1}
            )
        )
        result = await _TestApiClient().fetch_data({"category": "news"})

    assert result.source == "test_api_a"
    assert result.total == 1
    assert result.items[0].id == "12"
    assert result.items[0].payload == {"id": 12, "title": "News"}


@pytest.mark.asyncio
async def test_invalid_filters_fail_before_making_a_request() -> None:
    with respx.mock(assert_all_called=False) as router:
        router.get(TEST_API_A_URL)
        with pytest.raises(InvalidFiltersError):
            await _TestApiClient().fetch_data({"page": 0})

    assert router.calls.call_count == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status", "error_type"),
    [
        (401, ApiAuthError),
        (403, ApiAuthError),
        (418, ApiHttpError),
        (500, ApiHttpError),
    ],
)
async def test_unsuccessful_statuses_map_to_typed_errors(status, error_type) -> None:
    with respx.mock(assert_all_called=True) as router:
        router.get(TEST_API_A_URL).respond(status_code=status, text="do not expose response body")
        with pytest.raises(error_type) as error:
            await _TestApiClient(max_retries=0).fetch_data()

    assert error.value.status_code == status
    assert "do not expose" not in str(error.value)


@pytest.mark.asyncio
async def test_rate_limit_retries_and_returns_typed_error_when_exhausted() -> None:
    with respx.mock(assert_all_called=True) as router:
        route = router.get(TEST_API_A_URL)
        route.side_effect = [
            httpx.Response(429, headers={"Retry-After": "0"}),
            httpx.Response(429, headers={"Retry-After": "0"}),
        ]
        with pytest.raises(ApiRateLimitError) as error:
            await _TestApiClient(max_retries=1, retry_backoff=0).fetch_data()

    assert route.call_count == 2
    assert error.value.status_code == 429
    assert error.value.retry_after == 0


@pytest.mark.asyncio
async def test_transient_server_error_retries_once() -> None:
    with respx.mock(assert_all_called=True) as router:
        route = router.get(TEST_API_A_URL)
        route.side_effect = [
            httpx.Response(503),
            httpx.Response(200, json={"items": [{"id": "ok"}]}),
        ]
        result = await _TestApiClient(max_retries=1, retry_backoff=0).fetch_data()

    assert route.call_count == 2
    assert result.items[0].id == "ok"


@pytest.mark.asyncio
async def test_base_client_retries_timeout_by_default() -> None:
    calls = 0

    async def handler(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise httpx.ReadTimeout("temporary timeout")
        return httpx.Response(200, json={"items": [{"id": "ok"}]})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    try:
        result = await _TestApiClient(client=client, max_retries=1, retry_backoff=0).fetch_data()
    finally:
        await client.aclose()

    assert calls == 2
    assert result.items[0].id == "ok"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("body", "error_type"),
    [
        ("not-json", ApiResponseError),
        ({"items": [{"title": "missing id"}]}, ApiResponseError),
        ({"wrong": []}, ApiResponseError),
    ],
)
async def test_invalid_response_payloads_raise_response_error(body, error_type) -> None:
    with respx.mock(assert_all_called=True) as router:
        router.get(TEST_API_A_URL).mock(
            return_value=httpx.Response(200, json=body)
            if isinstance(body, dict)
            else httpx.Response(200, text=body)
        )
        with pytest.raises(error_type):
            await _TestApiClient().fetch_data()


@pytest.mark.asyncio
async def test_timeout_and_connection_errors_are_translated() -> None:
    async def timeout_handler(_: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("secret request headers should not leak")

    timeout_client = httpx.AsyncClient(transport=httpx.MockTransport(timeout_handler))
    with pytest.raises(ApiTimeoutError):
        await _TestApiClient(client=timeout_client, max_retries=0).fetch_data()
    await timeout_client.aclose()

    async def connection_handler(_: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection details")

    connection_client = httpx.AsyncClient(transport=httpx.MockTransport(connection_handler))
    with pytest.raises(ApiConnectionError):
        await _TestApiClient(client=connection_client, max_retries=0).fetch_data()
    await connection_client.aclose()


@pytest.mark.asyncio
async def test_injected_and_owned_client_lifecycles() -> None:
    injected = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json={"items": [{"id": "ok"}]}))
    )
    async with _TestApiClient(client=injected) as client:
        await client.fetch_data()
    assert not injected.is_closed
    await injected.aclose()

    with respx.mock(assert_all_called=True) as router:
        router.get(TEST_API_A_URL).respond(200, json={"items": [{"id": "ok"}]})
        async with _TestApiClient() as owned:
            await owned.fetch_data()
            owned_client = owned._client
            assert owned_client is not None and not owned_client.is_closed
        assert owned_client.is_closed


@pytest.mark.asyncio
async def test_fetch_all_runs_concurrently_and_keeps_other_success_on_failure() -> None:
    both_started = asyncio.Event()
    calls = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 2:
            both_started.set()
        await asyncio.wait_for(both_started.wait(), timeout=1)
        if str(request.url) == TEST_API_B_URL:
            return httpx.Response(503)
        return httpx.Response(200, json={"items": [{"id": "a"}]})

    shared_transport_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    clients = {
        _TestApiClient(client=shared_transport_client, max_retries=0): {},
        _TestApiClientB(client=shared_transport_client, max_retries=0): {},
    }
    outcomes = await fetch_all(clients)
    await shared_transport_client.aclose()

    assert [outcome.source for outcome in outcomes] == ["test_api_a", "test_api_b"]
    assert outcomes[0].result is not None
    assert outcomes[1].error is not None
    assert isinstance(outcomes[1].error, ApiHttpError)


@pytest.mark.asyncio
async def test_fetch_all_can_propagate_errors() -> None:
    with respx.mock(assert_all_called=True) as router:
        router.get(TEST_API_A_URL).respond(status_code=400)
        with pytest.raises(ApiHttpError):
            await fetch_all({_TestApiClient(max_retries=0): {}}, return_exceptions=False)


def test_client_requires_https_base_url() -> None:
    with pytest.raises(TypeError, match="HTTPS"):

        class InsecureClient(BaseApiClient):
            name = "insecure"
            base_url = "http://insecure.invalid"
            supported_categories = frozenset({Category.FACT_CHECK})

            def build_request(self, filters):
                return None

            def filters_from_request(self, request):
                return {}

            def parse_response(self, response):
                return None


@pytest.mark.asyncio
async def test_google_fact_check_search_uses_fast_filtered_request_and_normalizes_results() -> None:
    claim = {
        "text": "A claim to verify",
        "claimant": "Example speaker",
        "claimDate": "2025-01-01T00:00:00Z",
        "claimReview": [
            {
                "publisher": {"name": "Fact Checker", "site": "fact-check.example"},
                "title": "Review title",
                "reviewDate": "2025-01-02T00:00:00Z",
                "url": "https://fact-check.example/review/1",
                "textualRating": "False",
                "languageCode": "pl",
            }
        ],
    }
    with respx.mock(assert_all_called=True) as router:
        route = router.get(GOOGLE_FACT_CHECK_URL).respond(
            200,
            json={"claims": [claim], "nextPageToken": "next-page"},
        )
        result = await GoogleFactCheckClient(api_key="test-key").fetch_data(
            {
                "query": "claim to verify",
                "language_code": "pl",
                "review_publisher_site_filter": "fact-check.example",
                "max_age_days": 30,
                "page_size": 5,
            }
        )

    params = route.calls[0].request.url.params
    assert params["query"] == "claim to verify"
    assert params["languageCode"] == "pl"
    assert params["reviewPublisherSiteFilter"] == "fact-check.example"
    assert params["maxAgeDays"] == "30"
    assert params["pageSize"] == "5"
    assert params["key"] == "test-key"
    assert params["prettyPrint"] == "false"
    assert "claimReview" in params["fields"]
    assert result.next_cursor == "next-page"
    assert result.total is None
    assert result.items[0].id.startswith("gfc_")
    assert result.items[0].payload == claim


@pytest.mark.asyncio
async def test_google_fact_check_paginates_with_opaque_cursor() -> None:
    with respx.mock(assert_all_called=True) as router:
        route = router.get(GOOGLE_FACT_CHECK_URL).respond(200, json={"claims": []})
        result = await GoogleFactCheckClient().fetch_data(
            {"review_publisher_site_filter": "fact-check.example", "page_token": "opaque-token"}
        )

    params = route.calls[0].request.url.params
    assert params["reviewPublisherSiteFilter"] == "fact-check.example"
    assert params["pageToken"] == "opaque-token"
    assert params["pageSize"] == "10"
    assert result.items == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "filters",
    [
        {},
        {"query": "  "},
        {"query": "claim", "page_size": 21},
        {"query": "claim", "page_size": True},
        {"query": "claim", "max_age_days": 0},
        {"query": "claim", "unknown": "filter"},
    ],
)
async def test_google_fact_check_rejects_invalid_filters_without_request(filters) -> None:
    with respx.mock(assert_all_called=False) as router:
        router.get(GOOGLE_FACT_CHECK_URL)
        with pytest.raises(InvalidFiltersError):
            await GoogleFactCheckClient().fetch_data(filters)

    assert router.calls.call_count == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload",
    [
        [],
        {"claims": {}},
        {"claims": ["not a claim"]},
        {"claims": [{"claimReview": ["not a review"]}]},
    ],
)
async def test_google_fact_check_rejects_invalid_response_shapes(payload) -> None:
    with respx.mock(assert_all_called=True) as router:
        router.get(GOOGLE_FACT_CHECK_URL).respond(200, json=payload)
        with pytest.raises(ApiResponseError):
            await GoogleFactCheckClient().fetch_data({"query": "claim"})
