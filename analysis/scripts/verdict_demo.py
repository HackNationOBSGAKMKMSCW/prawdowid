"""SYNC 2: werdykty (stance + reguły) z prawdziwym LLM i ocena, czy pasaże wystarczają.

.venv/Scripts/python scripts/verdict_demo.py                  # atrapa retrievera (rag/mock.py)
.venv/Scripts/python scripts/verdict_demo.py --source sample  # data/samples/sample_input.json
.venv/Scripts/python scripts/verdict_demo.py --source sample --k 3 --chunk-chars 400

`--source sample` tnie źródła z sample_input.json chunkingiem osoby A (`build_payloads`,
pasaże ~800 znaków jak w Qdrancie) i wybiera top-k pasaży prostym rankingiem po tokenach
z `rag/sparse.py`, bez sieci i bez Qdranta. Dzięki temu sprawdzamy stance i cytaty na
pasażach docelowej długości, zanim prawdziwy retriever będzie gotowy.

Wymaga w analysis/.env konfiguracji FreeLLMAPI (OPENAI_BASE_URL, OPENAI_API_KEY, LLM_MODEL).
Wynik (AnalysisOutput) zapisuje do outputs/ (gitignored).
"""

import argparse
import json
import statistics
import sys
import time
from collections import Counter
from pathlib import Path

from prawdowid_analysis.rag.ingest import build_payloads
from prawdowid_analysis.rag.mock import mock_retrieve
from prawdowid_analysis.rag.sparse import tokenize
from prawdowid_analysis.schemas import (
    AnalysisInput,
    AnalysisOutput,
    Claim,
    ClaimResult,
    IngestReport,
    Passage,
)
from prawdowid_analysis.verdict.llm import FreeLLMClient, LLMError
from prawdowid_analysis.verdict.rules import aggregate
from prawdowid_analysis.verdict.security import (
    SecurityEvent,
    screen_passages,
    security_limitations,
)
from prawdowid_analysis.verdict.sources import tier_of
from prawdowid_analysis.verdict.stance import StanceAssessment, build_evidence

ROOT = Path(__file__).resolve().parents[1]
SAMPLE = ROOT / "data" / "samples" / "sample_input.json"
OUTPUTS = ROOT / "outputs"

