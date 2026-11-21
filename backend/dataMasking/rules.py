"""Reguły wykrywania danych osobowych w polskim tekście.

Każda reguła to wzorzec i opcjonalnie: walidator sumy kontrolnej, słowo-klucz
szukane tuż przed wartością oraz flaga ``weak``. Reguły ``weak`` (sam kształt,
bez sumy kontrolnej, np. telefon) nie maskują liczb, po których stoi jednostka
(„500 000 000 zł”) ani przed którymi stoi odwołanie prawne („poz. 1234”).

Imion i nazwisk celowo nie wykrywamy: zostają w tekście.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum

from . import validators as v


class Keyword(Enum):
    NONE = "none"
    """Słowo-klucz nie ma znaczenia."""
    REQUIRED = "required"
    """Bez słowa-klucza przed wartością reguła nic nie maskuje."""
    BYPASS = "bypass"
    """Słowo-klucz przed wartością pomija walidację (użytkownik sam nazwał dane)."""


@dataclass(frozen=True)
class Rule:
    label: str
    pattern: re.Pattern[str]
    priority: int
    validate: Callable[[str], bool] | None = None
    keyword: re.Pattern[str] | None = None
    keyword_mode: Keyword = Keyword.NONE
    weak: bool = False
    blocked_after: re.Pattern[str] | None = None
    """Nie maskuj, jeśli wartość stoi zaraz po tym tekście (np. „wersja 1.2.3.4”)."""


# Granice liczby: nie doklejona do liter/cyfr i nie będąca częścią ułamka („3,5”, „1.25”).
_B = r"(?<!\w)(?<!\d[.,])"
_E = r"(?!\w)(?![.,]\d)"

_UPPER = "A-ZĄĆĘŁŃÓŚŹŻ"
_MONTHS = (
    "stycznia|lutego|marca|kwietnia|maja|czerwca|lipca|sierpnia|"
    "września|wrzesnia|października|pazdziernika|listopada|grudnia"
)

# Nazwa ulicy: 1–4 słowa od wielkiej litery, liczba (np. „3 Maja”) albo skrót tytułu.
_STREET = (
    rf"(?:(?:[{_UPPER}][\w'.\-]*|\d{{1,2}}|(?i:gen|ks|św|sw|marsz|prof|kard|bpa?|al)\.)\s+){{1,4}}?"
)
_HOUSE = (
    r"\d{1,4}[a-zA-Z]?(?:\s?/\s?\d{1,4}[a-zA-Z]?|\s?(?i:m\.|lok\.|lokal|mieszk\.)\s?\d{1,4})?(?!\w)"
)

# Po tym tekst jest kwotą albo statystyką, nie numerem telefonu.
UNIT_AFTER = re.compile(
    r"\s*(?:zł|zl|złotych|zlotych|pln|eur|euro|usd|dolarów|\$|€|%|proc|procent|tys|mln|mld|"
    r"osób|osob|osoby|ludzi|mieszkańców|polaków|km|kg|ton|lat|latach|głosów|glosow|sztuk|szt|"
    r"m2|m²|ha|razy|dawek|zgonów|przypadków)(?!\w)",
    re.IGNORECASE,
)
# Przed tym liczba jest odwołaniem prawnym albo przybliżoną wielkością.
CONTEXT_BEFORE = re.compile(
    r"(?:poz\.|dz\.\s?u\.?|art\.|nr\s+druku|druk\s+nr|sygn\.?(?:\s+akt)?|ust\.|§|"
    r"ok\.|około|ponad|prawie|blisko|niemal|nawet|aż)\s*$",
    re.IGNORECASE,
)

URL = re.compile(r"(?:https?://|www\.)\S+", re.IGNORECASE)


def _kw(words: str) -> re.Pattern[str]:
    return re.compile(rf"(?<!\w)(?:{words})", re.IGNORECASE)


def _c(pattern: str, flags: int = 0) -> re.Pattern[str]:
    return re.compile(pattern, flags)


RULES: tuple[Rule, ...] = (
    Rule(
        "EMAIL",
        _c(r"(?<![\w.+\-])[\w.+\-]+@[\w\-]+(?:\.[\w\-]+)*\.[A-Za-z]{2,}(?![\w\-])"),
        priority=0,
    ),
    # Numer konta: polski (26 cyfr, opcjonalnie z „PL”) albo zagraniczny IBAN.
    Rule(
        "NR_KONTA",
        _c(
            rf"{_B}(?:PL ?)?\d{{2}}(?: ?\d{{4}}){{6}}{_E}"
            r"|(?<!\w)[A-Z]{2}\d{2}(?: ?[A-Z0-9]{4}){2,7}(?: ?[A-Z0-9]{1,3})?(?!\w)"
        ),
        priority=1,
        validate=v.is_iban,
        keyword=_kw(r"kont[oa]|rachun\w*|iban|przelew\w*"),
        keyword_mode=Keyword.BYPASS,
    ),
    Rule(
        "KARTA",
        _c(rf"{_B}\d(?:[ \-]?\d){{12,18}}{_E}"),
        priority=2,
        validate=v.is_payment_card,
    ),
    Rule(
        "PESEL",
        _c(rf"{_B}\d{{11}}{_E}"),
        priority=3,
        validate=v.is_pesel,
        keyword=_kw("pesel"),
        keyword_mode=Keyword.BYPASS,
        weak=True,
    ),
    Rule(
        "NIP",
        _c(
            rf"{_B}(?:PL ?)?\d{{3}}(?P<s>[\- ]?)\d{{3}}(?P=s)\d{{2}}(?P=s)\d{{2}}{_E}"
            rf"|{_B}\d{{3}}-\d{{2}}-\d{{2}}-\d{{3}}{_E}"
        ),
        priority=4,
        validate=v.is_nip,
        keyword=_kw("nip"),
        keyword_mode=Keyword.BYPASS,
        weak=True,
    ),
    Rule(
        "REGON",
        _c(rf"{_B}\d{{14}}{_E}"),
        priority=5,
        validate=v.is_regon,
        keyword=_kw("regon"),
        keyword_mode=Keyword.BYPASS,
    ),
    # 9 cyfr to zwykle telefon, więc 9-cyfrowy REGON tylko po słowie „REGON”.
    Rule(
        "REGON",
        _c(rf"{_B}\d{{9}}{_E}"),
        priority=5,
        keyword=_kw("regon"),
        keyword_mode=Keyword.REQUIRED,
    ),
    Rule(
        "DOWOD",
        _c(r"(?<!\w)[A-Z]{3} ?\d{6}(?!\w)"),
        priority=6,
        validate=v.is_id_card,
        keyword=_kw(r"dow[oó]d\w*|seria|nr\s+dowodu"),
        keyword_mode=Keyword.BYPASS,
    ),
    Rule(
        "PASZPORT",
        _c(r"(?i:paszport\w*|passport)[^\n\d]{0,25}?(?P<v>[A-Z]{2} ?\d{7})(?!\w)"),
        priority=6,
    ),
    Rule(
        "DATA_URODZENIA",
        _c(
            r"(?<!\w)(?i:ur\.|urodzon\w*|urodził\w*\s+się|urodzil\w*\s+sie|data\s+urodzenia:?|d\.\s?ur\.)"
            r"\s*(?i:dnia\s+|w\s+dniu\s+)?"
            rf"(?P<v>\d{{1,2}}[./\-]\d{{1,2}}[./\-](?:\d{{4}}|\d{{2}})|\d{{1,2}}\s+(?i:{_MONTHS})\s+\d{{4}}|\d{{4}}-\d{{2}}-\d{{2}})"
            r"(?:\s?r\.)?"
        ),
        priority=7,
    ),
    Rule(
        "ADRES",
        _c(
            r"(?<!\w)(?i:ul\.|ulic[aąyę]|al\.|alej[aąię]|aleje|pl\.|plac(?:u|em)?|os\.|osiedl(?:e|u|em))"
            rf"\s*{_STREET}{_HOUSE}"
        ),
        priority=8,
    ),
    # „mieszkam przy Długiej 5”, „adres: Długa 5/3”.
    Rule(
        "ADRES",
        _c(
            r"(?<!\w)(?:(?i:mieszka\w*|zamieszka\w*)[^\d\n.]{0,40}?(?i:na|przy)\s+|(?i:adres\w*):?\s+)"
            rf"(?P<v>{_STREET}{_HOUSE})"
        ),
        priority=8,
    ),
    # Z prefiksem kraju: pewny telefon.
    Rule(
        "TELEFON",
        _c(
            r"(?<![\w+])(?:\+|00) ?48[ \-]?"
            r"(?:\d{3}[ \-]?\d{3}[ \-]?\d{3}|\(?\d{2}\)?[ \-]?\d{3}[ \-]?\d{2}[ \-]?\d{2})(?!\w)(?![.,]\d)"
        ),
        priority=9,
    ),
    # Komórkowy bez prefiksu: 9 cyfr zaczynających się od 4–8, z jednakowymi odstępami.
    Rule(
        "TELEFON",
        _c(rf"{_B}[4-8]\d{{2}}(?P<s>[ \-]?)\d{{3}}(?P=s)\d{{3}}{_E}"),
        priority=9,
        weak=True,
    ),
    # Stacjonarny: (22) 123 45 67, 22 123 45 67, 22-123-45-67.
    Rule(
        "TELEFON",
        _c(
            rf"{_B}\(\d{{2}}\) ?\d{{3}}[ \-]?\d{{2}}[ \-]?\d{{2}}{_E}"
            rf"|{_B}[1-9]\d(?P<s>[ \-])\d{{3}}(?P=s)\d{{2}}(?P=s)\d{{2}}{_E}"
        ),
        priority=9,
        weak=True,
    ),
    Rule(
        "IP",
        _c(r"(?<![\w.])\d{1,3}(?:\.\d{1,3}){3}(?!\w)(?!\.\d)"),
        priority=10,
        validate=v.is_ipv4,
        blocked_after=re.compile(r"(?:wersj\w*|ver\.?|v\.?)\s*$", re.IGNORECASE),
    ),
    # Kod pocztowy tylko przed nazwą miejscowości, żeby nie łapać zakresów („10-100”).
    Rule(
        "KOD_POCZTOWY",
        _c(rf"(?<![\w\-])\d{{2}}-\d{{3}}(?![\w\-])(?=,?\s+[{_UPPER}])"),
        priority=11,
        weak=True,
    ),
    Rule(
        "NR_REJESTRACYJNY",
        _c(
            r"(?i:nr\.?\s+rej\w*\.?|numer\w*\s+rejestracyjn\w*|tablic\w*(?:\s+rejestracyjn\w*)?|rejestracj\w*)"
            r"[^\n]{0,15}?(?<!\w)(?P<v>(?=[A-Z]{1,3} ?[A-Z0-9]{0,4}\d)[A-Z]{1,3} ?[A-Z0-9]{4,5})(?!\w)"
        ),
        priority=12,
    ),
)
