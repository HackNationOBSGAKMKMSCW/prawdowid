"""Wykrywanie zapytań o treści niebezpieczne (terroryzm, broń, materiały wybuchowe, CBRN).

Serwis sprawdza fakty, więc samo pytanie o zamach z wiadomości jest uprawnione: dostaje
poziom ``sredni`` (temat wrażliwy, do obserwacji). Poziom ``wysoki`` oznacza zamiar
operacyjny — prośbę o instrukcję, przepis, zdobycie lub przeprowadzenie — połączony z
niebezpiecznym tematem. Dopasowanie działa na tekście bez polskich znaków.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal

from .topics import normalize

Severity = Literal["brak", "sredni", "wysoki"]

CATEGORIES: dict[str, tuple[str, ...]] = {
    "terroryzm": (
        r"terror\w*",
        r"zamach\w*",
        r"d[zż]ihad\w*",
        r"jihad\w*",
        r"isis",
        r"panstw\w* islamsk\w*",
        r"al[- ]?ka[ie]d\w*",
        r"al[- ]?qaeda",
        r"radykalizac\w*",
        r"zamachowc\w*",
        r"samobojcz\w* atak\w*",
    ),
    "materialy_wybuchowe": (
        r"bomb\w*",
        r"materia\w* wybuchow\w*",
        r"ladun\w* wybuchow\w*",
        r"detonator\w*",
        r"tatp",
        r"semtex\w*",
        r"trotyl\w*",
        r"saletr\w*",
        r"explosive\w*",
        r"\bied\b",
        r"granat\w*",
    ),
    "bron": (
        r"bron\w* paln\w*",
        r"bez pozwolenia na bron",
        r"karabin\w*",
        r"pistolet\w*",
        r"amunic\w*",
        r"ghost gun\w*",
        r"bron\w* z drukarki",
        r"druk\w* 3d bron\w*",
        r"tlumik\w*",
    ),
    "bron_masowego_razenia": (
        r"sarin\w*",
        r"waglik\w*",
        r"anthrax",
        r"rycyn\w*",
        r"ricin",
        r"bron\w* (?:biologiczn|chemiczn|jadrow|nuklearn)\w*",
        r"gaz\w* bojow\w*",
        r"brudn\w* bomb\w*",
        r"wzbogac\w* uran\w*",
        r"patogen\w*",
        r"nerve agent\w*",
    ),
    "przemoc_masowa": (
        r"strzelanin\w*",
        r"masow\w* (?:zabojstw|mord)\w*",
        r"(?:zabic|zamordowac|otruc) (?:jak najwiecej|wiele|tlum)\w*",
        r"mass shooting\w*",
    ),
}

INTENT_PATTERNS: tuple[str, ...] = (
    r"jak (?:\w+ )?(?:zrobic|zbudowac|zrobi|wyprodukowac|wytworzyc|zsyntetyzowac|przygotowac|"
    r"zdobyc|kupic|przemycic|ukryc|zaplanowac|przeprowadzic|zmontowac|uzbroic|odpalic|zdetonowac)",
    r"instrukcj\w*",
    r"przepis\w* na",
    r"krok po kroku",
    r"skad (?:wziac|kupic|zdobyc)",
    r"gdzie (?:kupic|zdobyc|zamowic)",
    r"schemat\w* (?:budowy|konstrukcji)",
    r"proporcj\w*",
    r"how (?:to|do i|can i) (?:make|build|buy|get|synthesi[sz]e|assemble|plan)",
    r"step by step",
    r"recipe",
)

_CATEGORY_REGEX = {
    name: re.compile(r"\b(?:" + "|".join(patterns) + r")\b")
    for name, patterns in CATEGORIES.items()
}
_INTENT_REGEX = re.compile(r"\b(?:" + "|".join(INTENT_PATTERNS) + r")")


@dataclass(frozen=True)
class SafetyAssessment:
    severity: Severity = "brak"
    categories: tuple[str, ...] = ()
    operational_intent: bool = False
    matches: tuple[str, ...] = field(default=())

    @property
    def dangerous(self) -> bool:
        return self.severity != "brak"

    def as_dict(self) -> dict[str, object]:
        return {
            "severity": self.severity,
            "categories": list(self.categories),
            "operational_intent": self.operational_intent,
            "matches": list(self.matches),
        }


def classify(text: str) -> SafetyAssessment:
    """Oceń zapytanie; nie wywołuje modelu, więc działa przed całym potokiem."""
    plain = normalize(text)
    categories: list[str] = []
    matches: list[str] = []
    for name, regex in _CATEGORY_REGEX.items():
        found = regex.findall(plain)
        if found:
            categories.append(name)
            matches.extend(dict.fromkeys(found))
    if not categories:
        return SafetyAssessment()
    intent = bool(_INTENT_REGEX.search(plain))
    return SafetyAssessment(
        severity="wysoki" if intent else "sredni",
        categories=tuple(categories),
        operational_intent=intent,
        matches=tuple(matches[:10]),
    )
