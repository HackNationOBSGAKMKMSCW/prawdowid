import httpx
import pytest
import respx

from backend.dataPreparation.apiReading import Category
from backend.dataPreparation.container import AnalysisDataContainer
from backend.dataPreparation.reading import run_api_reading

GOOGLE_API_URL = "https://factchecktools.googleapis.com/v1alpha1/claims:search"


@pytest.mark.asyncio
async def test_api_reading_uses_analysis_statements_and_preserves_topic_metadata() -> None:
    analysis = AnalysisDataContainer(
        source_text="Two claims.",
        category="Technologia i IT",
        language_code="pl",
        statements=["first claim", "second claim"],
    )
    with respx.mock(assert_all_called=True) as router:
        route = router.get(GOOGLE_API_URL).respond(200, json={"claims": []})
        results = await run_api_reading(
            analysis,
            category=Category.FACT_CHECK,
            api_keys={"google_fact_check": "test-key"},
        )

    assert len(results) == 2
    assert [result.request.query for result in results] == ["first claim", "second claim"]
    assert all(
        result.request.metadata == {"analysis_category": "Technologia i IT"} for result in results
    )
    assert all(result.request.categories == [Category.FACT_CHECK] for result in results)
    assert route.call_count == 2
    assert all(call.request.url.params["languageCode"] == "pl" for call in route.calls)
    assert all(call.request.url.params["key"] == "test-key" for call in route.calls)


@pytest.mark.asyncio
async def test_api_reading_rejects_analysis_without_statements() -> None:
    with pytest.raises(ValueError, match="at least one statement"):
        await run_api_reading(AnalysisDataContainer(category="Zdrowie"))


@pytest.mark.asyncio
async def test_api_reading_does_not_close_an_injected_http_client() -> None:
    analysis = AnalysisDataContainer(category="Prawo", statements=["a claim"])
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json={"claims": []}))
    )

    await run_api_reading(
        analysis,
        api_keys={"google_fact_check": "test-key"},
        http_client=client,
    )

    assert not client.is_closed
    await client.aclose()
