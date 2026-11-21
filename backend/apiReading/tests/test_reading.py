import pytest
import respx
from apiReading import run
from apiReading.models import Category
from textAnalysis.container import AnalysisDataContainer

GOOGLE_API_URL = "https://factchecktools.googleapis.com/v1alpha1/claims:search"


@pytest.mark.asyncio
async def test_package_run_uses_analysis_statements_and_metadata(monkeypatch, capsys) -> None:
    monkeypatch.setenv("GOOGLE_FACT_CHECK_API_KEY", "test-key")
    analysis = AnalysisDataContainer(
        source_text="Two claims.",
        category="Technologia i IT",
        language_code="pl",
        statements=["first claim", "second claim"],
    )
    with respx.mock(assert_all_called=True) as router:
        route = router.get(GOOGLE_API_URL).respond(200, json={"claims": []})
        results = await run(analysis)

    assert len(results) == 2
    assert [result.request.query for result in results] == ["first claim", "second claim"]
    assert all(
        result.request.metadata == {"analysis_category": "Technologia i IT"} for result in results
    )
    assert all(result.request.categories == [Category.FACT_CHECK] for result in results)
    assert route.call_count == 2
    assert all(call.request.url.params["languageCode"] == "pl" for call in route.calls)
    assert all(call.request.url.params["key"] == "test-key" for call in route.calls)
    output = capsys.readouterr().out
    assert "[apiReading] Przygotowano zapytania: liczba=2" in output
    assert "[apiReading:google_fact_check] GET próba 1/3" in output
    assert "[apiReading] Pakiet zakończył pracę" in output


@pytest.mark.asyncio
async def test_package_run_rejects_analysis_without_statements() -> None:
    with pytest.raises(ValueError, match="at least one statement"):
        await run(AnalysisDataContainer(category="Zdrowie"))


def test_api_reading_package_exports_only_its_entry_point() -> None:
    import apiReading

    assert apiReading.__all__ == ["run"]
