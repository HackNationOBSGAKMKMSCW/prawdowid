"""Odnajdywanie cytatów zwróconych przez LLM w oryginalnym tekście (offsety liczy Python).

Kolejność: dokładne dopasowanie → bez rozróżniania wielkości liter → fuzzy (rapidfuzz).
Cytat, którego nie da się odnaleźć, jest odrzucany (ochrona przed halucynacjami).
"""

from __future__ import annotations

from rapidfuzz import fuzz

FUZZY_CUTOFF = 85.0
MIN_FUZZY_LEN = 8


def _normalize_quotes(s: str) -> str:
    return (
        s.replace("„", '"')
        .replace("”", '"')
        .replace("“", '"')
        .replace("«", '"')
        .replace("»", '"')
        .replace("’", "'")
        .replace("‘", "'")
        .replace("–", "-")
        .replace("—", "-")
    )


def locate_quote(text: str, quote: str, *, start_hint: int = 0) -> tuple[int, int] | None:
    """Zwraca ``(start, end)`` cytatu w ``text`` albo ``None``.

    ``start_hint`` pozwala preferować wystąpienie od danej pozycji (gdy cytat się powtarza).
    """
    q = (quote or "").strip()
    if not q or not text:
        return None

    # 1. dokładnie
    for origin in (start_hint, 0):
        idx = text.find(q, origin)
        if idx != -1:
            return idx, idx + len(q)

    # 2. bez rozróżniania wielkości liter i typów cudzysłowów (normalizacja zachowuje długość)
    norm_text = _normalize_quotes(text).lower()
    norm_q = _normalize_quotes(q).lower()
    if len(norm_text) == len(text):
        for origin in (start_hint, 0):
            idx = norm_text.find(norm_q, origin)
            if idx != -1:
                return idx, idx + len(q)

    # 3. fuzzy: tylko dla dłuższych cytatów, krótkie dawałyby przypadkowe trafienia
    if len(norm_q) < MIN_FUZZY_LEN or len(norm_text) != len(text):
        return None
    alignment = fuzz.partial_ratio_alignment(norm_q, norm_text, score_cutoff=FUZZY_CUTOFF)
    if alignment is None:
        return None
    start, end = alignment.dest_start, alignment.dest_end
    # partial_ratio porównuje okno długości cytatu; odrzucamy wyraźnie krótsze trafienia
    if end - start < 0.8 * len(norm_q):
        return None
    return _trim(text, start, end)


def _trim(text: str, start: int, end: int) -> tuple[int, int]:
    while start < end and text[start].isspace():
        start += 1
    while end > start and text[end - 1].isspace():
        end -= 1
    return start, end