# Fikcyjne twierdzenia pod dokumenty atrapy (rag/mock.py).
MOCK_CLAIMS = [
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


def sample_corpus(chunk_chars: int) -> tuple[list[Claim], list[Passage]]:
    data = AnalysisInput.model_validate(json.loads(SAMPLE.read_text(encoding="utf-8")))
    passages: dict[str, Passage] = {}
    for src in data.sources:
        for payload in build_payloads(src, max_chars=chunk_chars):
            passages.setdefault(
                payload["chunk_id"], Passage.model_validate({**payload, "rerank_score": 0.0})
            )
    return data.claims, list(passages.values())


def local_retrieve(corpus: list[Passage], query: str, k: int) -> list[Passage]:
    """Zastępczy ranking: pokrycie tokenów zapytania (stemming PL z rag/sparse.py)."""
    q = set(tokenize(query))
    scored = []
    for p in corpus:
        overlap = len(q & set(tokenize(p.title + " " + p.text))) / max(len(q), 1)
        scored.append(p.model_copy(update={"rerank_score": round(overlap, 3)}))
    scored.sort(key=lambda p: (-p.rerank_score, p.chunk_id))
    return [p for p in scored[:k] if p.rerank_score > 0]


def describe_passage(p: Passage) -> str:
    missing = [n for n in ("published_at", "publisher", "title") if not getattr(p, n)]
    meta = f" BRAK: {','.join(missing)}" if missing else ""
    return (
        f"{p.chunk_id:<24} T{tier_of(p)} {p.source_type:<16} {p.published_at or '----------'} "
        f"{len(p.text):>4} zn. score={p.rerank_score:.2f}{meta}"
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", choices=["mock", "sample"], default="mock")
    parser.add_argument("--k", type=int, default=4, help="pasaży na twierdzenie")
    parser.add_argument("--chunk-chars", type=int, default=800, help="tylko --source sample")
    parser.add_argument(
        "--no-screen",
        action="store_true",
        help="nie odrzucaj pasaży z wstrzyknięciem (test odporności samego promptu)",
    )
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")

    try:
        client = FreeLLMClient.from_env()
    except LLMError as exc:
        print(f"[FAIL] {exc}")
        return 1
    screen = not args.no_screen
    print(
        f"LLM_MODEL={client.model}  źródło={args.source}  k={args.k}  "
        f"filtr wstrzyknięć={'tak' if screen else 'NIE'}"
    )

    if args.source == "sample":
        claims, corpus = sample_corpus(args.chunk_chars)

        def retrieve(q: str) -> list[Passage]:
            return local_retrieve(corpus, q, args.k)
    else:
        claims = MOCK_CLAIMS

        def retrieve(q: str) -> list[Passage]:
            return mock_retrieve(q, k=args.k)

    results: list[ClaimResult] = []
    all_assessments: list[StanceAssessment] = []
    all_passages: dict[str, Passage] = {}
    claim_ms: list[int] = []
    all_events: list[SecurityEvent] = []
    for claim in claims:
        print(f"\n== {claim.claim_id} [{claim.type}]: {claim.text}")
        passages = retrieve(claim.text)
        for p in passages:
            all_passages[p.chunk_id] = p
        started = time.perf_counter()
        clean, events = screen_passages(passages, claim_id=claim.claim_id)
        all_events += events
        to_llm = clean if screen else passages
        assessments: list[StanceAssessment] = []
        evidence = []
        if claim.type == "opinion" or not claim.check_worthy:
            verdict = aggregate(claim, [], passages)  # opinii nie wysyłamy do LLM
        else:
            try:
                evidence, assessments = build_evidence(claim, to_llm, client)
                verdict = aggregate(claim, evidence, to_llm)
            except LLMError as exc:
                verdict = aggregate(claim, [], to_llm, error=f"{exc.kind}: {exc}")
        if screen and events:
            verdict = verdict.model_copy(
                update={"limitations": verdict.limitations + security_limitations(events)}
            )
        claim_ms.append(int((time.perf_counter() - started) * 1000))
        all_assessments += assessments

        by_chunk = {a.chunk_id: a for a in assessments}
        flagged = {e.chunk_id: e for e in events}
        for p in passages:
            print("  " + describe_passage(p))
            if p.chunk_id in flagged:
                verb = "ODRZUCONY" if screen else "WYKRYTO, ale wysłano do LLM"
                print(f"    !! {verb}: wstrzyknięcie {flagged[p.chunk_id].patterns}")
            a = by_chunk.get(p.chunk_id)
            if a:
                mark = "OK " if a.quote_verified else ("ZLY" if a.quote else " - ")
                fb = " [fallback: zły JSON]" if not a.parse_ok else ""
                print(
                    f"    -> {a.stance:<12} cytat[{mark}] {a.quote[:90]!r}"
                    f"  ({a.llm.model}, {a.llm.duration_ms} ms){fb}"
                )
        s = verdict.strength
        print(
            f"  WERDYKT: {verdict.outcome_class}/{verdict.outcome}"
            f"  siła={s.level if s else '-'}  flagi={verdict.flags or '-'}"
            f"  przekazanie={'tak' if verdict.handover.recommended else 'nie'}"
        )
        print(f"  {verdict.explanation_pl}")
        if s:
            print(f"  czynniki: {'; '.join(s.factors)}")
        if verdict.limitations:
            print(f"  ograniczenia: {'; '.join(verdict.limitations)}")
        results.append(
            ClaimResult(claim=claim, passages=passages, evidence=evidence, verdict=verdict)
        )

    report(results, all_assessments, list(all_passages.values()), claim_ms)
    docs = sorted({e.doc_id for e in all_events})
    print(f"Zdarzenia bezpieczeństwa (security_events): {len(all_events)}, dokumenty: {docs}")
    OUTPUTS.mkdir(exist_ok=True)
    out = OUTPUTS / f"verdict_demo_{args.source}.json"
    output = AnalysisOutput(
        request_id=f"demo_{args.source}", results=results, ingest=IngestReport()
    )
    out.write_text(output.model_dump_json(indent=2), encoding="utf-8")
    events_out = OUTPUTS / f"security_events_{args.source}.json"
    events_out.write_text(
        json.dumps([e.to_dict() for e in all_events], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"\nZapisano: {out.relative_to(ROOT)}, {events_out.relative_to(ROOT)}")
    return 0


def report(
    results: list[ClaimResult],
    assessments: list[StanceAssessment],
    passages: list[Passage],
    claim_ms: list[int],
) -> None:
    """Podsumowanie na SYNC 2: czy pasaże (długość, metadane) wystarczają do stance i cytatów."""
    print("\n" + "=" * 78 + "\nPODSUMOWANIE")
    lengths = [len(p.text) for p in passages]
    if lengths:
        print(
            f"Pasaże: {len(passages)}, długość min/mediana/max = {min(lengths)}/"
            f"{int(statistics.median(lengths))}/{max(lengths)} znaków"
        )
    no_date = sum(1 for p in passages if not p.published_at)
    print(
        f"Metadane: bez published_at {no_date}/{len(passages)}; "
        f"typy źródeł {dict(Counter(p.source_type for p in passages))}"
    )
    decisive = [a for a in assessments if a.stance in ("supports", "refutes")]
    verified = [a for a in decisive if a.quote_verified]
    fallbacks = sum(1 for a in assessments if not a.parse_ok)
    print(
        f"Stanowiska: {dict(Counter(a.stance for a in assessments))}; "
        f"zły JSON (fallback): {fallbacks}/{len(assessments)}"
    )
    if decisive:
        by_chunk = {p.chunk_id: p for p in passages}
        ratios = [len(a.quote) / max(len(by_chunk[a.chunk_id].text), 1) for a in verified]
        print(
            f"Cytaty: zweryfikowane {len(verified)}/{len(decisive)} rozstrzygających"
            + (f"; cytat to mediana {statistics.median(ratios):.0%} pasażu" if ratios else "")
        )
    if assessments:
        calls = [a.llm.duration_ms for a in assessments]
        tok_in = [a.llm.tokens_in for a in assessments]
        print(
            f"LLM: {len(calls)} wywołań, mediana {int(statistics.median(calls))} ms, "
            f"max {max(calls)} ms; tokeny wejścia mediana {int(statistics.median(tok_in))}; "
            f"modele {dict(Counter(a.llm.model for a in assessments))}"
        )
    if claim_ms:
        print(f"Czas na twierdzenie: mediana {statistics.median(claim_ms) / 1000:.1f} s")
    outcomes = Counter(r.verdict.outcome for r in results if r.verdict)
    print(f"Werdykty: {dict(outcomes)}")


if __name__ == "__main__":
    sys.exit(main())
