"""Illustrative client for an API returning a ``data`` collection."""

from datetime import UTC, datetime
from typing import Any

import httpx

from ..base import BaseApiClient, RequestSpec
from ..exceptions import ApiResponseError, InvalidFiltersError
from ..models import FetchResult, Item


class ExampleBClient(BaseApiClient):
    """Example client; replace the URL and mapping with a real API contract."""

    name = "example_b"
    base_url = "https://api.example-b.invalid"

    def build_request(self, filters: dict[str, Any]) -> RequestSpec:
        allowed = {"query", "limit"}
        if set(filters) - allowed:
            raise InvalidFiltersError(self.name, "unsupported filter")

        limit = filters.get("limit", 100)
        if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 1000:
            raise InvalidFiltersError(self.name, "limit must be an integer from 1 to 1000")
        query = filters.get("query")
        if query is not None and not isinstance(query, str):
            raise InvalidFiltersError(self.name, "query must be a string")

        headers = {"X-Api-Key": self.api_key} if self.api_key else None
        return RequestSpec(
            "GET",
            "/records",
            params={key: filters[key] for key in ("query", "limit") if key in filters},
            headers=headers,
        )

    def parse_response(self, response: httpx.Response) -> FetchResult:
        payload = response.json()
        if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
            raise ApiResponseError(self.name, "expected a data list")

        items = [
            Item(id=str(item["id"]), source=self.name, payload=item)
            for item in payload["data"]
            if isinstance(item, dict) and "id" in item
        ]
        if len(items) != len(payload["data"]):
            raise ApiResponseError(self.name, "one or more records are missing an id")

        return FetchResult(
            source=self.name,
            items=items,
            fetched_at=datetime.now(UTC),
            total=payload.get("total"),
            next_cursor=payload.get("next_cursor"),
        )
