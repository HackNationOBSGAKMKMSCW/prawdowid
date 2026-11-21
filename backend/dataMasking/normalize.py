"""Znormalizowana kopia tekstu, na której działają reguły, z mapą pozycji do oryginału.

Reguły widzą tekst „wyprostowany”, a znaczniki trafiają w oryginalne miejsca:

- znikają niewidoczne znaki (zero-width, miękki dywiz), którymi da się rozbić numer,
- cyfry i litery w innych zapisach (pełna szerokość, indeksy) zamieniają się na zwykłe (NFKC),
- różne myślniki to ``-``, różne spacje (twarda, wąska) to spacja,
- litera O w liczbie to zero: „6OO 1OO 2OO” → „600 100 200”,
- liczby słownie dłuższe niż 6 cyfr to cyfry: „sześćset sto dwieście” → „600 100 200”,
- sklejone wiadomości dostają odstęp: „609 887 766Wnusiu”, „tel600100200”.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass

_DASHES = "‐‑‒–—―−﹘﹣－"
_INVISIBLE = "­͏؜ᅟᅠ឴឵᠎ㅤﾠ"


@dataclass(frozen=True)
class View:
    text: str
    starts: list[int]
    """Dla każdego znaku ``text`` – początek odpowiadającego fragmentu oryginału."""
    ends: list[int]
    """Dla każdego znaku ``text`` – koniec odpowiadającego fragmentu oryginału."""

    def original_span(self, start: int, end: int) -> tuple[int, int]:
        return self.starts[start], self.ends[end - 1]


def _chars(text: str) -> View:
    out: list[str] = []
    starts: list[int] = []
    ends: list[int] = []
    for i, ch in enumerate(text):
        if ch in _INVISIBLE or unicodedata.category(ch) == "Cf":
            continue
        if ch in _DASHES:
            norm = "-"
        elif unicodedata.category(ch) == "Zs":
            norm = " "
        else:
            norm = unicodedata.normalize("NFKC", ch)
        for c in norm:
            out.append(c)
            starts.append(i)
            ends.append(i + 1)
    return View("".join(out), starts, ends)


def _rewrite(view: View, pattern: re.Pattern[str], repl: Callable[[re.Match[str]], str]) -> View:
    """Jak ``re.sub``, ale z mapą pozycji: zamiennik tej samej długości mapuje znak po znaku."""
    out: list[str] = []
    starts: list[int] = []
    ends: list[int] = []
    cursor = 0
    for m in pattern.finditer(view.text):
        new = repl(m)
        if new == m.group():
            continue
        out.append(view.text[cursor : m.start()])
        starts.extend(view.starts[cursor : m.start()])
        ends.extend(view.ends[cursor : m.start()])
        if len(new) == m.end() - m.start():
            starts.extend(view.starts[m.start() : m.end()])
            ends.extend(view.ends[m.start() : m.end()])
        else:
            s, e = view.starts[m.start()], view.ends[m.end() - 1]
            starts.extend([s] * len(new))
            ends.extend([e] * len(new))
        out.append(new)
        cursor = m.end()
    if cursor == 0 and not out:
        return view
    out.append(view.text[cursor:])
    starts.extend(view.starts[cursor:])
    ends.extend(view.ends[cursor:])
    return View("".join(out), starts, ends)


# --- Litera O w liczbie ------------------------------------------------------------------

_DIGITISH = re.compile(r"(?<!\w)(?=[\dOo]*\d)[\dOo]+(?!\w)")


def _o_to_zero(m: re.Match[str]) -> str:
    return m.group().replace("O", "0").replace("o", "0")


# --- Liczby słownie ----------------------------------------------------------------------


def _ascii(word: str) -> str:
    return unicodedata.normalize("NFKD", word).encode("ascii", "ignore").decode()


_WORDS: dict[str, tuple[int, int]] = {}
"""Słowo → (wartość, klasa): 3 setki, 2 dziesiątki, 1 naście (10–19), 0 jedności."""
for _cls, _table in (
    (0, "zero jeden jedna dwa dwie trzy cztery pięć sześć siedem osiem dziewięć"),
    (
        1,
        "dziesięć jedenaście dwanaście trzynaście czternaście piętnaście szesnaście "
        "siedemnaście osiemnaście dziewiętnaście",
    ),
    (
        2,
        "dwadzieścia trzydzieści czterdzieści pięćdziesiąt sześćdziesiąt siedemdziesiąt "
        "osiemdziesiąt dziewięćdziesiąt",
    ),
    (3, "sto dwieście trzysta czterysta pięćset sześćset siedemset osiemset dziewięćset"),
):
    _values = {
        0: [0, 1, 1, 2, 2, 3, 4, 5, 6, 7, 8, 9],
        1: list(range(10, 20)),
        2: list(range(20, 100, 10)),
        3: list(range(100, 1000, 100)),
    }[_cls]
    for _word, _value in zip(_table.split(), _values, strict=True):
        _WORDS[_word] = (_value, _cls)
        _WORDS[_ascii(_word)] = (_value, _cls)

_WORD_ALT = "|".join(sorted(map(re.escape, _WORDS), key=len, reverse=True))
_NUMBER_RUN = re.compile(
    rf"(?<!\w)(?:{_WORD_ALT})(?:[\s,\-]+(?:{_WORD_ALT}))+(?!\w)", re.IGNORECASE
)
_TOKEN = re.compile(rf"{_WORD_ALT}", re.IGNORECASE)


def _number_words_to_digits(m: re.Match[str]) -> str:
    """„sześćset sto dwieście” → „600 100 200”, „pięć jeden dwa …” → „512…”."""
    groups: list[tuple[int, int]] = []  # (wartość, liczba cyfr)
    last_cls: int | None = None
    for token in _TOKEN.findall(m.group()):
        value, cls = _WORDS[token.lower()]
        joins = groups and (
            (last_cls == 3 and cls in (2, 1, 0) and value != 0)
            or (last_cls == 2 and cls == 0 and value != 0)
        )
        if joins:
            prev, width = groups[-1]
            groups[-1] = (prev + value, width)
        else:
            width = {3: 3, 2: 2, 1: 2, 0: 1}[cls]
            groups.append((value, width))
        last_cls = cls
    if sum(width for _, width in groups) < 7:
        return m.group()
    parts: list[str] = []
    for i, (value, width) in enumerate(groups):
        digits = str(value).zfill(width)
        # Cyfry pojedynczo („pięć jeden dwa”) sklejamy, większe grupy rozdzielamy spacją.
        if i and not (width == 1 and groups[i - 1][1] == 1):
            parts.append(" ")
        parts.append(digits)
    return "".join(parts)


# --- Sklejone wiadomości -----------------------------------------------------------------

_UPPER = "A-ZĄĆĘŁŃÓŚŹŻ"
_LOWER = "a-ząćęłńóśźż"
# Cyfra, a zaraz po niej nowe słowo od wielkiej litery: „766Wnusiu”.
_DIGIT_THEN_WORD = re.compile(rf"\d(?=[{_UPPER}][{_LOWER}])")
# Słowo doklejone do długiej liczby: „tel600100200”, „600100200zadzwoń”.
_WORD_THEN_LONG_NUMBER = re.compile(r"(?<=[^\W\d_]{2})[^\W\d_](?=\d{7})")
_LONG_NUMBER_THEN_WORD = re.compile(r"(?<=\d{6})\d(?=[^\W\d_]{2})")


def _space_after(m: re.Match[str]) -> str:
    return m.group() + " "


def build_view(text: str) -> View:
    view = _chars(text)
    view = _rewrite(view, _DIGITISH, _o_to_zero)
    view = _rewrite(view, _NUMBER_RUN, _number_words_to_digits)
    for pattern in (_DIGIT_THEN_WORD, _WORD_THEN_LONG_NUMBER, _LONG_NUMBER_THEN_WORD):
        view = _rewrite(view, pattern, _space_after)
    return view
