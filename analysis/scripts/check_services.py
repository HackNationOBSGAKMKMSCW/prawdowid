"""Sprawdza połączenie z Qdrantem i endpointem embeddingów z analysis/.env.

.venv/Scripts/python scripts/check_services.py
"""

import sys
import time

import httpx

from prawdowid_analysis.rag.config import load_config


def main() -> int:
    cfg = load_config()
    ok = True

    headers = {"api-key": cfg.qdrant_api_key} if cfg.qdrant_api_key else {}
    try:
        r = httpx.get(f"{cfg.qdrant_url}/collections", headers=headers, timeout=10)
        r.raise_for_status()
        names = [c["name"] for c in r.json()["result"]["collections"]]
        print(f"[OK]   Qdrant: kolekcje {names}")
    except Exception as e:  # noqa: BLE001
        ok = False
        print(f"[FAIL] Qdrant ({cfg.qdrant_url}): {e}")

    auth = {"Authorization": f"Bearer {cfg.embedding_api_key}"} if cfg.embedding_api_key else {}
    try:
        r = httpx.get(f"{cfg.embedding_base_url}/models", headers=auth, timeout=10)
        r.raise_for_status()
        models = [m["id"] for m in r.json().get("data", [])]
        print(f"[OK]   Modele: {models}")
        t0 = time.perf_counter()
        r = httpx.post(
            f"{cfg.embedding_base_url}/embeddings",
            headers=auth,
            json={"model": cfg.embedding_model, "input": ["Test embeddingu po polsku."]},
            timeout=120,
        )
        r.raise_for_status()
        dim = len(r.json()["data"][0]["embedding"])
        dt = time.perf_counter() - t0
        print(f"[OK]   Embedding {cfg.embedding_model}: wymiar {dim}, {dt:.2f} s")
    except Exception as e:  # noqa: BLE001
        ok = False
        print(f"[FAIL] Embeddingi ({cfg.embedding_base_url}, {cfg.embedding_model}): {e}")

    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
