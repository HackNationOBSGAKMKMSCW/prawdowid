"""Źródła wzorcowe: lokalny korpus, podział na fragmenty i wyszukiwanie BM25.

Korpus to pliki JSON w `analysis/data/sources/` (jeden plik = jeden dokument):

    {"id": "...", "title": "...", "publisher": "...", "url": "...",
     "published_at": "YYYY-MM-DD", "text": "..."}

Do korpusu trafiają wyłącznie źródła zatwierdzone jako wzorcowe; model nie dostaje
nic spoza puli (korpus + źródła podane w zapytaniu + wyniki fact-checkingu).

BM25 działa offline i bez zależności. Polska fleksja jest przybliżana obcięciem
tokenu do prefiksu (`STEM_CHARS`), co wystarcza do dopasowania form typu
„stolica/stolicą/stolicy”. Interfejs `Retriever.search()` pozwala później
podmienić wyszukiwarkę (np. na wektorową) bez zmian w reszcie potoku.
"""

import json
import math
import os
import re
import unicodedata
from collections import Counter
from collections.abc import Iterable
from pathlib import Path

from .config import ANALYSIS_DIR
from .schemas import ReferenceSource, SourceKind

DEFAULT_CORPUS_DIR = ANALYSIS_DIR / "data" / "sources"
CHUNK_CHARS = 900
STEM_CHARS = 6

_STOPWORDS = {
    "a", "aby", "ale", "albo", "ani", "az", "bo", "by", "byc", "byl", "byla", "bylo", "czy",
    "dla", "do", "gdy", "i", "ich", "jak", "jako", "jej", "jest", "jego", "juz", "ku", "lub",
    "ma", "na", "nad", "nie", "o", "od", "oraz", "po", "pod", "przez", "przy", "sa", "sie",
    "tak", "takze", "te", "to", "tym", "u", "w", "we", "z", "za", "ze", "zas", "ten", "ta",
    "the", "of", "and", "in", "is", "an", "on", "for", "that", "are", "was",
}  # fmt: skip


def _fold(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text.lower().replace("ł", "l"))
    return "".join(ch for ch in normalized if not unicodedata.combining(ch))


def tokenize(text: str) -> list[str]:
    tokens = []
    for token in re.findall(r"\w+", _fold(text)):
        if token in _STOPWORDS:
            continue
        tokens.append(token if token.isdigit() else token[:STEM_CHARS])
    return tokens


KEYWORD_MATCH_CHARS = 4


def _words(text: str) -> list[str]:
    return [t for t in re.findall(r"\w+", _fold(text)) if t not in _STOPWORDS]


def expand_query(claim: str, keywords: Iterable[str]) -> str:
    """Dopisuje do zapytania słowa kluczowe (w mianowniku) pasujące do twierdzenia.

    Słowo kluczowe pasuje, gdy któreś jego słowo ma wspólny początek ze słowem
    twierdzenia (`_same_stem`), np. „Rysy” do „Rysów”. Dzięki temu forma podstawowa
    pomaga trafić w korpus tam, gdzie obcięcie do `STEM_CHARS` nie wystarcza;
    słowa kluczowe dotyczące innych twierdzeń nie są dodawane.
    """
    claim_words = _words(claim)
    extra = [
        keyword
        for keyword in keywords
        if any(_same_stem(k, c) for k in _words(keyword) for c in claim_words)
    ]
    return " ".join([claim, *extra]) if extra else claim


def _same_stem(a: str, b: str) -> bool:
    """Wspólny początek ≥ 3 znaki i najwyżej o 1 krótszy od krótszego słowa
    (maks. `KEYWORD_MATCH_CHARS`): „rysy”/„rysow”, „szczepionka”/„szczepionki”."""
    if a == b:
        return True
    common = len(os.path.commonprefix([a, b]))
    return common >= 3 and common >= min(len(a), len(b), KEYWORD_MATCH_CHARS + 1) - 1


