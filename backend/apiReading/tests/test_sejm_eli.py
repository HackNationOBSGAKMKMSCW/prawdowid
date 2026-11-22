import json
from pathlib import Path

import httpx
import pytest
import respx
from apiReading.clients.sejm_eli import SejmEliClient
from apiReading.exceptions import ApiHttpError, ApiResponseError, InvalidFiltersError
from apiReading.models import Category, ReadingRequest

ELI_SEARCH_URL = "https://api.sejm.gov.pl/eli/acts/search"
ELI_DETAIL_URL = "https://api.sejm.gov.pl/eli/acts/DU/2024/1984"
FIXTURES = Path(__file__).parent / "fixtures"


def _fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


@pytest.mark.asyncio
async def test_reference_search_resolves_act_directly_and_normalizes_details() -> None:
    with respx.mock(assert_all_called=True) as router:
        route = router.get(ELI_DETAIL_URL).respond(200, json=_fixture("sejm_eli_act.json"))
        result = await SejmEliClient().fetch_data({"query": "Zmiana (Dz.U. z 2024 r. poz. 1984)"})

    assert dict(route.calls[0].request.url.params) == {}
    assert result.total == 1
    assert result.next_cursor is None
    assert result.items[0].id == "eli_du_2024_1984"
    assert result.items[0].payload == {
        "title": _fixture("sejm_eli_act.json")["title"],
        "act_type": "Rozporządzenie",
        "publisher": "DU",
        "year": 2024,
        "position": 1984,
        "eli_id": "DU/2024/1984",
        "display_address": "Dz.U. 2024 poz. 1984",
        "status": "obowiązujący",
        "promulgation_date": "2024-12-31",
        "announcement_date": "2024-12-30",
        "change_date": "2025-01-02T10:57:07",
        "url_isap": "https://isap.sejm.gov.pl/isap.nsf/DocDetails.xsp?id=WDU20240001984",
        "url_text_html": "https://api.sejm.gov.pl/eli/acts/DU/2024/1984/text.html",
        "url_text_pdf": "https://api.sejm.gov.pl/eli/acts/DU/2024/1984/text.pdf",
        "source_name": "Sejm ELI / ISAP",
    }


@pytest.mark.parametrize(
    ("query", "expected_path"),
    [
        ("Monitor Polski z 2022 r. pozycja 51", "/eli/acts/MP/2022/51"),
        ("Dz. U. 2021 poz. 10", "/eli/acts/DU/2021/10"),
    ],
)
def test_reference_parser_supports_both_official_publishers(query: str, expected_path: str) -> None:
    spec = SejmEliClient().build_request({"query": query})

    assert spec.path == expected_path


@pytest.mark.asyncio
async def test_title_search_uses_verified_parameters_and_official_fixture() -> None:
    fixture = _fixture("sejm_eli_search.json")
    with respx.mock(assert_all_called=True) as router:
        route = router.get(ELI_SEARCH_URL).respond(200, json=fixture)
        result = await SejmEliClient().fetch_data(
            {"query": "algorytmu przekazywania środków", "page_size": 5}
        )

    params = route.calls[0].request.url.params
    assert params["title"] == "algorytmu przekazywania środków"
    assert params["limit"] == "5"
    assert params["offset"] == "0"
    assert result.total == 1
    assert result.next_cursor is None
    assert result.items[0].id == "eli_du_2024_1984"
    assert result.items[0].payload["eli_id"] == "DU/2024/1984"
    assert SejmEliClient.requires_api_key is False
    assert SejmEliClient.supported_categories == frozenset({Category.LEGAL_ACT})


