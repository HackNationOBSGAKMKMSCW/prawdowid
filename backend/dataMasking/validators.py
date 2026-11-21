"""Sprawdzanie sum kontrolnych identyfikatorów.

Numery z sumą kontrolną maskujemy dopiero po poprawnej walidacji, dzięki czemu
przypadkowy ciąg cyfr w statystyce (np. „12345678901 zł”) zostaje w tekście.
PESEL, NIP, REGON, IBAN i karty sprawdza ``python-stdnum``; dowodu osobistego
ta biblioteka nie obsługuje, więc jego sumę liczymy sami.
"""

from __future__ import annotations

import re

from stdnum import iban, luhn
from stdnum.pl import nip, pesel, regon

_DIGITS = re.compile(r"\D")


def digits(value: str) -> str:
    return _DIGITS.sub("", value)


def is_pesel(value: str) -> bool:
    """11 cyfr, poprawna data urodzenia i suma kontrolna."""
    return pesel.is_valid(digits(value))


def is_nip(value: str) -> bool:
    return nip.is_valid(value)


def is_regon(value: str) -> bool:
    return regon.is_valid(digits(value))


def is_iban(value: str) -> bool:
    """Polski numer konta (26 cyfr) można podać bez prefiksu ``PL``."""
    compact = re.sub(r"\s", "", value).upper()
    if compact.isdigit():
        compact = "PL" + compact
    return iban.is_valid(compact)


def is_payment_card(value: str) -> bool:
    d = digits(value)
    # Visa 4, Mastercard 2/5, Amex 3, Maestro 6. Inne pierwsze cyfry to raczej nie karty.
    return 13 <= len(d) <= 19 and d[0] in "23456" and luhn.is_valid(d)


_ID_CARD = re.compile(r"[A-Z]{3}\d{6}")
_ID_CARD_WEIGHTS = (7, 3, 1, 0, 7, 3, 1, 7, 3)


def is_id_card(value: str) -> bool:
    """Polski dowód osobisty: 3 litery i 6 cyfr, pierwsza cyfra jest kontrolna."""
    compact = value.replace(" ", "").replace("-", "").upper()
    if not _ID_CARD.fullmatch(compact):
        return False
    values = [ord(ch) - 55 for ch in compact[:3]] + [int(ch) for ch in compact[3:]]
    checksum = sum(v * w for v, w in zip(values, _ID_CARD_WEIGHTS, strict=True)) % 10
    return checksum == values[3]


def is_ipv4(value: str) -> bool:
    parts = value.split(".")
    return len(parts) == 4 and all(
        p.isdigit() and int(p) <= 255 and (p == "0" or not p.startswith("0")) for p in parts
    )
