"""Granica A <-> B: `retrieve(query, k=6, filters=None) -> list[Passage]`.

1. Wyszukiwanie hybrydowe w Qdrant: prefetch dense + BM25, fuzja RRF -> kandydaci.
2. Reranker (domyślnie cosinus bge-m3) -> `rerank_score`, sortowanie, top-k.

`rerank_score` jest bezwzględną miarą trafności (próg wstrzymania się po stronie
werdyktu); wynik RRF służy tylko do zebrania kandydatów.
"""

import os
from collections.abc import Callable
from functools import lru_cache

from ..schemas import Passage
from .config import load_config
from .embed import OpenAIEmbedder, embedder_from_config
from .rerank import CosineReranker, Reranker
from .sparse import sparse_vector
from .store import QdrantStore, store_from_config

Retriever = Callable[..., list[Passage]]


@lru_cache(maxsize=1)
def _deps() -> tuple[QdrantStore, OpenAIEmbedder, int]:
    cfg = load_config()
    return store_from_config(cfg), embedder_from_config(cfg), cfg.prefetch_limit


def search(
    query: str,
    store: QdrantStore,
    embedder: OpenAIEmbedder,
    k: int = 6,
    filters: dict | None = None,
    prefetch_limit: int = 30,
    reranker: Reranker | None = None,
    candidates: int | None = None,
) -> list[Passage]:
    reranker = reranker or CosineReranker()
    query_vec = embedder.embed([query])[0]
    points = store.hybrid_query(
        dense=query_vec,
        sparse=sparse_vector(query, is_query=True),
        limit=max(candidates or 3 * k, k),
        prefetch_limit=max(prefetch_limit, k),
        filters=filters,
        with_dense_vector=True,
    )
    if not points:
        return []
    scores = reranker.score(query, query_vec, points)
    ranked = sorted(
        zip(points, scores, strict=True), key=lambda ps: (-ps[1], ps[0]["payload"]["chunk_id"])
    )
    return [
        Passage.model_validate({**pt["payload"], "rerank_score": round(score, 4)})
        for pt, score in ranked[:k]
    ]


def retrieve(query: str, k: int = 6, filters: dict | None = None) -> list[Passage]:
    store, embedder, prefetch_limit = _deps()
    return search(query, store, embedder, k=k, filters=filters, prefetch_limit=prefetch_limit)


def get_retriever(name: str | None = None) -> Retriever:
    """Przełącznik `RETRIEVER=mock|qdrant` (domyślnie `mock`)."""
    name = (name or os.getenv("RETRIEVER") or "mock").strip().lower()
    if name == "mock":
        from .mock import mock_retrieve

        return mock_retrieve
    if name == "qdrant":
        return retrieve
    raise ValueError(f"Nieznany retriever: {name!r} (dozwolone: mock, qdrant)")
