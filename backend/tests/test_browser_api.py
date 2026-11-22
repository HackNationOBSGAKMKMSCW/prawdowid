"""``server:app``: kontrakt endpointów dla frontendu, bez bazy i bez modeli (atrapy)."""

from __future__ import annotations

from pathlib import Path
from uuid import UUID

import api_store
import pytest
from database.migrate import discover
from fastapi.testclient import TestClient
from server import create_app


def report(verdict: str = "falsz") -> dict:
    ok = {"status": "ok"}
    return {
        "evidence": {**ok, "data": {}},
        "input_analysis": {
            **ok,
            "data": {
                "manipulation": {"manipulation_detected": False, "score": 90, "fragments": []}
            },
        },
        "claims_verdict": {
            **ok,
            "data": {
                "verdict": verdict,
                "summary": "Podsumowanie.",
                "claims": [
                    {
                        "claim": "Szczepionki powodują autyzm.",
                        "verdict": verdict,
                        "explanation": "Badania tego nie potwierdzają.",
                        "evidence": [
                            {
                                "quote": "Brak związku.",
                                "publisher": "NIZP PZH",
                                "url": "https://www.pzh.gov.pl/",
                            }
                        ],
                    }
                ],
            },
        },
    }


class FakeStore:
    def __init__(self) -> None:
        self.results: dict[UUID, str] = {}
        self.reports: dict[UUID, tuple[str, str | None]] = {}

    async def health_check(self) -> None:
        return None

    async def record_result(self, result_id: UUID, input_type: str) -> None:
        self.results[result_id] = input_type

    async def save_report(self, result_id: UUID, reason: str, comment: str | None) -> bool:
        if result_id not in self.results:
            return False
        self.reports.setdefault(result_id, (reason, comment))
        return True

    async def close(self) -> None:
        return None


@pytest.fixture
def client():
    store = FakeStore()

    async def runner(text: str) -> dict:
        return report()

    async def validator(url: str) -> str:
        if "localhost" in url:
            from api_routes import ApiFailure

            raise ApiFailure(422, "unsafe_url", "The website address is not publicly accessible.")
        return url

    app = create_app(store=store, verification_runner=runner, url_validator=validator)
    with TestClient(app) as test_client:
        yield test_client, store


def test_check_and_report_round_trip(client):
    test_client, store = client
    response = test_client.get("/api/check", params={"text": "Szczepionki powodują autyzm."})
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "result" and body["input_type"] == "text"
    assert body["claims"][0]["verdict"] == "false"
    assert body["claims"][0]["sources"][0]["publisher"] == "NIZP PZH"
    assert response.headers["cache-control"] == "no-store"

    sent = test_client.post(f"/api/check/{body['id']}/report", json={"reason": "bad_source"})
    assert sent.status_code == 204
    assert store.reports[UUID(body["id"])] == ("bad_source", None)


def test_errors_have_code_for_the_frontend(client):
    test_client, _ = client
    unsafe = test_client.get("/api/check", params={"text": "http://localhost/admin"})
    assert unsafe.status_code == 422
    assert unsafe.json()["error"]["code"] == "unsafe_url"

    mixed = test_client.get(
        "/api/check", params={"text": "https://example.org i jeszcze komentarz"}
    )
    assert mixed.json()["error"]["code"] == "invalid_url"

    missing = test_client.post(
        "/api/check/00000000-0000-0000-0000-000000000000/report", json={"reason": "other"}
    )
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "result_not_found"


def test_health(client):
    test_client, _ = client
    assert test_client.get("/api/health").json() == {"status": "ok"}


def test_trusted_sources_are_read_only_and_public_fields_only(client):
    test_client, _ = client
    listed = test_client.get("/api/trusted-sources")
    assert listed.status_code == 200
    sources = listed.json()
    assert sources, "the code whitelist is never empty"
    assert set(sources[0]) == {"id", "name", "url", "trust", "topics", "description"}

    one = test_client.get(f"/api/trusted-sources/{sources[0]['id']}")
    assert one.status_code == 200 and one.json()["id"] == sources[0]["id"]
    assert test_client.get("/api/trusted-sources/nie-ma-takiego").status_code == 404

    # detection and search call remote sites and the LLM: not on the public API
    assert test_client.post("/api/trusted-sources/search", json={"text": "x"}).status_code in (
        404,
        405,
    )
    assert test_client.post(f"/api/trusted-sources/{sources[0]['id']}/check").status_code in (
        404,
        405,
    )


def test_feedback_migration_is_shared_and_idempotent():
    path = Path(api_store.MIGRATION_PATH)
    assert path.is_file()
    assert any(
        m.name == "api_feedback" and m.sql == path.read_text(encoding="utf-8") for m in discover()
    )
    sql = path.read_text(encoding="utf-8")
    assert sql.count("CREATE TABLE IF NOT EXISTS") == 2
    assert "CREATE TABLE api" not in sql
