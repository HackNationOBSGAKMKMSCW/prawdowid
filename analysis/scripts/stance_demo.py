"""Stance + werdykt na atrapie retrievera z prawdziwym LLM; pomiar czasu generacji.

.venv/Scripts/python scripts/stance_demo.py            # wszystkie twierdzenia
.venv/Scripts/python scripts/stance_demo.py --k 2      # mniej pasaży na twierdzenie

Wymaga w analysis/.env: OPENAI_BASE_URL, LLM_MODEL i OPENAI_API_KEY (dla FreeLLMAPI:
`http://<host>:3001/v1`, klucz `freellmapi-…`, model `auto`/`auto:<profil>` lub przypięty).
Wypisuje stanowisko i cytat dla każdego pasażu, werdykt dla twierdzenia oraz czasy:
na wywołanie, na twierdzenie i medianę (cel z zadania: mediana <= 30 s na zgłoszenie).
"""

import argparse
import statistics
import sys
import time

from prawdowid_analysis.rag.mock import mock_retrieve
from prawdowid_analysis.schemas import Claim
from prawdowid_analysis.verdict.llm import FreeLLMClient, LLMError, is_router_model
from prawdowid_analysis.verdict.rules import aggregate
from prawdowid_analysis.verdict.stance import build_evidence

# Fikcyjne twierdzenia pod dokumenty atrapy (rag/mock.py).
CLAIMS = [
    Claim(
        claim_id="clm_demo_1",
        text="Od 2027 r. wniosek paszportowy można złożyć w dowolnym urzędzie wojewódzkim.",
        type="legal",
        check_worthy=True,
    ),
    Claim(
        claim_id="clm_demo_2",
        text="Opłata za paszport dla dorosłych wzrośnie trzykrotnie.",
        type="numeric",
        check_worthy=True,
    ),
    Claim(
        claim_id="clm_demo_3",
        text="W 2025 r. wydano 2,4 mln paszportów.",
        type="numeric",
        check_worthy=True,
    ),
    Claim(
        claim_id="clm_demo_4",
        text="Paszport można odebrać w jeden dzień.",
        type="event",
        check_worthy=True,
    ),
]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--k", type=int, default=4, help="pasaży na twierdzenie")
    args = parser.parse_args()

    try:
        client = FreeLLMClient.from_env()
        models = client.list_models()
    except LLMError as exc:
        print(f"[FAIL] {exc}")
        return 1
    print(f"LLM_MODEL: {client.model}; dostępnych modeli z aktywnym kluczem: {len(models)}")
    if not is_router_model(client.model) and client.model not in models:
        print(f"[FAIL] Model {client.model} nie jest dostępny (brak klucza lub limitu).")
        return 1

    call_ms: list[int] = []
    claim_ms: list[int] = []
    tokens_out: list[int] = []
    models_used: dict[str, int] = {}  # przy `auto` router może zmieniać model między wywołaniami
    for claim in CLAIMS:
        print(f"\n== {claim.claim_id}: {claim.text}")
        passages = mock_retrieve(claim.text, k=args.k)
        started = time.perf_counter()
        try:
            evidence, assessments = build_evidence(claim, passages, client)
            verdict = aggregate(claim, evidence, passages)
        except LLMError as exc:
            verdict = aggregate(claim, [], passages, error=f"{exc.kind}: {exc}")
            assessments = []
        claim_ms.append(int((time.perf_counter() - started) * 1000))
        for a in assessments:
            call_ms.append(a.llm.duration_ms)
            tokens_out.append(a.llm.tokens_out)
            mark = "OK " if a.quote_verified else ("ZLY" if a.quote else "   ")
            json_flag = "" if a.parse_ok else " [fallback: zły JSON]"
            failover = f", failover x{a.llm.fallback_attempts}" if a.llm.fallback_attempts else ""
            print(
                f"  {a.chunk_id:<16} {a.stance:<12} cytat[{mark}] {a.quote[:70]!r}\n"
                f"  {'':<16} {a.llm.model} ({a.llm.duration_ms} ms, "
                f"{a.llm.tokens_in}->{a.llm.tokens_out} tok{failover}){json_flag}"
            )
            models_used[a.llm.model] = models_used.get(a.llm.model, 0) + 1
        print(f"  WERDYKT: {verdict.outcome_class}/{verdict.outcome}  {verdict.explanation_pl}")

    if call_ms:
        total_s = sum(call_ms) / 1000
        print(
            f"\nWywołania: {len(call_ms)}, mediana {statistics.median(call_ms)} ms, "
            f"max {max(call_ms)} ms, ~{sum(tokens_out) / max(total_s, 1e-9):.1f} tok/s wyjścia"
        )
    print(f"Na twierdzenie (k={args.k}): mediana {statistics.median(claim_ms) / 1000:.1f} s")
    print(f"Modele, które faktycznie odpowiedziały (X-Routed-Via): {models_used}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
