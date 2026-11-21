"""Client for Sejm legislative-process search."""

from datetime import UTC, datetime
from typing import Any, ClassVar

import httpx

from ..base import BaseApiClient, RequestSpec
from ..exceptions import ApiResponseError, InvalidFiltersError
from ..models import Category, FetchResult, Item, ReadingRequest


class SejmApiClient(BaseApiClient):
    """Search legislative processes from the keyless Sejm API."""

    name = "sejm"
    base_url = "https://api.sejm.gov.pl"
    supported_categories: ClassVar[frozenset[Category]] = frozenset({Category.LEGISLATIVE_PROCESS})
    requires_api_key = False
    default_term: ClassVar[int] = 10
    default_limit: ClassVar[int] = 10
    max_limit: ClassVar[int] = 100
    max_offset: ClassVar[int] = 2_147_483_647

    def filters_from_request(self, request: ReadingRequest) -> dict[str, Any]:
        """Map the shared query and page size to Sejm's search vocabulary."""

        return {"query": request.query, "limit": request.page_size}

    def build_request(self, filters: dict[str, Any]) -> RequestSpec:
        """Validate filters and build one paginated process search request."""

        allowed = {"query", "term", "limit", "offset", "page_token"}
        if set(filters) - allowed:
            raise InvalidFiltersError(self.name, "unsupported filter")

        query = _optional_nonempty_string(filters, "query")
        if query is None:
            raise InvalidFiltersError(self.name, "query is required")

        term = filters.get("term", self.default_term)
        if not _is_integer(term) or not 1 <= term <= 99:
            raise InvalidFiltersError(self.name, "term must be an integer from 1 to 99")

        limit = filters.get("limit", self.default_limit)
        if not _is_integer(limit) or not 1 <= limit <= self.max_limit:
            raise InvalidFiltersError(
                self.name,
                f"limit must be an integer from 1 to {self.max_limit}",
            )

        offset = filters.get("offset", 0)
        page_token = filters.get("page_token")
        if page_token is not None:
            if "offset" in filters:
                raise InvalidFiltersError(self.name, "offset and page_token cannot be combined")
            if not isinstance(page_token, str) or not page_token.isdecimal():
                raise InvalidFiltersError(self.name, "page_token must be a non-negative offset")
            offset = int(page_token)
        if not _is_integer(offset) or not 0 <= offset <= self.max_offset:
            raise InvalidFiltersError(
                self.name,
                f"offset must be an integer from 0 to {self.max_offset}",
            )

        return RequestSpec(
            "GET",
            f"/sejm/term{term}/processes",
            params={"title": query, "limit": limit, "offset": offset},
        )

    def parse_response(self, response: httpx.Response) -> FetchResult:
        """Normalize one Sejm result page and expose its next offset cursor."""

        payload = response.json()
        if not isinstance(payload, list):
            raise ApiResponseError(self.name, "expected a list of legislative processes")

        request = response.request
        term = self.default_term
        path_parts = request.url.path.rstrip("/").split("/")
        if len(path_parts) >= 3 and path_parts[-2].startswith("term"):
            term = int(path_parts[-2][4:])

        items: list[Item] = []
        for process in payload:
            if not isinstance(process, dict):
                raise ApiResponseError(self.name, "process entries must be objects")

            number = process.get("number")
            title = process.get("title")
            if not isinstance(number, str) or not number.strip():
                raise ApiResponseError(self.name, "process number must be a non-empty string")
            if not isinstance(title, str) or not title.strip():
                raise ApiResponseError(self.name, "process title must be a non-empty string")

            print_numbers = process.get("printsConsideredJointly", [])
            if not isinstance(print_numbers, list) or any(
                not isinstance(print_number, str) for print_number in print_numbers
            ):
                raise ApiResponseError(
                    self.name, "printsConsideredJointly must be a list of strings"
                )

            process_start_date = process.get("processStartDate")
            if process_start_date is not None and not isinstance(process_start_date, str):
                raise ApiResponseError(self.name, "processStartDate must be a string or null")

            passed = process.get("passed")
            if passed is not None and not isinstance(passed, bool):
                raise ApiResponseError(self.name, "passed must be a boolean or null")

            document_type = process.get("documentType")
            if document_type is not None and not isinstance(document_type, str):
                raise ApiResponseError(self.name, "documentType must be a string or null")

            urls = _normalize_urls(process.get("links", []), self.name)
            normalized = {
                "title": title,
                "number": number,
                "print_numbers": print_numbers,
                "process_start_date": process_start_date,
                "passed": passed,
                "document_type": document_type,
                "urls": urls,
            }
            items.append(
                Item(
                    id=f"sejm_{term}_{number}",
                    source=self.name,
                    payload=normalized,
                )
            )

        limit = _response_query_int(request, "limit", self.default_limit)
        offset = _response_query_int(request, "offset", 0)
        next_cursor = str(offset + len(items)) if len(items) == limit else None

        return FetchResult(
            source=self.name,
            items=items,
            fetched_at=datetime.now(UTC),
            next_cursor=next_cursor,
        )


def _optional_nonempty_string(filters: dict[str, Any], key: str) -> str | None:
    value = filters.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise InvalidFiltersError(SejmApiClient.name, f"{key} must be a non-empty string")
    return value.strip()


def _is_integer(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _normalize_urls(value: Any, source: str) -> dict[str, str]:
    if not isinstance(value, list):
        raise ApiResponseError(source, "links must be a list")

    urls: dict[str, str] = {}
    for link in value:
        if not isinstance(link, dict):
            raise ApiResponseError(source, "link entries must be objects")
        relation = link.get("rel")
        href = link.get("href")
        if not isinstance(relation, str) or not relation:
            raise ApiResponseError(source, "link rel must be a non-empty string")
        if not isinstance(href, str) or not href:
            raise ApiResponseError(source, "link href must be a non-empty string")
        urls[relation] = href
    return urls


def _response_query_int(response: httpx.Request, key: str, default: int) -> int:
    value = response.url.params.get(key)
    if value is None or not value.isdecimal():
        return default
    return int(value)
