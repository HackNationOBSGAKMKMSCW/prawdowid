"""Ewaluacja retrievera: recall@k, hit@1, MRR i separacja `rerank_score`.

    .venv/Scripts/python scripts/eval_retrieval.py data/samples/sample_input.json \
        data/samples/sample_retrieval_expected.jsonl -k 6

Zakłada, że źródła z pliku wejściowego są już w indeksie (np. po `rag_demo.py`);
z `--ingest` najpierw je dokłada (z pomijaniem duplikatów).
"""

import argparse
import json
import sys
from pathlib import Path

from prawdowid_analysis.rag.config import load_config
from prawdowid_analysis.rag.embed import embedder_from_config
from prawdowid_analysis.rag.ingest import ingest_sources, make_doc_id
from prawdowid_analysis.rag.metrics import evaluate_claim, summarize
from prawdowid_analysis.rag.retriever import search
from prawdowid_analysis.rag.store import store_from_config
from prawdowid_analysis.schemas import AnalysisInput


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("input", type=Path)
    ap.add_argument("expected", type=Path)
    ap.add_argument("-k", type=int, default=6)
    ap.add_argument("--ingest", action="store_true")
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")

    data = AnalysisInput.model_validate(json.loads(args.input.read_text(encoding="utf-8")))
    expected = {
        row["claim_id"]: row["expected_urls"]
        for row in map(json.loads, args.expected.read_text(encoding="utf-8").splitlines())
        if row
    }
    cfg = load_config()
    store, embedder = store_from_config(cfg), embedder_from_config(cfg)
    if args.ingest:
        print("Ingest:", ingest_sources(data.sources, store, embedder, max_chars=cfg.chunk_chars))

    titles = {make_doc_id(s.url): s.title for s in data.sources}
    results = []
    for claim in data.claims:
        if claim.claim_id not in expected:
            continue
        passages = search(claim.text, store, embedder, k=args.k, prefetch_limit=cfg.prefetch_limit)
        r = evaluate_claim(claim.claim_id, expected[claim.claim_id], passages)
        results.append(r)
        status = f"recall={r.recall:.2f} RR={r.reciprocal_rank:.2f}" if r.expected else "bez źródła"
        print(f"{claim.claim_id}  top={r.top_score:.3f}  {status}")
        missed = r.expected - set(r.ranked_docs)
        for doc in missed:
            print(f"    brak w top-{args.k}: {titles.get(doc, doc)}")

    print("\n" + json.dumps(summarize(results), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