def chunk_text(text: str, max_chars: int = CHUNK_CHARS) -> list[str]:
    """Dzieli tekst po akapitach, sklejając krótkie akapity do `max_chars`."""
    paragraphs = [" ".join(p.split()) for p in re.split(r"\n\s*\n", text)]
    chunks: list[str] = []
    current = ""
    for paragraph in filter(None, paragraphs):
        if len(paragraph) > max_chars:
            if current:
                chunks.append(current)
                current = ""
            sentences = re.split(r"(?<=[.!?])\s+", paragraph)
            for sentence in sentences:
                if current and len(current) + len(sentence) + 1 > max_chars:
                    chunks.append(current)
                    current = ""
                current = f"{current} {sentence}".strip()
            continue
        if current and len(current) + len(paragraph) + 2 > max_chars:
            chunks.append(current)
            current = ""
        current = f"{current}\n\n{paragraph}".strip()
    if current:
        chunks.append(current)
    return chunks


def split_source(source: ReferenceSource, max_chars: int = CHUNK_CHARS) -> list[ReferenceSource]:
    """Dzieli długie źródło na fragmenty `<id>#<n>`; krótkie zostawia bez zmian."""
    chunks = chunk_text(source.text, max_chars)
    if len(chunks) <= 1:
        return [source]
    return [
        source.model_copy(update={"source_id": f"{source.source_id}#{n}", "text": chunk})
        for n, chunk in enumerate(chunks, 1)
    ]


def load_documents(
    directory: Path = DEFAULT_CORPUS_DIR, kind: SourceKind = "korpus"
) -> list[ReferenceSource]:
    """Wczytuje dokumenty korpusu wzorcowego (bez podziału na fragmenty)."""
    documents = []
    for path in sorted(Path(directory).glob("*.json")):
        raw = json.loads(path.read_text(encoding="utf-8"))
        documents.append(
            ReferenceSource(
                source_id=raw.get("id") or path.stem,
                kind=kind,
                title=raw.get("title", ""),
                publisher=raw.get("publisher", ""),
                url=raw.get("url"),
                published_at=raw.get("published_at"),
                text=raw["text"],
            )
        )
    return documents


class Retriever:
    """BM25 nad fragmentami źródeł wzorcowych."""

    def __init__(self, sources: Iterable[ReferenceSource], k1: float = 1.5, b: float = 0.75):
        self.passages: list[ReferenceSource] = [p for s in sources for p in split_source(s)]
        self._tokens = [Counter(tokenize(f"{p.title} {p.text}")) for p in self.passages]
        self._lengths = [sum(t.values()) for t in self._tokens]
        self._avg_len = (sum(self._lengths) / len(self._lengths)) if self._lengths else 0.0
        self._df: Counter[str] = Counter()
        for tokens in self._tokens:
            self._df.update(tokens.keys())
        self.k1, self.b = k1, b

    @classmethod
    def from_directory(cls, directory: Path = DEFAULT_CORPUS_DIR) -> "Retriever":
        return cls(load_documents(directory))

    def __len__(self) -> int:
        return len(self.passages)

    def _idf(self, term: str) -> float:
        n, df = len(self.passages), self._df.get(term, 0)
        return math.log(1 + (n - df + 0.5) / (df + 0.5))

    def search(
        self, query: str, k: int = 5, min_score: float = 0.5
    ) -> list[tuple[ReferenceSource, float]]:
        """Zwraca do `k` fragmentów z wynikiem BM25 >= `min_score`, od najlepszego."""
        terms = set(tokenize(query))
        if not terms or not self.passages:
            return []
        scored = []
        for passage, tokens, length in zip(self.passages, self._tokens, self._lengths, strict=True):
            score = 0.0
            for term in terms:
                tf = tokens.get(term, 0)
                if tf:
                    norm = 1 - self.b + self.b * length / (self._avg_len or 1)
                    score += self._idf(term) * tf * (self.k1 + 1) / (tf + self.k1 * norm)
            if score >= min_score:
                scored.append((passage, score))
        scored.sort(key=lambda pair: pair[1], reverse=True)
        return scored[:k]
