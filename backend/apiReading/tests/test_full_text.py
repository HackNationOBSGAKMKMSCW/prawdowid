import pytest
import respx
from apiReading import run_full_text
from apiReading.exceptions import ApiAuthError
from apiReading.full_text import MAX_QUERY_CHARS
from apiReading.models import Category
from textAnalysis.container import AnalysisDataContainer

GOOGLE_API_URL = "https://factchecktools.googleapis.com/v1alpha1/claims:search"


@pytest.mark.asyncio
async def test_run_full_text_searches_once_with_source_text(monkeypatch, capsys) -> None:
    monkeypatch.setenv("GOOGLE_FACT_CHECK_API_KEY", "test-key")
    source_text = "  original text to search  "
    analysis = AnalysisDataContainer(
        source_text=source_text,
        category="Technologia i IT",
        language_code="pl",
        statements=["statement that must be ignored"],
    )
    claim = {"text": "claim text", "claimReview": []}
    with respx.mock(assert_all_called=True) as router:
        route = router.get(GOOGLE_API_URL).respond(200, json={"claims": [claim]})
        result = await run_full_text(analysis)

    assert route.call_count == 1
    assert route.calls[0].request.url.params["query"] == "original text to search"
    assert route.calls[0].request.url.params["languageCode"] == "pl"
    assert route.calls[0].request.url.params["key"] == "test-key"
    assert result.request.categories == [Category.FACT_CHECK]
    assert result.request.page_size == 10
    assert result.request.metadata == {
        "analysis_category": "Technologia i IT",
        "truncated": False,
    }
    assert result.items[0].payload == claim
    output = capsys.readouterr().out
    assert source_text.strip() not in output
    assert "test-key" not in output


@pytest.mark.asyncio
async def test_run_full_text_rejects_blank_source_text() -> None:
    with pytest.raises(ValueError, match="source text"):
        await run_full_text(AnalysisDataContainer(source_text="  \n "))


@pytest.mark.asyncio
async def test_run_full_text_truncates_long_queries_and_marks_metadata(monkeypatch) -> None:
    monkeypatch.setenv("GOOGLE_FACT_CHECK_API_KEY", "test-key")
    analysis = AnalysisDataContainer(source_text="x" * (MAX_QUERY_CHARS + 1))
    with respx.mock(assert_all_called=True) as router:
        route = router.get(GOOGLE_API_URL).respond(200, json={"claims": []})
        result = await run_full_text(analysis)

    assert route.calls[0].request.url.params["query"] == "x" * MAX_QUERY_CHARS
    assert result.request.metadata["truncated"] is True


@pytest.mark.asyncio
async def test_run_full_text_returns_auth_error_without_api_key(monkeypatch, capsys) -> None:
    monkeypatch.delenv("GOOGLE_FACT_CHECK_API_KEY", raising=False)
    analysis = AnalysisDataContainer(source_text="private search text")

    result = await run_full_text(analysis)

    assert len(result.results) == 1
    assert isinstance(result.results[0].error, ApiAuthError)
    assert "private search text" not in capsys.readouterr().out
