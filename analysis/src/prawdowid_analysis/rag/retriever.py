"""Granica A <-> B: `retrieve(query, k=6, filters=None) -> list[Passage]`.

Wyszukiwanie hybrydowe w Qdrant: prefetch dense + BM25, fuzja RRF.
`rerank_score` to na razie wynik RRF; reranker dojdzie w kolejnym kroku.
"""

import os
from collections.abc import Callable
from functools import lru_cache

from ..schemas import Passage
from .config import load_config
from .embed import OpenAIEmbedder, embedder_from_config
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
) -> list[Passage]:
    points = store.hybrid_query(
        dense=embedder.embed([query])[0],
        sparse=sparse_vector(query, is_query=True),
        limit=k,
        prefetch_limit=max(prefetch_limit, k),
        filters=filters,
    )
    return [
        Passage.model_validate({**pt["payload"], "rerank_score": round(pt["score"], 4)})
        for pt in points
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
