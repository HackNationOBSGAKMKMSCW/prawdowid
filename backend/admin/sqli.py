"""Wykrywanie prób SQL injection w danych wejściowych (parametry URL, pola JSON, tekst).

Backend używa wyłącznie zapytań parametryzowanych, więc wykrycie **niczego nie blokuje**:
służy do powiadomienia admina (alert ``sql_injection`` w ``monitor_alerts``).

Heurystyka szuka składni SQL, a nie pojedynczych słów: „union select”, tautologii po
cudzysłowie (``' OR '1'='1``), zapytań doklejonych po średniku (``; DROP TABLE``), funkcji
opóźniających (``SLEEP(5)``), odwołań do katalogu bazy (``information_schema``) itp.
Wzorzec „silny” wystarcza sam; „słabe” (komentarz po cudzysłowie) liczą się dopiero razem.

Do alertu trafiają tylko nazwy wzorców i pól, nigdy wartość (mogłaby to być np. hasło).
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import parse_qsl, unquote_plus

_FLAGS = re.IGNORECASE | re.DOTALL

# Wzorce działają na tekście ze sklejonymi białymi znakami (każdy ciąg -> jedna spacja), więc
# zamiast ``\s*`` jest ``" ?"``: dopasowanie jest liniowe (bez katastrofalnego nawracania).
STRONG: dict[str, re.Pattern[str]] = {
    "union_select": re.compile(r"\bunion (?:(?:all|distinct) )?select\b", _FLAGS),
    # ' OR '1'='1   " or "a"="a   ') or (1=1   — zawsze po cudzysłowie/nawiasie
    "tautologia": re.compile(
        r"['\"`)] ?(?:or|and|\|\||&&) ?\(? ?['\"]?(\w{1,32})['\"]? ?(?:=|like) ?['\"]?\1\b",
        _FLAGS,
    ),
    # 1 or 1=1 --   (bez cudzysłowu: wymagany komentarz albo średnik na końcu)
    "tautologia_z_komentarzem": re.compile(
        r"\b(?:or|and) (\d{1,12}) ?= ?\1 ?(?:--|#|/\*|;)", _FLAGS
    ),
    # x'; DROP TABLE users   1; DELETE FROM t   — średnik po wartości i pełna składnia polecenia
    "zapytanie_doklejone": re.compile(
        r"['\"`)\d] ?; ?(?:(?:drop|truncate|alter|create) (?:table|database|schema|index|view"
        r"|user|procedure|function)\b|delete from\b|insert into\b|update \w{1,64} set\b"
        r"|exec(?:ute)? (?:xp_|sp_)\w*|shutdown\b|grant \w{1,32} on\b)",
        _FLAGS,
    ),
    "drop_table": re.compile(r"\bdrop (?:table|database|schema) (?:if exists )?[\w`\"\[]", _FLAGS),
    # SLEEP(5)  pg_sleep(5)  BENCHMARK(1000000,  WAITFOR DELAY '0:0:5' — bez spacji przed „(”
    "opoznienie": re.compile(
        r"\b(?:sleep|pg_sleep)\(\d{1,3}\)|\bbenchmark\(\d{3,},|\bwaitfor delay '\d", _FLAGS
    ),
    "katalog_bazy": re.compile(
        r"\b(?:information_schema|pg_catalog|sqlite_master|sysobjects|mysql\.user)\b", _FLAGS
    ),
    "procedura_systemowa": re.compile(
        r"\bxp_cmdshell\b|\bload_file ?\(|\binto (?:out|dump)file\b", _FLAGS
    ),
}
WEAK: dict[str, re.Pattern[str]] = {
    # admin'--   admin'#   (komentarz kończący wartość, nie hashtag "#crypto)
    "komentarz_po_cudzyslowie": re.compile(r"['\"] ?(?:--|#|/\*)(?= |$)", _FLAGS),
    "select_from": re.compile(r"\bselect\b[ \w*,().`\"]{1,80}\bfrom \w", _FLAGS),
    "char_kody": re.compile(r"\b(?:char|chr)\(\d{2,3}(?:, ?\d{2,3})+\)", _FLAGS),
}
# Komentarze inline krótkie (ograniczona długość = liniowo także przy wielu „/*”).
_INLINE_COMMENT = re.compile(r"/\*.{0,64}?\*/", _FLAGS)
_WHITESPACE = re.compile(r"\s+")
MAX_SCAN = 8_000  # znaków na pole; ładunki SQL injection są krótkie


@dataclass
class Finding:
    """Wynik dla jednego pola: nazwy dopasowanych wzorców."""

    location: str
    patterns: list[str] = field(default_factory=list)


@dataclass
class Detection:
    findings: list[Finding] = field(default_factory=list)

    @property
    def detected(self) -> bool:
        return bool(self.findings)

    @property
    def patterns(self) -> list[str]:
        return sorted({name for finding in self.findings for name in finding.patterns})

    @property
    def locations(self) -> list[str]:
        return [finding.location for finding in self.findings]


def scan_text(text: str) -> list[str]:
    """Nazwy wzorców SQL injection w tekście (pusta lista = czysto)."""
    if not text or len(text) < 4:
        return []
    candidate = text[:MAX_SCAN]
    for _ in range(2):  # %27%20OR%20... i podwójne kodowanie
        decoded = unquote_plus(candidate)
        if decoded == candidate:
            break
        candidate = decoded
    # UNION/**/SELECT (komentarz = spacja) i UN/**/ION (sklejenie, filtry słów kluczowych)
    variants = tuple(
        _WHITESPACE.sub(" ", _INLINE_COMMENT.sub(sep, candidate)) for sep in (" ", "")
    )
    strong = [n for n, pattern in STRONG.items() if any(pattern.search(v) for v in variants)]
    weak = [n for n, pattern in WEAK.items() if any(pattern.search(v) for v in variants)]
    if strong or len(weak) >= 2:
        return strong + weak
    return []


def _strings(value: Any, path: str) -> Iterator[tuple[str, str]]:
    if isinstance(value, str):
        yield path, value
    elif isinstance(value, dict):
        for key, item in value.items():
            yield from _strings(item, f"{path}.{key}" if path else str(key))
            if isinstance(key, str):
                yield f"{path}.{key}#klucz" if path else f"{key}#klucz", key
    elif isinstance(value, list):
        for index, item in enumerate(value[:200]):
            yield from _strings(item, f"{path}[{index}]")


def scan_fields(fields: Any, prefix: str = "") -> Detection:
    """Przeskanuj zagnieżdżone dane (np. JSON); ``location`` to ścieżka pola."""
    detection = Detection()
    for location, text in _strings(fields, prefix):
        patterns = scan_text(text)
        if patterns:
            detection.findings.append(Finding(location, patterns))
    return detection


def scan_request(path: str, query_string: bytes, body: bytes, content_type: str) -> Detection:
    """Ścieżka URL, parametry zapytania i treść (JSON albo formularz) jednego żądania."""
    detection = Detection()
    path_patterns = scan_text(path)
    if path_patterns:
        detection.findings.append(Finding("sciezka", path_patterns))
    query = query_string.decode("latin-1")
    for key, value in parse_qsl(query, keep_blank_values=True):
        for location, text in ((f"query.{key}", value), (f"query.{key}#klucz", key)):
            patterns = scan_text(text)
            if patterns:
                detection.findings.append(Finding(location, patterns))
    if body:
        text = body.decode("utf-8", "replace")  # rozmiar ogranicza middleware
        if "json" in content_type:
            try:
                detection.findings += scan_fields(json.loads(text), "body").findings
            except ValueError:
                detection.findings += scan_fields(text, "body").findings
        elif "x-www-form-urlencoded" in content_type:
            pairs = dict(parse_qsl(text, keep_blank_values=True))
            detection.findings += scan_fields(pairs, "form").findings
        else:
            detection.findings += scan_fields(text, "body").findings
    return detection
