"""Client for searching datasets in the dane.gov.pl catalogue."""

from datetime import UTC, datetime
from typing import Any, ClassVar
from urllib.parse import parse_qs, urlparse

import httpx

from ..base import BaseApiClient, RequestSpec
from ..exceptions import ApiResponseError, InvalidFiltersError
from ..models import Category, FetchResult, Item, ReadingRequest


class DaneGovClient(BaseApiClient):
    """Search public datasets without requiring an API key."""

    name = "dane_gov"
    base_url = "https://api.dane.gov.pl"
    supported_categories: ClassVar[frozenset[Category]] = frozenset({Category.OPEN_DATA})
    requires_api_key: ClassVar[bool] = False
    max_page_size: ClassVar[int] = 100

    def filters_from_request(self, request: ReadingRequest) -> dict[str, Any]:
        """Translate the shared request fields to dataset-search filters."""

        return {"query": request.query, "page_size": request.page_size}

    def build_request(self, filters: dict[str, Any]) -> RequestSpec:
        """Validate supported filters and build one paginated search request."""

        allowed = {"query", "page_size", "page_token"}
        if set(filters) - allowed:
            raise InvalidFiltersError(self.name, "unsupported filter")

        query = filters.get("query")
        if not isinstance(query, str) or not query.strip():
            raise InvalidFiltersError(self.name, "query must be a non-empty string")

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

        page = _page_number(filters.get("page_token", "1"), self.name)
        return RequestSpec(
            "GET",
            "/datasets",
            params={"q": query.strip(), "page": page, "per_page": page_size},
        )

    def parse_response(self, response: httpx.Response) -> FetchResult:
        """Validate the JSON:API response and flatten dataset metadata."""

        payload = response.json()
        if not isinstance(payload, dict):
            raise ApiResponseError(self.name, "expected a dataset search response object")

        rows = payload.get("data")
        if not isinstance(rows, list):
            raise ApiResponseError(self.name, "expected data to be a list")

        included = _included_resources(payload.get("included", []))
        items = [self._parse_dataset(row, included) for row in rows]
        next_cursor = _next_cursor(payload, self.name)
        return FetchResult(
            source=self.name,
            items=items,
            fetched_at=datetime.now(UTC),
            total=_total_count(payload, self.name),
            next_cursor=next_cursor,
        )

    def _parse_dataset(
        self,
        row: Any,
        included: dict[tuple[str, str], dict[str, Any]],
    ) -> Item:
        if not isinstance(row, dict):
            raise ApiResponseError(self.name, "dataset entries must be objects")

        dataset_id = row.get("id")
        attributes = row.get("attributes")
        relationships = row.get("relationships")
        if not isinstance(dataset_id, str) or not dataset_id.strip():
            raise ApiResponseError(self.name, "dataset id must be a non-empty string")
        if not isinstance(attributes, dict):
            raise ApiResponseError(self.name, "dataset attributes must be an object")
        if not isinstance(relationships, dict):
            raise ApiResponseError(self.name, "dataset relationships must be an object")

        title = attributes.get("title")
        if not isinstance(title, str) or not title.strip():
            raise ApiResponseError(self.name, "dataset title must be a non-empty string")

        notes = _optional_string(attributes, "notes", self.name)
        url = _optional_string(attributes, "url", self.name)
        modified = _optional_string(attributes, "modified", self.name)
        if modified is None:
            modified = _optional_string(attributes, "updated_at", self.name)
        resources_count = _resource_count(attributes, relationships, self.name)
        institution = _institution(attributes, relationships, included, self.name)

        return Item(
            id=dataset_id,
            source=self.name,
            payload={
                "title": title,
                "notes": notes,
                "institution": institution,
                "url": url,
                "modified": modified,
                "resources_count": resources_count,
            },
        )


def _page_number(value: Any, source: str) -> int:
    if not isinstance(value, str) or not value.isdecimal() or int(value) < 1:
        raise InvalidFiltersError(source, "page_token must be a positive numeric string")
    return int(value)


def _optional_string(attributes: dict[str, Any], key: str, source: str) -> str | None:
    value = attributes.get(key)
    if value is not None and not isinstance(value, str):
        raise ApiResponseError(source, f"dataset {key} must be a string or null")
    return value


