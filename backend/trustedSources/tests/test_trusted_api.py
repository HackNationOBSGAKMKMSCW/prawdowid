import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from trustedSources import api
from trustedSources import registry as registry_module
from trustedSources.models import TrustedSearchReport
from trustedSources.registry import SourceRegistry


@pytest.fixture
def client(monkeypatch, registry: SourceRegistry) -> TestClient:
    monkeypatch.setattr(registry_module, "_default", registry)
    app = FastAPI()
    app.include_router(api.router)
    return TestClient(app)


def test_list_and_get_are_public(client: TestClient) -> None:
    sources = client.get("/api/trusted-sources").json()
    assert len(sources) == 4
    assert client.get(f"/api/trusted-sources/{sources[0]['id']}").status_code == 200
    assert client.get("/api/trusted-sources/nope").status_code == 404


def test_write_endpoints_are_gone(client: TestClient) -> None:
    assert client.post("/api/trusted-sources", json={"url": "https://kgsok.pl/"}).status_code == 405
    source_id = client.get("/api/trusted-sources").json()[0]["id"]
    assert client.delete(f"/api/trusted-sources/{source_id}").status_code == 405


def test_search_endpoint(client: TestClient, monkeypatch) -> None:
    seen = {}

    async def fake_search(queries):
        seen["queries"] = queries
        return TrustedSearchReport(queries=list(queries), hits=[])

    async def fake_queries(text):
        return [f"llm: {text}"]

    monkeypatch.setattr(api, "search", fake_search)
    monkeypatch.setattr(api, "queries_for_text", fake_queries)
    response = client.post("/api/trusted-sources/search", json={"text": "Ziemia jest płaska", "queries": ["płaska Ziemia"]})
    assert response.status_code == 200
    assert seen["queries"] == ["llm: Ziemia jest płaska", "płaska Ziemia"]
    assert client.post("/api/trusted-sources/search", json={}).status_code == 422
