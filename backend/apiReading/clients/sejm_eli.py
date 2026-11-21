"""Client for Polish legal acts in Sejm's ELI API (including ISAP links)."""

from datetime import UTC, date, datetime, timedelta
from typing import Any, ClassVar

import httpx

from ..base import BaseApiClient, RequestSpec
from ..exceptions import ApiResponseError, InvalidFiltersError
from ..models import Category, FetchResult, Item, ReadingRequest
from ._polish_legal import normalize_eli_date, parse_act_reference


class SejmEliClient(BaseApiClient):
    """Search Polish legal acts and resolve common Dz.U./M.P. references."""

    name = "sejm_eli"
    base_url = "https://api.sejm.gov.pl"
    supported_categories: ClassVar[frozenset[Category]] = frozenset({Category.LEGAL_ACT})
    requires_api_key = False
    max_page_size: ClassVar[int] = 20
    max_query_length: ClassVar[int] = 300
    max_offset: ClassVar[int] = 2_147_483_647

    def filters_from_request(self, request: ReadingRequest) -> dict[str, Any]:
        """Map a shared request to title search filters."""

        filters: dict[str, Any] = {"query": request.query, "page_size": request.page_size}
        if request.max_age_days is not None:
            filters["max_age_days"] = request.max_age_days
        return filters

    def build_request(self, filters: dict[str, Any]) -> RequestSpec:
        """Build either a precise act-reference lookup or one title-search page."""

        allowed = {"query", "page_size", "page_token", "max_age_days"}
        if set(filters) - allowed:
            raise InvalidFiltersError(self.name, "unsupported filter")

        query = filters.get("query")
        if not isinstance(query, str) or not query.strip():
            raise InvalidFiltersError(self.name, "query must be a non-empty string")
        query = query.strip()
        if len(query) > self.max_query_length:
            raise InvalidFiltersError(
                self.name,
                f"query must be at most {self.max_query_length} characters",
            )

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
        offset = _offset(filters.get("page_token"), self.name)
        max_age_days = filters.get("max_age_days")
        if max_age_days is not None and (
            not isinstance(max_age_days, int)
            or isinstance(max_age_days, bool)
            or not 1 <= max_age_days <= 2_147_483_647
        ):
            raise InvalidFiltersError(self.name, "max_age_days must be a positive integer")

        reference = parse_act_reference(query)
        if reference is not None:
            publisher, year, position = reference
            return RequestSpec("GET", f"/eli/acts/{publisher}/{year}/{position}")

        params: dict[str, Any] = {"title": query, "limit": page_size, "offset": offset}
        if max_age_days is not None:
            params["dateFrom"] = (date.today() - timedelta(days=max_age_days)).isoformat()
        return RequestSpec("GET", "/eli/acts/search", params=params)

    def parse_response(self, response: httpx.Response) -> FetchResult:
        """Validate and normalize a detail response or a search-results page."""

        payload = response.json()
        path_parts = response.request.url.path.strip("/").split("/")
        is_detail = (
            len(path_parts) == 5
            and path_parts[:2] == ["eli", "acts"]
            and path_parts[2] in {"DU", "MP"}
            and path_parts[3].isdecimal()
            and path_parts[4].isdecimal()
        )
        if is_detail:
            if not isinstance(payload, dict):
                raise ApiResponseError(self.name, "expected a legal act object")
            raw_items = [payload]
            total = 1
            next_cursor = None
        else:
            if not isinstance(payload, dict) or not isinstance(payload.get("items"), list):
                raise ApiResponseError(self.name, "expected a legal act search response")
            raw_items = payload["items"]
            total = _total_count(payload, self.name)
            offset = _response_offset(response)
            page_size = _response_limit(response)
            next_cursor = None
            has_next_page = (total is not None and offset + len(raw_items) < total) or (
                total is None and len(raw_items) == page_size
            )
            if has_next_page:
                next_cursor = str(offset + len(raw_items))

        items = [self._normalize_act(raw_item) for raw_item in raw_items]
        return FetchResult(
            source=self.name,
            items=items,
            fetched_at=datetime.now(UTC),
            total=total,
            next_cursor=next_cursor,
        )

    def _normalize_act(self, act: Any) -> Item:
        if not isinstance(act, dict):
            raise ApiResponseError(self.name, "legal act entries must be objects")

        publisher = act.get("publisher")
        year = act.get("year")
        position = act.get("pos")
        title = act.get("title")
        if not isinstance(publisher, str) or not publisher.strip():
            raise ApiResponseError(self.name, "legal act publisher must be a non-empty string")
        if not _is_integer(year) or year < 1:
            raise ApiResponseError(self.name, "legal act year must be a positive integer")
        if not _is_integer(position) or position < 1:
            raise ApiResponseError(self.name, "legal act position must be a positive integer")
        if not isinstance(title, str) or not title.strip():
            raise ApiResponseError(self.name, "legal act title must be a non-empty string")

        address = _optional_string(act, "address", self.name)
        eli_id = _optional_string(act, "ELI", self.name) or f"{publisher}/{year}/{position}"
        text_html = _optional_bool(act, "textHTML", self.name)
        text_pdf = _optional_bool(act, "textPDF", self.name)
        try:
            promulgation_date = normalize_eli_date(_optional_string(act, "promulgation", self.name))
            announcement_date = normalize_eli_date(
                _optional_string(act, "announcementDate", self.name)
            )
            change_date = normalize_eli_date(_optional_string(act, "changeDate", self.name))
        except ValueError as exc:
            raise ApiResponseError(
                self.name, "legal act contains an invalid date", cause=exc
            ) from exc

        return Item(
            id=f"eli_{publisher.lower()}_{year}_{position}",
            source=self.name,
            payload={
                "title": title,
                "act_type": _optional_string(act, "type", self.name),
                "publisher": publisher,
                "year": year,
                "position": position,
                "eli_id": eli_id,
                "display_address": _optional_string(act, "displayAddress", self.name),
                "status": _optional_string(act, "status", self.name),
                "promulgation_date": promulgation_date,
                "announcement_date": announcement_date,
                "change_date": change_date,
                "url_isap": (
                    f"https://isap.sejm.gov.pl/isap.nsf/DocDetails.xsp?id={address}"
                    if address
                    else None
                ),
                "url_text_html": (
                    f"{self.base_url}/eli/acts/{publisher}/{year}/{position}/text.html"
                    if text_html
                    else None
                ),
                "url_text_pdf": (
                    f"{self.base_url}/eli/acts/{publisher}/{year}/{position}/text.pdf"
                    if text_pdf
                    else None
                ),
                "source_name": "Sejm ELI / ISAP",
            },
        )