@pytest.mark.asyncio
async def test_reading_request_and_search_pagination_are_mapped() -> None:
    request = ReadingRequest(query="ustawa o podatku", categories=[Category.LEGAL_ACT])
    filters = SejmEliClient().filters_from_request(request)
    assert filters == {"query": "ustawa o podatku", "page_size": 10}

    fixture = _fixture("sejm_eli_search.json")
    fixture["totalCount"] = 3
    with respx.mock(assert_all_called=True) as router:
        route = router.get(ELI_SEARCH_URL).respond(200, json=fixture)
        first_page = await SejmEliClient().fetch_data({"query": "ustawa", "page_size": 1})
        await SejmEliClient().fetch_data(
            {"query": "ustawa", "page_size": 1, "page_token": first_page.next_cursor}
        )

    assert first_page.next_cursor == "1"
    assert route.calls[1].request.url.params["offset"] == "1"


@pytest.mark.asyncio
async def test_empty_search_response_is_valid() -> None:
    with respx.mock(assert_all_called=True) as router:
        router.get(ELI_SEARCH_URL).respond(200, json={"count": 0, "items": [], "totalCount": 0})
        result = await SejmEliClient().fetch_data({"query": "missing act"})

    assert result.items == []
    assert result.total == 0
    assert result.next_cursor is None


@pytest.mark.asyncio
async def test_unknown_act_reference_returns_typed_not_found_error() -> None:
    with respx.mock(assert_all_called=True) as router:
        router.get(ELI_DETAIL_URL).respond(404)
        with pytest.raises(ApiHttpError) as error:
            await SejmEliClient(max_retries=0).fetch_data({"query": "Dz.U. 2024 poz. 1984"})

    assert error.value.status_code == 404


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "filters",
    [
        {},
        {"query": " "},
        {"query": "a" * 301},
        {"query": "ordinary query", "page_size": True},
        {"query": "ordinary query", "page_size": 21},
        {"query": "ordinary query", "page_token": True},
        {"query": "ordinary query", "page_token": "-1"},
        {"query": "ordinary query", "max_age_days": False},
        {"query": "ordinary query", "max_age_days": 0},
        {"query": "ordinary query", "unknown": "filter"},
        {"query": "Dz.U. 2024 poz. 1984", "page_size": True},
    ],
)
async def test_invalid_filters_fail_before_request(filters: dict) -> None:
    with respx.mock(assert_all_called=False) as router:
        router.get(ELI_SEARCH_URL)
        router.get(ELI_DETAIL_URL)
        with pytest.raises(InvalidFiltersError):
            await SejmEliClient().fetch_data(filters)

    assert router.calls.call_count == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload",
    [
        [],
        {"items": {}},
        {"items": ["not an act"]},
        {"items": [{"publisher": "DU", "year": 2024, "pos": 1}]},
        {
            "items": [
                {
                    "publisher": "DU",
                    "year": True,
                    "pos": 1,
                    "title": "Act",
                }
            ]
        },
        {
            "items": [
                {
                    "publisher": "DU",
                    "year": 2024,
                    "pos": 1,
                    "title": "Act",
                    "promulgation": "not-a-date",
                }
            ]
        },
    ],
)
async def test_malformed_search_responses_raise_api_response_error(payload: object) -> None:
    with respx.mock(assert_all_called=True) as router:
        router.get(ELI_SEARCH_URL).respond(200, json=payload)
        with pytest.raises(ApiResponseError):
            await SejmEliClient().fetch_data({"query": "Act"})


@pytest.mark.asyncio
async def test_malformed_json_raises_api_response_error() -> None:
    with respx.mock(assert_all_called=True) as router:
        router.get(ELI_SEARCH_URL).respond(200, text="not json")
        with pytest.raises(ApiResponseError):
            await SejmEliClient().fetch_data({"query": "Act"})


@pytest.mark.asyncio
async def test_rate_limit_retry_uses_shared_retry_after_and_no_key_in_url() -> None:
    with respx.mock(assert_all_called=True) as router:
        route = router.get(ELI_SEARCH_URL)
        route.side_effect = [
            httpx.Response(429, headers={"Retry-After": "0"}),
            httpx.Response(200, json={"count": 0, "items": []}),
        ]
        await SejmEliClient(api_key="ignored-secret", max_retries=1).fetch_data(
            {"query": "ustawa", "page_size": 1}
        )

    assert route.call_count == 2
    assert "ignored-secret" not in str(route.calls[0].request.url)
