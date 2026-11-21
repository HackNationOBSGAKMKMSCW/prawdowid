import json
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
import respx
from apiReading.clients.sejm import SejmApiClient
from apiReading.exceptions import ApiResponseError, InvalidFiltersError
from apiReading.models import Category, ReadingRequest

SEJM_PROCESSES_URL = "https://api.sejm.gov.pl/sejm/term10/processes"
FIXTURE_PATH = Path(__file__).parent / "fixtures" / "sejm_processes.json"


@pytest.mark.asyncio
async def test_sejm_process_search_normalizes_official_response_fixture() -> None:
    fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))

    with respx.mock(assert_all_called=True) as router:
        route = router.get(SEJM_PROCESSES_URL).respond(200, json=fixture)
        result = await SejmApiClient().fetch_data({"query": "wicemarszałków", "limit": 1})

    request = route.calls[0].request
    assert request.url.params["title"] == "wicemarszałków"
    assert request.url.params["limit"] == "1"
    assert request.url.params["offset"] == "0"
    assert result.source == "sejm"
    assert result.fetched_at.tzinfo == UTC
    assert result.total is None
    assert result.next_cursor == "1"
    assert [item.id for item in result.items] == ["sejm_10_1"]
    assert result.items[0].payload == {
        "title": fixture[0]["title"],
        "number": "1",
        "print_numbers": ["2"],
        "process_start_date": "2023-11-13",
        "passed": True,
        "document_type": "projekt uchwały",
        "urls": {
            "isap": "https://isap.sejm.gov.pl/isap.nsf/DocDetails.xsp?id=WMP20230001261",
            "eli": "https://eli.gov.pl/eli/MP/2023/1261/ogl",
            "eli-api": "https://api.sejm.gov.pl/eli/acts/MP/2023/1261",
        },
    }


@pytest.mark.asyncio
async def test_sejm_defaults_term_and_maps_reading_request() -> None:
    request = ReadingRequest(query="projekt ustawy", categories=[Category.LEGISLATIVE_PROCESS])

    with respx.mock(assert_all_called=True) as router:
        route = router.get(SEJM_PROCESSES_URL).respond(200, json=[])
        result = await SejmApiClient().fetch_data(SejmApiClient().filters_from_request(request))

    assert route.calls[0].request.url.params["title"] == "projekt ustawy"
    assert route.calls[0].request.url.params["limit"] == "10"
    assert route.calls[0].request.url.params["offset"] == "0"
    assert result.items == []
    assert result.next_cursor is None
    assert SejmApiClient.requires_api_key is False
    assert SejmApiClient.supported_categories == frozenset({Category.LEGISLATIVE_PROCESS})


@pytest.mark.asyncio
async def test_sejm_uses_page_token_as_offset_cursor() -> None:
    with respx.mock(assert_all_called=True) as router:
        route = router.get(SEJM_PROCESSES_URL).respond(200, json=[])
        await SejmApiClient().fetch_data({"query": "projekt", "page_token": "25"})

    params = route.calls[0].request.url.params
    assert params["offset"] == "25"
    assert params["limit"] == "10"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"items": []},
        ["not a process"],
        [{"number": "1"}],
        [{"number": "1", "title": "Title", "passed": "yes"}],
        [{"number": "1", "title": "Title", "printsConsideredJointly": [1]}],
        [{"number": "1", "title": "Title", "links": ["invalid"]}],
    ],
)
async def test_sejm_rejects_malformed_response_shapes(payload) -> None:
    with respx.mock(assert_all_called=True) as router:
        router.get(SEJM_PROCESSES_URL).respond(200, json=payload)
        with pytest.raises(ApiResponseError):
            await SejmApiClient().fetch_data({"query": "Title"})


@pytest.mark.asyncio
async def test_sejm_rejects_invalid_filters_before_request() -> None:
    invalid_filters = [
        {},
        {"query": " "},
        {"query": "Title", "term": True},
        {"query": "Title", "term": 0},
        {"query": "Title", "limit": True},
        {"query": "Title", "limit": 101},
        {"query": "Title", "offset": False},
        {"query": "Title", "offset": -1},
        {"query": "Title", "page_token": "next"},
        {"query": "Title", "offset": 0, "page_token": "10"},
        {"query": "Title", "unknown": "filter"},
    ]
    with respx.mock(assert_all_called=False) as router:
        router.get(SEJM_PROCESSES_URL)
        for filters in invalid_filters:
            with pytest.raises(InvalidFiltersError):
                await SejmApiClient().fetch_data(filters)

    assert router.calls.call_count == 0


@pytest.mark.asyncio
async def test_sejm_retries_rate_limit_using_shared_retry_after_handling() -> None:
    with respx.mock(assert_all_called=True) as router:
        route = router.get(SEJM_PROCESSES_URL)
        route.side_effect = [
            httpx.Response(429, headers={"Retry-After": "0"}),
            httpx.Response(200, json=[]),
        ]
        result = await SejmApiClient(max_retries=1, retry_backoff=0).fetch_data(
            {"query": "projekt"}
        )

    assert route.call_count == 2
    assert result.items == []


def test_sejm_fixture_is_a_bare_array_from_the_official_process_endpoint() -> None:
    fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))

    assert isinstance(fixture, list)
    assert all("number" in process and "title" in process for process in fixture)


def test_fixture_dates_are_realistic_iso_dates() -> None:
    fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))

    for process in fixture:
        assert (
            datetime.fromisoformat(process["processStartDate"]).date().isoformat()
            == (process["processStartDate"])
        )
