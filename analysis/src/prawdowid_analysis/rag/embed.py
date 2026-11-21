"""Embeddingi przez API zgodne z OpenAI (`POST {base_url}/embeddings`), np. Ollama /v1."""

from typing import Protocol

import httpx


class Embedder(Protocol):
    model: str

    def embed(self, texts: list[str]) -> list[list[float]]: ...


class OpenAIEmbedder:
    def __init__(
        self,
        base_url: str,
        model: str,
        api_key: str | None = None,
        batch_size: int = 32,
        timeout_s: float = 60.0,
    ) -> None:
        self.model = model
        self.batch_size = batch_size
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        self._client = httpx.Client(base_url=base_url, headers=headers, timeout=timeout_s)

    def embed(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for i in range(0, len(texts), self.batch_size):
            batch = texts[i : i + self.batch_size]
            resp = self._client.post("/embeddings", json={"model": self.model, "input": batch})
            resp.raise_for_status()
            data = sorted(resp.json()["data"], key=lambda d: d["index"])
            vectors.extend(d["embedding"] for d in data)
        return vectors

    def embed_one(self, text: str) -> list[float]:
        return self.embed([text])[0]


def embedder_from_config(cfg) -> OpenAIEmbedder:
    return OpenAIEmbedder(
        base_url=cfg.embedding_base_url,
        model=cfg.embedding_model,
        api_key=cfg.embedding_api_key,
        timeout_s=cfg.timeout_s,
    )
