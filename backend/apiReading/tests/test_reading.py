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

    assert apiReading.__all__ == ["run", "run_full_text"]


@pytest.mark.asyncio
async def test_package_run_returns_final_claim_payload(monkeypatch) -> None:
    monkeypatch.setenv("GOOGLE_FACT_CHECK_API_KEY", "test-key")
    claim = {
        "text": "claim text",
        "claimReview": [
            {
                "publisher": {"name": "Demagog"},
                "url": "https://example.test/review",
                "textualRating": "Fałsz",
            }
        ],
    }
    analysis = AnalysisDataContainer(statements=["claim text"], language_code="pl")
    with respx.mock(assert_all_called=True) as router:
        router.get(GOOGLE_API_URL).respond(200, json={"claims": [claim]})
        results = await run(analysis)

    assert [item.payload for item in results[0].items] == [claim]
    assert results[0].items[0].source == "google_fact_check"


def test_clean_statement_strips_meta_prefix_and_caps_length() -> None:
    from apiReading.reading import clean_statement

    assert clean_statement("Tekst zawiera twierdzenie, że Ziemia jest płaska.") == "Ziemia jest płaska"
    assert clean_statement("Autor tekstu twierdzi, że klimat się ociepla.") == "klimat się ociepla"
    assert len(clean_statement("słowo " * 100)) <= 100


def test_build_queries_orders_original_statement_keywords() -> None:
    from apiReading.reading import build_queries
    from textAnalysis.container import KeywordItem

    analysis = AnalysisDataContainer(
        original_text="ziemia jest płaska",
        keywords=[KeywordItem("Ziemia", "x"), KeywordItem("kształt", "y")],
    )
    first = build_queries(analysis, "Tekst zawiera twierdzenie, że Ziemia jest płaska.", True)
    assert first == ["ziemia jest płaska", "Ziemia kształt"]  # cleaned statement deduped
    later = build_queries(analysis, "Inne twierdzenie", False)
    assert later == ["Inne twierdzenie", "Ziemia kształt"]


@pytest.mark.asyncio
async def test_run_falls_back_to_next_query_only_when_empty(monkeypatch) -> None:
    from textAnalysis.container import KeywordItem

    monkeypatch.setenv("GOOGLE_FACT_CHECK_API_KEY", "test-key")
    analysis = AnalysisDataContainer(
        statements=["Autor twierdzi, że długie zdanie bez wyników"],
        keywords=[KeywordItem("klimat", "x")],
        language_code="pl",
    )
    claim = {"text": "klimat", "claimReview": []}

    def respond(request):
        import httpx

        query = request.url.params["query"]
        claims = [claim] if query == "klimat" else []
        return httpx.Response(200, json={"claims": claims})

    with respx.mock(assert_all_called=True) as router:
        route = router.get(GOOGLE_API_URL).mock(side_effect=respond)
        results = await run(analysis)

    assert route.call_count == 2
    assert results[0].request.query == "klimat"
    assert len(results[0].items) == 1


@pytest.mark.asyncio
async def test_run_does_not_fall_back_on_api_error(monkeypatch) -> None:
    from textAnalysis.container import KeywordItem

    monkeypatch.setenv("GOOGLE_FACT_CHECK_API_KEY", "test-key")
    analysis = AnalysisDataContainer(
        statements=["zdanie"], keywords=[KeywordItem("klimat", "x")], language_code="pl"
    )
    with respx.mock() as router:
        route = router.get(GOOGLE_API_URL).respond(403, json={"error": {"message": "denied"}})
        results = await run(analysis)

    assert route.call_count == 1
    assert results[0].items == []