def _offset(value: Any, source: str) -> int:
    if value is None:
        return 0
    if not isinstance(value, str) or not value.isdecimal() or len(value) > 10:
        raise InvalidFiltersError(source, "page_token must be a non-negative offset")
    offset = int(value)
    if offset > 2_147_483_647:
        raise InvalidFiltersError(source, "page_token offset is too large")
    return offset


def _is_integer(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _optional_string(payload: dict[str, Any], key: str, source: str) -> str | None:
    value = payload.get(key)
    if value is not None and not isinstance(value, str):
        raise ApiResponseError(source, f"{key} must be a string or null")
    return value


def _optional_bool(payload: dict[str, Any], key: str, source: str) -> bool | None:
    value = payload.get(key)
    if value is not None and not isinstance(value, bool):
        raise ApiResponseError(source, f"{key} must be a boolean or null")
    return value


def _total_count(payload: dict[str, Any], source: str) -> int | None:
    value = payload.get("totalCount", payload.get("count"))
    if value is not None and (not _is_integer(value) or value < 0):
        raise ApiResponseError(source, "totalCount must be a non-negative integer")
    return value


def _response_offset(response: httpx.Response) -> int:
    value = response.request.url.params.get("offset", "0")
    return int(value) if value.isdecimal() else 0


def _response_limit(response: httpx.Response) -> int:
    value = response.request.url.params.get("limit", "10")
    return int(value) if value.isdecimal() else 10
