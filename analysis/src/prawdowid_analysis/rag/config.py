"""Konfiguracja RAG z `.env` (analysis/.env). Żadnych adresów ani kluczy w kodzie."""

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

# analysis/.env: trzy poziomy nad tym plikiem (rag -> prawdowid_analysis -> src -> analysis)
_ENV_PATH = Path(__file__).resolve().parents[3] / ".env"


@dataclass(frozen=True)
class RagConfig:
    qdrant_url: str
    qdrant_api_key: str | None
    collection: str
    embedding_base_url: str
    embedding_api_key: str | None
    embedding_model: str
    chunk_chars: int = 800
    prefetch_limit: int = 30
    timeout_s: float = 60.0


def load_config() -> RagConfig:
    load_dotenv(_ENV_PATH, override=False)

    def env(name: str, default: str | None = None) -> str | None:
        value = os.getenv(name, default)
        return value.strip() if value and value.strip() else default

    base_url = env("EMBEDDING_BASE_URL") or env("OPENAI_BASE_URL")
    model = env("EMBEDDING_MODEL")
    if not base_url or not model:
        raise RuntimeError(
            "Brak konfiguracji embeddingów: ustaw OPENAI_BASE_URL (lub EMBEDDING_BASE_URL) "
            "i EMBEDDING_MODEL w analysis/.env"
        )
    return RagConfig(
        qdrant_url=env("QDRANT_URL", "http://localhost:6333").rstrip("/"),
        qdrant_api_key=env("QDRANT_API_KEY"),
        collection=env("QDRANT_COLLECTION", "prawdowid_passages"),
        embedding_base_url=base_url.rstrip("/"),
        embedding_api_key=env("EMBEDDING_API_KEY") or env("OPENAI_API_KEY"),
        embedding_model=model,
        chunk_chars=int(env("CHUNK_CHARS", "800")),
        prefetch_limit=int(env("PREFETCH_LIMIT", "30")),
    )
