"""Weryfikacja dosłowności cytatów względem treści źródła.

Cytat jest uznany, gdy po normalizacji typografii (cudzysłowy, myślniki, spacje,
wielkość liter) występuje w źródle jako ciągły fragment. Nie ma dopasowania
przybliżonego: zmieniona liczba, data albo usunięte „nie” sprawiają, że cytat
nie przechodzi. Zwracamy dokładny fragment ze źródła, a nie tekst modelu.
"""

import unicodedata

MIN_QUOTE_CHARS = 8

_CHAR_MAP = {
    "„": '"', "”": '"', "“": '"', "«": '"', "»": '"', "‟": '"',
    "’": "'", "‘": "'", "‚": "'", "`": "'",
    "–": "-", "—": "-", "‑": "-", "−": "-",
    " ": " ", " ": " ", " ": " ",
}  # fmt: skip
_EDGE_CHARS = " \t\n\"'.,;:!?()[]"


def _normalize_with_map(text: str) -> tuple[str, list[int]]:
    """Normalizuje tekst i zwraca mapę: indeks znaku znormalizowanego -> indeks w oryginale."""
    out: list[str] = []
    index: list[int] = []
    for i, raw_char in enumerate(text):
        for char in unicodedata.normalize("NFKC", raw_char):
            char = _CHAR_MAP.get(char, char)
            if char.isspace():
                if not out or out[-1] == " ":
                    continue
                char = " "
            for lowered in char.lower():
                out.append(lowered)
                index.append(i)
    while out and out[-1] == " ":
        out.pop()
        index.pop()
    return "".join(out), index


def normalize(text: str) -> str:
    return _normalize_with_map(text)[0]


def verify_quote(quote: str, source_text: str) -> str | None:
    """Zwraca dokładny fragment źródła odpowiadający cytatowi albo None."""
    if not quote or "..." in quote or "…" in quote:
        return None
    needle = normalize(quote).strip(_EDGE_CHARS)
    if len(needle) < MIN_QUOTE_CHARS:
        return None
    haystack, index = _normalize_with_map(source_text)
    start = haystack.find(needle)
    if start == -1:
        return None
    end = start + len(needle) - 1
    return source_text[index[start] : index[end] + 1]