def _included_resources(value: Any) -> dict[tuple[str, str], dict[str, Any]]:
    if not isinstance(value, list):
        raise ApiResponseError("dane_gov", "included must be a list")

    resources: dict[tuple[str, str], dict[str, Any]] = {}
    for resource in value:
        if not isinstance(resource, dict):
            raise ApiResponseError("dane_gov", "included resources must be objects")
        resource_id = resource.get("id")
        resource_type = resource.get("type")
        attributes = resource.get("attributes")
        if (
            not isinstance(resource_id, str)
            or not isinstance(resource_type, str)
            or not isinstance(attributes, dict)
        ):
            raise ApiResponseError(
                "dane_gov", "included resources require id, type, and attributes"
            )
        resources[(resource_type, resource_id)] = attributes
    return resources


def _institution(
    attributes: dict[str, Any],
    relationships: dict[str, Any],
    included: dict[tuple[str, str], dict[str, Any]],
    source: str,
) -> str | None:
    direct_value = attributes.get("institution")
    if direct_value is not None:
        if not isinstance(direct_value, str):
            raise ApiResponseError(source, "dataset institution must be a string or null")
        return direct_value

    relationship = relationships.get("institution")
    if relationship is None:
        return None
    if not isinstance(relationship, dict):
        raise ApiResponseError(source, "institution relationship must be an object")
    linkage = relationship.get("data")
    if linkage is None:
        return None
    if not isinstance(linkage, dict):
        raise ApiResponseError(source, "institution relationship data must be an object or null")

    institution_id = linkage.get("id")
    institution_type = linkage.get("type")
    if not isinstance(institution_id, str) or not isinstance(institution_type, str):
        raise ApiResponseError(source, "institution relationship data requires id and type")
    institution_attributes = included.get((institution_type, institution_id))
    if institution_attributes is None:
        return institution_id

    name = institution_attributes.get("name", institution_attributes.get("title"))
    if name is not None and not isinstance(name, str):
        raise ApiResponseError(source, "included institution name must be a string or null")
    return name or institution_id


def _resource_count(
    attributes: dict[str, Any],
    relationships: dict[str, Any],
    source: str,
) -> int | None:
    value = attributes.get("resources_count")
    if value is None:
        resources = relationships.get("resources")
        if resources is not None:
            if not isinstance(resources, dict):
                raise ApiResponseError(source, "resources relationship must be an object")
            metadata = resources.get("meta", {})
            if not isinstance(metadata, dict):
                raise ApiResponseError(source, "resources relationship meta must be an object")
            value = metadata.get("count")
    if value is not None and (not isinstance(value, int) or isinstance(value, bool) or value < 0):
        raise ApiResponseError(source, "dataset resources_count must be a non-negative integer")
    return value


def _next_cursor(payload: dict[str, Any], source: str) -> str | None:
    links = payload.get("links", {})
    if not isinstance(links, dict):
        raise ApiResponseError(source, "links must be an object")
    next_link = links.get("next")
    if next_link is not None:
        if not isinstance(next_link, str):
            raise ApiResponseError(source, "links.next must be a URL string or null")
        page_values = parse_qs(urlparse(next_link).query).get("page")
        if not page_values:
            raise ApiResponseError(source, "links.next must include a numeric page")
        return str(_response_page(page_values[0], source))

    meta = payload.get("meta", {})
    if not isinstance(meta, dict):
        raise ApiResponseError(source, "meta must be an object")
    pagination = meta.get("pagination", meta)
    if not isinstance(pagination, dict):
        raise ApiResponseError(source, "pagination metadata must be an object")

    next_page = pagination.get("next_page")
    if next_page is not None:
        return str(_response_page(next_page, source))

    current_page = pagination.get("page", pagination.get("current_page"))
    page_count = pagination.get(
        "page_count",
        pagination.get("total_pages", pagination.get("pages")),
    )
    if current_page is None or page_count is None:
        return None
    current_page = _response_page(current_page, source)
    page_count = _response_page(page_count, source)
    if current_page < page_count:
        return str(current_page + 1)
    return None


def _response_page(value: Any, source: str) -> int:
    if isinstance(value, bool):
        raise ApiResponseError(source, "pagination page must be a positive integer")
    if isinstance(value, str) and value.isdecimal():
        value = int(value)
    if not isinstance(value, int) or value < 1:
        raise ApiResponseError(source, "pagination page must be a positive integer")
    return value


def _total_count(payload: dict[str, Any], source: str) -> int | None:
    meta = payload.get("meta", {})
    if not isinstance(meta, dict):
        raise ApiResponseError(source, "meta must be an object")
    pagination = meta.get("pagination", meta)
    if not isinstance(pagination, dict):
        raise ApiResponseError(source, "pagination metadata must be an object")
    value = pagination.get("total", meta.get("count"))
    if value is None:
        return None
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ApiResponseError(source, "total must be a non-negative integer")
    return value
