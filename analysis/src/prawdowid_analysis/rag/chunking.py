"""Podział `clean_text` na pasaże po zdaniach, z offsetami względem oryginału.

Gwarancja: dla każdego chunka `clean_text[chunk.start:chunk.end] == chunk.text`.
"""

import re
from dataclasses import dataclass

# Koniec zdania: . ! ? … (opcjonalnie cudzysłów/nawias), potem biały znak i wielka litera,
# cyfra albo cudzysłów. Pusta linia też kończy zdanie (nagłówki, punkty listy).
_SENT_END = re.compile(r"(?<=[.!?…])[\"”»)]*\s+(?=[A-ZĄĆĘŁŃÓŚŹŻ0-9\"„«(])|\n\s*\n")

# Skróty, po których kropka nie kończy zdania.
_ABBREV = {
    "art",
    "ust",
    "pkt",
    "nr",
    "poz",
    "dz",
    "u",
    "r",
    "zm",
    "tj",
    "np",
    "m.in",
    "tzw",
    "ok",
    "godz",
    "str",
    "s",
    "tys",
    "mln",
    "mld",
    "zł",
    "proc",
    "prof",
    "dr",
    "inż",
    "św",
    "ul",
    "al",
    "pl",
    "lit",
    "rozp",
    "min",
    "ws",
    "wg",
    "jw",
    "itd",
    "itp",
}


@dataclass(frozen=True)
class Chunk:
    index: int
    start: int
    end: int
    text: str


def split_sentences(text: str) -> list[tuple[int, int]]:
    """Zwraca zakresy (start, end) zdań; białe znaki na brzegach są obcięte."""
    spans: list[tuple[int, int]] = []
    pos = 0
    for m in _SENT_END.finditer(text):
        is_paragraph = re.search(r"\n\s*\n", m.group(0)) is not None
        last_word = re.search(r"([\w.]+?)\.?[\"”»)]*$", text[pos : m.start()])
        if not is_paragraph and last_word and last_word.group(1).lower().rstrip(".") in _ABBREV:
            continue
        _append_span(text, pos, m.start(), spans)
        pos = m.end()
    _append_span(text, pos, len(text), spans)
    return spans


def _append_span(text: str, start: int, end: int, spans: list[tuple[int, int]]) -> None:
    while start < end and text[start].isspace():
        start += 1
    while end > start and text[end - 1].isspace():
        end -= 1
    if end > start:
        spans.append((start, end))


def chunk_text(text: str, max_chars: int = 800, overlap_sentences: int = 1) -> list[Chunk]:
    """Skleja kolejne zdania do ~`max_chars` znaków; sąsiednie chunki dzielą
    `overlap_sentences` zdań. Zdanie dłuższe niż limit tworzy osobny chunk."""
    sentences = split_sentences(text)
    chunks: list[Chunk] = []
    i = 0
    while i < len(sentences):
        j = i + 1
        while j < len(sentences) and sentences[j][1] - sentences[i][0] <= max_chars:
            j += 1
        start, end = sentences[i][0], sentences[j - 1][1]
        chunks.append(Chunk(index=len(chunks), start=start, end=end, text=text[start:end]))
        if j >= len(sentences):
            break
        # cofnięcie o overlap, ale zawsze co najmniej jedno zdanie do przodu
        i = max(j - overlap_sentences, i + 1)
    return chunks
