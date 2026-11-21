"""Keyless title search client for the EUR-Lex Cellar SPARQL endpoint."""

import re
from datetime import UTC, datetime
from typing import Any, ClassVar
from urllib.parse import quote

import httpx

from ..base import BaseApiClient, RequestSpec
from ..exceptions import ApiResponseError, InvalidFiltersError
from ..models import Category, FetchResult, Item, ReadingRequest


class EurLexClient(BaseApiClient):
    """Search EUR-Lex legal acts through the public Cellar SPARQL endpoint."""

    name = "eurlex"
    base_url = "https://publications.europa.eu/webapi/rdf/sparql"
    supported_categories: ClassVar[frozenset[Category]] = frozenset({Category.LEGAL_ACT})
    requires_api_key = False
    max_page_size: ClassVar[int] = 100
    max_query_length: ClassVar[int] = 500

    def filters_from_request(self, request: ReadingRequest) -> dict[str, Any]:
        """Map shared query, language, and pagination fields to this client's filters."""

        filters: dict[str, Any] = {
            "query": request.query,
            "page_size": request.page_size,
        }
        if request.language_code is not None:
            filters["language_code"] = request.language_code
        return filters

    def build_request(self, filters: dict[str, Any]) -> RequestSpec:
        allowed = {"query", "language_code", "page_size", "page_token"}
        if set(filters) - allowed:
            raise InvalidFiltersError(self.name, "unsupported filter")

        query_text = filters.get("query")
        if not isinstance(query_text, str) or not query_text.strip():
            raise InvalidFiltersError(self.name, "query must be a non-empty string")
        query_text = query_text.strip()
        if len(query_text) > self.max_query_length:
            raise InvalidFiltersError(
                self.name,
                f"query must be at most {self.max_query_length} characters",
            )

        language_code = filters.get("language_code")
        if language_code is not None:
            if not isinstance(language_code, str) or not re.fullmatch(
                r"[A-Za-z]{2,8}(?:-[A-Za-z0-9]{1,8})*", language_code
            ):
                raise InvalidFiltersError(self.name, "language_code must be a valid language tag")
            language_code = language_code.lower()

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

        page_token = filters.get("page_token")
        if page_token is None:
            offset = 0
        elif not isinstance(page_token, str) or not page_token.isdecimal() or len(page_token) > 10:
            raise InvalidFiltersError(self.name, "page_token must be a non-negative offset")
        else:
            offset = int(page_token)
            if offset > 2_147_483_647:
                raise InvalidFiltersError(self.name, "page_token offset is too large")

        sparql_query = _build_sparql_query(query_text, language_code, page_size, offset)
        return RequestSpec(
            "GET",
            "",
            params={
                "query": sparql_query,
                "format": "application/sparql-results+json",
            },
            headers={"Accept": "application/sparql-results+json"},
        )

    def parse_response(self, response: httpx.Response) -> FetchResult:
        try:
            payload = response.json()
        except (ValueError, httpx.HTTPError) as exc:
            raise ApiResponseError(self.name, "expected valid SPARQL JSON", cause=exc) from exc

        if not isinstance(payload, dict):
            raise ApiResponseError(self.name, "expected a SPARQL results object")
        head = payload.get("head")
        results = payload.get("results")
        if not isinstance(head, dict) or not isinstance(results, dict):
            raise ApiResponseError(self.name, "expected SPARQL head and results objects")
        variables = head.get("vars")
        bindings = results.get("bindings")
        if (
            not isinstance(variables, list)
            or any(not isinstance(variable, str) for variable in variables)
            or not isinstance(bindings, list)
            or not {"celex", "title", "docType", "date"}.issubset(variables)
        ):
            raise ApiResponseError(self.name, "expected SPARQL vars and bindings lists")

        items: list[Item] = []
        for row in bindings:
            if not isinstance(row, dict) or any(
                not isinstance(key, str) or key not in variables for key in row
            ):
                raise ApiResponseError(self.name, "SPARQL binding rows must be objects")
            for variable, binding in row.items():
                _binding_value(binding, variable)
            values: dict[str, str | None] = {}
            for variable in ("celex", "title", "docType", "date"):
                values[variable] = (
                    _binding_value(row[variable], variable) if variable in row else None
                )

            celex = values["celex"]
            title = values["title"]
            if not celex or not title:
                raise ApiResponseError(self.name, "SPARQL rows require non-empty celex and title")

            items.append(
                Item(
                    id=f"eurlex_{celex}",
                    source=self.name,
                    payload={
                        "celex": celex,
                        "title": title,
                        "doc_type": values["docType"],
                        "date": values["date"],
                        "in_force": None,
                        "url_eurlex": (
                            "https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:"
                            f"{quote(celex, safe='')}"
                        ),
                    },
                )
            )

        limit = _query_limit(response)
        next_cursor = str(limit[1] + limit[0]) if limit and len(items) == limit[0] else None
        return FetchResult(
            source=self.name,
            items=items,
            fetched_at=datetime.now(UTC),
            next_cursor=next_cursor,
        )


