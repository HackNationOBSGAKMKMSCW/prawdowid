"""Kolekcja Qdrant przez REST (httpx), bez qdrant-client (grpcio bywa problemem na Py 3.15).

Kolekcja: wektor gęsty `dense` (cosine) + rzadki `bm25` z `modifier: idf`.
Payload punktu = pola `Passage` (bez `rerank_score`) + `chunk_index`, `injection_flags`.
"""

from typing import Any, Protocol

import httpx

DENSE = "dense"
SPARSE = "bm25"
KEYWORD_INDEXES = ("doc_id", "source_type", "published_at", "url")


class VectorStore(Protocol):
    def ensure_collection(self, dim: int) -> None: ...
    def get_doc_hash(self, doc_id: str) -> str | None: ...
    def delete_doc(self, doc_id: str) -> None: ...
    def upsert(self, points: list[dict[str, Any]]) -> None: ...


def _filter(filters: dict | None) -> dict | None:
    """`{"source_type": ["official_primary"], "doc_id": "doc_x"}` -> filtr Qdrant."""
    if not filters:
        return None
    must = []
    for key, value in filters.items():
        if value is None:
            continue
        if isinstance(value, list | tuple | set):
            must.append({"key": key, "match": {"any": list(value)}})
        else:
            must.append({"key": key, "match": {"value": value}})
    return {"must": must} if must else None


class QdrantStore:
    def __init__(self, url: str, collection: str, api_key: str | None = None, timeout_s=60.0):
        headers = {"api-key": api_key} if api_key else {}
        self.collection = collection
        self._c = httpx.Client(base_url=url, headers=headers, timeout=timeout_s)

    # ── pomocnicze ──
    def _req(self, method: str, path: str, **kw) -> dict:
        resp = self._c.request(method, path, **kw)
        if resp.status_code >= 400:
            raise RuntimeError(f"Qdrant {method} {path}: {resp.status_code} {resp.text[:300]}")
        return resp.json()

    @property
    def _base(self) -> str:
        return f"/collections/{self.collection}"

    # ── zarządzanie kolekcją ──
    def collection_exists(self) -> bool:
        return bool(self._req("GET", f"{self._base}/exists")["result"]["exists"])

    def ensure_collection(self, dim: int) -> None:
        if self.collection_exists():
            info = self._req("GET", self._base)["result"]
            size = info["config"]["params"]["vectors"][DENSE]["size"]
            if size != dim:
                raise RuntimeError(
                    f"Kolekcja {self.collection!r} ma wymiar {size}, model daje {dim}: "
                    "zmiana modelu embeddingów wymaga nowej kolekcji (reindeks)."
                )
            return
        self._req(
            "PUT",
            self._base,
            json={
                "vectors": {DENSE: {"size": dim, "distance": "Cosine"}},
                "sparse_vectors": {SPARSE: {"modifier": "idf"}},
            },
        )
        for field in KEYWORD_INDEXES:
            self._req(
                "PUT",
                f"{self._base}/index",
                params={"wait": "true"},
                json={"field_name": field, "field_schema": "keyword"},
            )

    def drop_collection(self) -> None:
        self._req("DELETE", self._base)

    # ── dokumenty ──
    def get_doc_hash(self, doc_id: str) -> str | None:
        """Hash zapisanego dokumentu; None, gdy go nie ma (także gdy brak kolekcji)."""
        if not self.collection_exists():
            return None
        res = self._req(
            "POST",
            f"{self._base}/points/scroll",
            json={
                "filter": _filter({"doc_id": doc_id}),
                "limit": 1,
                "with_payload": ["text_hash"],
                "with_vector": False,
            },
        )["result"]["points"]
        return res[0]["payload"]["text_hash"] if res else None

    def delete_doc(self, doc_id: str) -> None:
        self._req(
            "POST",
            f"{self._base}/points/delete",
            params={"wait": "true"},
            json={"filter": _filter({"doc_id": doc_id})},
        )

    def upsert(self, points: list[dict[str, Any]]) -> None:
        for i in range(0, len(points), 64):
            self._req(
                "PUT",
                f"{self._base}/points",
                params={"wait": "true"},
                json={"points": points[i : i + 64]},
            )

    # ── wyszukiwanie ──
    def hybrid_query(
        self,
        dense: list[float],
        sparse: dict[str, list],
        limit: int,
        prefetch_limit: int,
        filters: dict | None = None,
    ) -> list[dict]:
        flt = _filter(filters)
        prefetch = [{"query": dense, "using": DENSE, "limit": prefetch_limit, "filter": flt}]
        if sparse["indices"]:
            prefetch.append(
                {"query": sparse, "using": SPARSE, "limit": prefetch_limit, "filter": flt}
            )
        body = {
            "prefetch": prefetch,
            "query": {"fusion": "rrf"},
            "limit": limit,
            "with_payload": True,
        }
        return self._req("POST", f"{self._base}/points/query", json=body)["result"]["points"]

    def count(self) -> int:
        return self._req("POST", f"{self._base}/points/count", json={"exact": True})["result"][
            "count"
        ]


def store_from_config(cfg) -> QdrantStore:
    return QdrantStore(cfg.qdrant_url, cfg.collection, cfg.qdrant_api_key, cfg.timeout_s)
