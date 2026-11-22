import json
from pathlib import Path

import pytest
import respx
from apiReading.base import RequestSpec
from apiReading.clients.dane_gov import DaneGovClient
from apiReading.exceptions import ApiResponseError, InvalidFiltersError
from apiReading.models import Category, ReadingRequest

DANE_GOV_DATASETS_URL = "https://api.dane.gov.pl/datasets"
FIXTURE_PATH = Path(__file__).parent / "fixtures" / "dane_gov_search.json"


def _search_fixture() -> dict:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def test_dane_gov_client_uses_open_data_and_does_not_require_api_key() -> None:
    client = DaneGovClient()

    assert client.name == "dane_gov"
    assert client.supported_categories == frozenset({Category.OPEN_DATA})
    assert client.requires_api_key is False


def test_build_request_maps_filters_to_dataset_search_parameters() -> None:
    request = DaneGovClient().build_request(
        {"query": "  transport  ", "page_size": 25, "page_token": "3"}
    )

    assert isinstance(request, RequestSpec)
    assert request.method == "GET"
    assert request.path == "/datasets"
    assert request.params == {"q": "transport", "page": 3, "per_page": 25}


@pytest.mark.asyncio
async def test_search_maps_fixture_to_flat_items_and_uses_no_api_key() -> None:
    with respx.mock(assert_all_called=True) as router:
        route = router.get(DANE_GOV_DATASETS_URL).respond(200, json=_search_fixture())
        result = await DaneGovClient().fetch_data({"query": "energia", "page_size": 1})

    request = route.calls[0].request
    assert dict(request.url.params) == {"q": "energia", "page": "1", "per_page": "1"}
    assert "key" not in request.url.params
    assert result.source == "dane_gov"
    assert result.total == 365
    assert result.next_cursor == "2"
    assert len(result.items) == 1
    assert result.items[0].id == "307"
    assert result.items[0].payload == {
        "title": "STRATEG",
        "notes": ", transport, <mark>energy</mark> security and environment, regional development, human capital, social capital, sustainable",
        "institution": "34",
        "url": "http://strateg.stat.gov.pl/",
        "modified": "2025-01-22T09:51:54",
        "resources_count": 3,
    }


@pytest.mark.asyncio
async def test_empty_response_has_no_items_or_next_cursor() -> None:
    with respx.mock(assert_all_called=True) as router:
        router.get(DANE_GOV_DATASETS_URL).respond(
            200,
            json={"data": [], "links": {"next": None}, "meta": {"pagination": {"total": 0}}},
        )
        result = await DaneGovClient().fetch_data({"query": "nothing"})

    assert result.items == []
    assert result.total == 0
    assert result.next_cursor is None


@pytest.mark.asyncio
async def test_pagination_token_is_sent_as_numeric_page_and_meta_provides_next_cursor() -> None:
    with respx.mock(assert_all_called=True) as router:
        route = router.get(DANE_GOV_DATASETS_URL).respond(
            200,
            json={
                "data": [],
                "meta": {"page": 4, "pages": 6, "total": 60},
            },
        )
        result = await DaneGovClient().fetch_data(
            {"query": "transport", "page_size": 20, "page_token": "4"}
        )

    assert route.calls[0].request.url.params["page"] == "4"
    assert route.calls[0].request.url.params["per_page"] == "20"
    assert result.next_cursor == "5"
    assert result.total == 60


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload",
    [
        [],
        {},
        {"data": ["not a dataset"]},
        {"data": [{"attributes": {}, "relationships": {}}]},
        {"data": [{"id": "1", "relationships": {}}]},
        {"data": [{"id": "1", "attributes": {}, "relationships": []}]},
        {
            "data": [
                {
                    "id": "1",
                    "attributes": {"title": 42},
                    "relationships": {},
                }
            ]
        },
        {"data": [], "links": {"next": "https://api.dane.gov.pl/datasets?page=bad"}},
    ],
)
async def test_malformed_responses_raise_api_response_error(payload) -> None:
    with respx.mock(assert_all_called=True) as router:
        router.get(DANE_GOV_DATASETS_URL).respond(200, json=payload)
        with pytest.raises(ApiResponseError):
            await DaneGovClient().fetch_data({"query": "transport"})


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "filters",
    [
        {},
        {"query": "  "},
        {"query": 3},
        {"query": "data", "unknown": "filter"},
        {"query": "data", "page_size": True},
        {"query": "data", "page_size": 0},
        {"query": "data", "page_size": 101},
        {"query": "data", "page_token": True},
        {"query": "data", "page_token": 2},
        {"query": "data", "page_token": "0"},
        {"query": "data", "page_token": "next"},
    ],
)
async def test_invalid_filters_are_rejected_before_request(filters) -> None:
    with respx.mock(assert_all_called=False) as router:
        router.get(DANE_GOV_DATASETS_URL)
        with pytest.raises(InvalidFiltersError):
            await DaneGovClient().fetch_data(filters)

    assert router.calls.call_count == 0


def test_filters_from_reading_request_maps_query_and_page_size() -> None:
    request = ReadingRequest(query="open data", categories=[Category.OPEN_DATA], page_size=7)

    assert DaneGovClient().filters_from_request(request) == {"query": "open data", "page_size": 7}
