"""Reranking kandydatów z wyszukiwania hybrydowego -> `rerank_score`.

RRF daje tylko kolejność (pierwszy wynik ma ~1.0 niezależnie od trafności), więc
`rerank_score` liczymy osobno, jako bezwzględną miarę trafności pasażu dla zapytania,
na której część werdyktu może oprzeć próg wstrzymania się.

`CosineReranker`: podobieństwo cosinusowe embeddingu zapytania i pasażu (ten sam model
co indeks, zero dodatkowych wywołań). Miejsce na reranker cross-encoder (np. bge-reranker
za endpointem HTTP) z tym samym interfejsem.
"""

import math
from typing import Protocol

from .store import DENSE


class Reranker(Protocol):
    name: str

    def score(self, query: str, query_vec: list[float], candidates: list[dict]) -> list[float]:
        """Wynik dla każdego kandydata (punkt Qdrant z `payload` i `vector`)."""
        ...


def cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


class CosineReranker:
    name = "cosine"

    def score(self, query: str, query_vec: list[float], candidates: list[dict]) -> list[float]:
        return [cosine(query_vec, c["vector"][DENSE]) for c in candidates]
