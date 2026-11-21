import httpx
import main
import pytest
import respx
from dataPreparation import reading as reading_module
from dataPreparation.analysis import AnalysisConfigurationError
from dataPreparation.container import AnalysisDataContainer, KeywordItem
from dataPreparation.settings import Settings

GOOGLE_API_URL = "https://factchecktools.googleapis.com/v1alpha1/claims:search"


@pytest.mark.asyncio
async def test_analysis_and_check_are_separate_operations_with_analysis_handoff(
    monkeypatch,
) -> None:
    async def mock_analysis(text: str, top_keywords: int = 5) -> AnalysisDataContainer:
        assert text == "A claim to verify."
        return AnalysisDataContainer(
            source_text=text,
            category="Prawo i Administracja",
            confidence=0.9,
            keywords=[KeywordItem("claim", "The statement topic.")],
            statements=["A claim to verify."],
        )

    monkeypatch.setattr(main, "run_analysis", mock_analysis)
    monkeypatch.setenv("GOOGLE_FACT_CHECK_API_KEY", "test-key")
    transport = httpx.ASGITransport(app=main.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        analyze_response = await client.post("/api/analyze", json={"text": "A claim to verify."})
        assert analyze_response.status_code == 200
        analysis = analyze_response.json()

        with respx.mock(assert_all_called=True) as router:
            router.get(GOOGLE_API_URL).respond(200, json={"claims": []})
            check_response = await client.post(
                "/api/check",
                json={"analysis": analysis, "category": "fact_check", "language_code": "en"},
            )

    assert check_response.status_code == 200
    results = check_response.json()
    assert len(results) == 1
    assert results[0]["request"]["query"] == "A claim to verify."
    assert results[0]["request"]["metadata"] == {"analysis_category": "Prawo i Administracja"}
    assert results[0]["results"][0]["result"]["items"] == []


@pytest.mark.asyncio
async def test_analysis_endpoint_returns_service_unavailable_without_llm_key(monkeypatch) -> None:
    async def missing_configuration(*args, **kwargs):
        raise AnalysisConfigurationError("Set FREELLM_API_KEY")

    monkeypatch.setattr(main, "run_analysis", missing_configuration)
    transport = httpx.ASGITransport(app=main.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/api/analyze", json={"text": "A claim."})

    assert response.status_code == 503


@pytest.mark.asyncio
async def test_check_endpoint_serializes_missing_provider_key(monkeypatch) -> None:
    monkeypatch.setattr(
        reading_module.Settings,
        "from_environment",
        classmethod(
            lambda cls: Settings(
                freelmm_api_key=None,
                freelmm_base_url=None,
                freelmm_model="auto",
                google_fact_check_api_key=None,
                llm_timeout=30,
                llm_max_retries=2,
            )
        ),
    )
    transport = httpx.ASGITransport(app=main.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/check",
            json={
                "analysis": {
                    "source_text": "A claim.",
                    "category": "Science",
                    "statements": ["A claim."],
                }
            },
        )

    assert response.status_code == 200
    error = response.json()[0]["results"][0]["error"]
    assert error["type"] == "ApiAuthError"
    assert error["source"] == "google_fact_check"
