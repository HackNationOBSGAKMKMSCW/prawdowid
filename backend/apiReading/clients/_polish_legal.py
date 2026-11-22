"""Shared parsing helpers for Polish legislation API clients."""

import re
from datetime import date, datetime
from html.parser import HTMLParser

_ACT_REFERENCE = re.compile(
    r"\b(?P<publisher>dz\.?\s*u\.?|dziennik\s+ustaw|m\.?\s*p\.?|monitor\s+polski)"
    r"(?:\s+z)?\s*(?P<year>\d{4})\s*(?:r\.?)?\s*"
    r"(?:poz\.?|pozycja)\s*(?P<position>\d+)\b",
    re.IGNORECASE,
)
_PUBLISHERS = {
    "dz.u.": "DU",
    "dziennikustaw": "DU",
    "m.p.": "MP",
    "monitorpolski": "MP",
}


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self.parts.append(data)


def parse_act_reference(query: str) -> tuple[str, int, int] | None:
    """Return ``(publisher, year, position)`` for a recognizable act citation."""

    match = _ACT_REFERENCE.search(query)
    if match is None:
        return None
    publisher_text = re.sub(r"\s+", "", match.group("publisher")).lower()
    publisher = _PUBLISHERS.get(publisher_text)
    if publisher is None:
        return None
    return publisher, int(match.group("year")), int(match.group("position"))


def normalize_eli_date(value: str | None) -> str | None:
    """Validate an ISO date or datetime and return its normalized ISO value."""

    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("date values must be strings or null")
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError:
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).isoformat()
        except ValueError as exc:
            raise ValueError("date values must be ISO formatted") from exc


def strip_html(value: str) -> str:
    """Strip tags and collapse whitespace from a small HTML fragment."""

    extractor = _TextExtractor()
    extractor.feed(value)
    return " ".join(" ".join(extractor.parts).split())