def _build_sparql_query(
    query_text: str,
    language_code: str | None,
    page_size: int,
    offset: int,
) -> str:
    filters = [f"FILTER(CONTAINS(LCASE(STR(?title)), LCASE({_sparql_literal(query_text)})))"]
    if language_code is not None:
        filters.append(f"FILTER(LANG(?title) = {_sparql_literal(language_code)})")

    return "\n".join(
        [
            "PREFIX cdm: <http://publications.europa.eu/ontology/cdm#>",
            "SELECT DISTINCT ?celex ?title ?docType ?date WHERE {",
            "  ?work cdm:resource_legal_id_celex ?celex .",
            "  ?work cdm:work_title ?title .",
            "  OPTIONAL { ?work cdm:work_date_document ?date . }",
            "  OPTIONAL { ?work cdm:work_has_resource-type ?docType . }",
            *(f"  {filter_clause}" for filter_clause in filters),
            "}",
            f"LIMIT {page_size}",
            f"OFFSET {offset}",
        ]
    )


def _sparql_literal(value: str) -> str:
    """Encode arbitrary input as a SPARQL double-quoted string literal."""

    escaped: list[str] = []
    for character in value:
        codepoint = ord(character)
        if character == "\\":
            escaped.append("\\\\")
        elif character == '"':
            escaped.append('\\"')
        elif character == "\n":
            escaped.append("\\n")
        elif character == "\r":
            escaped.append("\\r")
        elif character == "\t":
            escaped.append("\\t")
        elif codepoint < 0x20 or 0x7F <= codepoint <= 0x9F:
            escaped.append(f"\\u{codepoint:04X}")
        else:
            escaped.append(character)
    return f'"{"".join(escaped)}"'


def _binding_value(binding: Any, variable: str) -> str:
    if not isinstance(binding, dict):
        raise ApiResponseError(EurLexClient.name, f"invalid {variable} binding")
    if set(binding) - {"type", "value", "datatype", "xml:lang", "lang"}:
        raise ApiResponseError(EurLexClient.name, f"invalid {variable} binding")
    binding_type = binding.get("type")
    value = binding.get("value")
    if (
        not isinstance(binding_type, str)
        or binding_type not in {"uri", "literal", "typed-literal", "bnode"}
        or not isinstance(value, str)
    ):
        raise ApiResponseError(EurLexClient.name, f"invalid {variable} binding")
    for metadata_key in ("datatype", "xml:lang", "lang"):
        metadata_value = binding.get(metadata_key)
        if metadata_value is not None and not isinstance(metadata_value, str):
            raise ApiResponseError(EurLexClient.name, f"invalid {variable} binding")
    return value


def _query_limit(response: httpx.Response) -> tuple[int, int] | None:
    """Read pagination details attached by request construction when available."""

    try:
        request = response.request
    except RuntimeError:
        return None
    if request is None:
        return None
    query = request.url.params.get("query", "")
    limits = re.findall(r"\bLIMIT\s+(\d+)\b", query, re.IGNORECASE)
    offsets = re.findall(r"\bOFFSET\s+(\d+)\b", query, re.IGNORECASE)
    if not limits or not offsets:
        return None
    return int(limits[-1]), int(offsets[-1])
