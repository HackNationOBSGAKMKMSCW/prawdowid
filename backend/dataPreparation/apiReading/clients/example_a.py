"""Illustrative client for an API returning an ``items`` collection."""

from datetime import UTC, datetime
from typing import Any

import httpx

from ..base import BaseApiClient, RequestSpec
from ..exceptions import ApiResponseError, InvalidFiltersError
from ..models import FetchResult, Item


class ExampleAClient(BaseApiClient):
    """Example client; replace the URL and mapping with a real API contract."""

    name = "example_a"
    base_url = "https://api.example-a.invalid"

    def build_request(self, filters: dict[str, Any]) -> RequestSpec:
        allowed = {"category", "page"}
        unknown = set(filters) - allowed
        if unknown:
            raise InvalidFiltersError(self.name, "unsupported filter")

        page = filters.get("page", 1)
        if not isinstance(page, int) or isinstance(page, bool) or page < 1:
            raise InvalidFiltersError(self.name, "page must be a positive integer")
        category = filters.get("category")
        if category is not None and not isinstance(category, str):
            raise InvalidFiltersError(self.name, "category must be a string")

        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else None
        return RequestSpec(
            "GET",
            "/items",
            params={key: filters[key] for key in ("category", "page") if key in filters},
            headers=headers,
        )

    def parse_response(self, response: httpx.Response) -> FetchResult:
        payload = response.json()
        if not isinstance(payload, dict) or not isinstance(payload.get("items"), list):
            raise ApiResponseError(self.name, "expected an items list")

        items = [
            Item(id=str(item["id"]), source=self.name, payload=item)
            for item in payload["items"]
            if isinstance(item, dict) and "id" in item
        ]
        if len(items) != len(payload["items"]):
            raise ApiResponseError(self.name, "one or more items are missing an id")

        return FetchResult(
            source=self.name,
            items=items,
            fetched_at=datetime.now(UTC),
            total=payload.get("total"),
            next_cursor=payload.get("next_cursor"),
        )
