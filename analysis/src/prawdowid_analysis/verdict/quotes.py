"""Weryfikacja cytatów: czy cytat podany przez model naprawdę występuje w tekście pasażu.

Bez sieci i bez LLM. Najpierw dopasowanie dokładne po normalizacji (białe znaki,
typograficzne cudzysłowy i myślniki, wielkość liter), potem dopasowanie przybliżone
(rapidfuzz) z wysokim progiem, które wybacza drobne różnice przepisania (np. brak
kropki, inny cudzysłów). Wynik zawsze wskazuje fragment źródła (`matched_text`
i offsety względem `passage.text`), więc w dowodzie zapisujemy dokładne brzmienie źródła,
a nie wersję modelu.
"""

import re
from dataclasses import dataclass

from rapidfuzz import fuzz

# Progi: stroić tylko na publicznej części zbioru testowego.
FUZZY_THRESHOLD = 95.0
MIN_QUOTE_CHARS = 12

_TRANSLATE = str.maketrans(
    {
        "“": '"',
        "”": '"',
        "„": '"',
        "«": '"',
        "»": '"',
        "‘": "'",
        "’": "'",
        "‚": "'",
        "–": "-",
        "—": "-",
        "−": "-",
        " ": " ",
    }
)
_WS_RE = re.compile(r"\s")
_NUMBER_RE = re.compile(r"\d+(?:[.,]\d+)*")
_WORD_RE = re.compile(r"\w+")
# Słowa zmieniające sens zdania na przeciwny: muszą się zgadzać przy dopasowaniu przybliżonym.
_NEGATIONS = frozenset({"nie", "nigdy", "brak", "bez", "żaden", "żadna", "żadne", "ani"})


def _critical_tokens(norm: str) -> tuple[list[str], list[str]]:
    words = _WORD_RE.findall(norm)
    return _NUMBER_RE.findall(norm), [w for w in words if w in _NEGATIONS]


@dataclass(frozen=True)
class QuoteMatch:
    verified: bool
    score: float  # 0-100, 100 = dopasowanie dokładne po normalizacji
    char_start: int | None = None  # offsety względem passage.text
    char_end: int | None = None
    matched_text: str = ""  # dokładny fragment passage.text


def _normalize(text: str) -> tuple[str, list[int]]:
    """Zwraca tekst znormalizowany i mapę: indeks znormalizowany -> indeks oryginału."""
    chars: list[str] = []
    index: list[int] = []
    prev_space = True  # usuwa białe znaki na początku
    for i, ch in enumerate(text.translate(_TRANSLATE)):
        if _WS_RE.match(ch):
            if prev_space:
                continue
            ch, prev_space = " ", True
        else:
            prev_space = False
        chars.append(ch.lower())
        index.append(i)
    if chars and chars[-1] == " ":
        chars.pop()
        index.pop()
    return "".join(chars), index


def _strip_quote(quote: str) -> str:
    # Modele często otaczają cytat cudzysłowem lub wielokropkiem.
    return quote.strip().strip("\"'“”„«»").strip(" .…").strip()


def verify_quote(
    quote: str,
    passage_text: str,
    *,
    threshold: float = FUZZY_THRESHOLD,
    min_chars: int = MIN_QUOTE_CHARS,
) -> QuoteMatch:
    """Sprawdza, czy `quote` występuje w `passage_text`; zwraca dopasowany fragment źródła."""
    norm_quote, _ = _normalize(_strip_quote(quote or ""))
    norm_text, index = _normalize(passage_text or "")
    if len(norm_quote) < min_chars or not norm_text:
        return QuoteMatch(verified=False, score=0.0)

    start = norm_text.find(norm_quote)
    if start >= 0:
        score, end = 100.0, start + len(norm_quote)
    elif len(norm_quote) > len(norm_text):
        return QuoteMatch(verified=False, score=0.0)
    else:
        al = fuzz.partial_ratio_alignment(norm_quote, norm_text)
        if al is None or al.score < threshold or al.dest_end <= al.dest_start:
            return QuoteMatch(verified=False, score=al.score if al else 0.0)
        score, start, end = al.score, al.dest_start, al.dest_end
        # Literówka w słowie jest dopuszczalna, zmieniona liczba albo zgubione "nie" — nie.
        if _critical_tokens(norm_quote) != _critical_tokens(norm_text[start:end]):
            return QuoteMatch(verified=False, score=round(score, 1))

    o_start, o_end = index[start], index[end - 1] + 1
    return QuoteMatch(
        verified=True,
        score=round(score, 1),
        char_start=o_start,
        char_end=o_end,
        matched_text=passage_text[o_start:o_end],
    )
