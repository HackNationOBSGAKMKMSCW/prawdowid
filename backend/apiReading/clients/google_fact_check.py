"""Client for Google's Fact Check Tools claims search API."""

import hashlib
import json
from datetime import UTC, datetime
from typing import Any, ClassVar

import httpx

from ..base import BaseApiClient, RequestSpec
from ..exceptions import ApiResponseError, InvalidFiltersError
from ..models import Category, FetchResult, Item, ReadingRequest


class GoogleFactCheckClient(BaseApiClient):
    """Search published fact checks with Google's server-side claim search."""

    name = "google_fact_check"
    base_url = "https://factchecktools.googleapis.com"
    supported_categories: ClassVar[frozenset[Category]] = frozenset({Category.FACT_CHECK})
    max_page_size: ClassVar[int] = 20
    response_fields: ClassVar[str] = (
        "claims(text,claimant,claimDate,claimReview("
        "publisher(name,site),title,reviewDate,url,textualRating,languageCode)),"
        "nextPageToken"
    )

    def filters_from_request(self, request: ReadingRequest) -> dict[str, Any]:
        """Translate provider-neutral fields into Google's supported filters."""

        filters: dict[str, Any] = {
            "query": request.query,
            "page_size": request.page_size,
        }
        if request.language_code is not None:
            filters["language_code"] = request.language_code
        if request.max_age_days is not None:
            filters["max_age_days"] = request.max_age_days
        return filters

    def build_request(self, filters: dict[str, Any]) -> RequestSpec:
        allowed = {
            "query",
            "language_code",
            "review_publisher_site_filter",
            "max_age_days",
            "page_size",
            "page_token",
        }
        if set(filters) - allowed:
            raise InvalidFiltersError(self.name, "unsupported filter")

        query = _optional_nonempty_string(filters, "query")
        publisher_site = _optional_nonempty_string(filters, "review_publisher_site_filter")
        if query is None and publisher_site is None:
            raise InvalidFiltersError(
                self.name,
                "query or review_publisher_site_filter is required",
            )

        language_code = _optional_nonempty_string(filters, "language_code")
        page_token = _optional_nonempty_string(filters, "page_token")
        page_size = filters.get("page_size", 10)
        if (
            not isinstance(page_size, int)
            or isinstance(page_size, bool)
            or not 1 <= page_size <= self.max_page_size
        ):
            raise InvalidFiltersError(
                self.name,
                f"page_size must be an integer from 1 to {self.max_page_size}",
            )

        params: dict[str, Any] = {
            "pageSize": page_size,
            "fields": self.response_fields,
            "prettyPrint": "false",
        }
        if query is not None:
            params["query"] = query
        if publisher_site is not None:
            params["reviewPublisherSiteFilter"] = publisher_site
        if language_code is not None:
            params["languageCode"] = language_code
        if page_token is not None:
            params["pageToken"] = page_token

        max_age_days = filters.get("max_age_days")
        if max_age_days is not None:
            if (
                not isinstance(max_age_days, int)
                or isinstance(max_age_days, bool)
                or not 1 <= max_age_days <= 2_147_483_647
            ):
                raise InvalidFiltersError(self.name, "max_age_days must be a positive integer")
            params["maxAgeDays"] = max_age_days

        # Google requires an API key unless the injected HTTP client supplies OAuth.
        if self.api_key:
            params["key"] = self.api_key

        return RequestSpec("GET", "/v1alpha1/claims:search", params=params)

    def parse_response(self, response: httpx.Response) -> FetchResult:
        payload = response.json()
        if not isinstance(payload, dict):
            raise ApiResponseError(self.name, "expected a claims search response object")

        claims = payload.get("claims", [])
        next_page_token = payload.get("nextPageToken")
        if not isinstance(claims, list):
            raise ApiResponseError(self.name, "expected claims to be a list")
        if next_page_token is not None and not isinstance(next_page_token, str):
            raise ApiResponseError(self.name, "expected nextPageToken to be a string")

        items = []
        for claim in claims:
            if not isinstance(claim, dict):
                raise ApiResponseError(self.name, "claim entries must be objects")
            reviews = claim.get("claimReview", [])
            if reviews is not None and (
                not isinstance(reviews, list)
                or any(not isinstance(review, dict) for review in reviews)
            ):
                raise ApiResponseError(self.name, "claimReview entries must be objects")

            items.append(
                Item(
                    id=_claim_id(claim),
                    source=self.name,
                    payload=claim,
                )
            )

        return FetchResult(
            source=self.name,
            items=items,
            fetched_at=datetime.now(UTC),
            next_cursor=next_page_token or None,
        )


def _optional_nonempty_string(filters: dict[str, Any], key: str) -> str | None:
    value = filters.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise InvalidFiltersError("google_fact_check", f"{key} must be a non-empty string")
    return value.strip()


def _claim_id(claim: dict[str, Any]) -> str:
    """Create a stable ID because the API does not expose a claim resource ID."""

    serialized = json.dumps(claim, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    digest = hashlib.sha256(serialized.encode("utf-8")).hexdigest()[:24]
    return f"gfc_{digest}"
