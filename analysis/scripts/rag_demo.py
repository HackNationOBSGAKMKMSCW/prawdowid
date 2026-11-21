"""Demo RAG: ingest źródeł z pliku wejściowego + retrieve top-k dla każdego twierdzenia.

    .venv/Scripts/python scripts/rag_demo.py data/samples/sample_input.json
    .venv/Scripts/python scripts/rag_demo.py data/samples/sample_input.json --reset

Pierwszy przebieg: `added=N, skipped=1` (duplikat URL), drugi: wszystko `skipped`.
Wynik zapisywany do `outputs/` (gitignored).
"""

import argparse
import json
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

from prawdowid_analysis.rag.config import load_config
from prawdowid_analysis.rag.embed import embedder_from_config
from prawdowid_analysis.rag.ingest import ingest_sources
from prawdowid_analysis.rag.retriever import search
from prawdowid_analysis.rag.store import store_from_config
from prawdowid_analysis.schemas import AnalysisInput

OUTPUTS = Path(__file__).resolve().parents[1] / "outputs"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("input", type=Path)
    ap.add_argument("-k", type=int, default=6)
    ap.add_argument("--reset", action="store_true", help="usuń kolekcję przed ingestem")
    ap.add_argument("--chars", type=int, default=160, help="ile znaków pasażu wypisać")
    args = ap.parse_args()

    sys.stdout.reconfigure(encoding="utf-8")
    data = AnalysisInput.model_validate(json.loads(args.input.read_text(encoding="utf-8")))
    cfg = load_config()
    store, embedder = store_from_config(cfg), embedder_from_config(cfg)
    print(f"Qdrant: kolekcja {cfg.collection!r}, embeddingi: {cfg.embedding_model}")

    if args.reset and store.collection_exists():
        store.drop_collection()
        print("Usunięto kolekcję.")

    t0 = time.perf_counter()
    report = ingest_sources(data.sources, store, embedder, max_chars=cfg.chunk_chars)
    print(
        f"Ingest: added={report.added} skipped={report.skipped} replaced={report.replaced} "
        f"({time.perf_counter() - t0:.2f} s, punktów w kolekcji: {store.count()})\n"
    )

    results = []
    for claim in data.claims:
        t1 = time.perf_counter()
        passages = search(claim.text, store, embedder, k=args.k, prefetch_limit=cfg.prefetch_limit)
        dt = time.perf_counter() - t1
        print(f"── {claim.claim_id} [{claim.type}] {claim.text}  ({dt:.2f} s)")
        for rank, p in enumerate(passages, 1):
            snippet = p.text.replace("\n", " ")[: args.chars]
            print(f"  {rank}. {p.rerank_score:.4f}  {p.chunk_id}  [{p.source_type}] {p.title}")
            print(f"       {snippet}")
        print()
        results.append(
            {
                "claim": claim.model_dump(),
                "passages": [p.model_dump() for p in passages],
                "latency_s": round(dt, 3),
            }
        )

    OUTPUTS.mkdir(exist_ok=True)
    out = OUTPUTS / f"rag_demo_{datetime.now(UTC):%Y%m%dT%H%M%SZ}.json"
    out.write_text(
        json.dumps(
            {"request_id": data.request_id, "ingest": report.model_dump(), "results": results},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"Zapisano: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
