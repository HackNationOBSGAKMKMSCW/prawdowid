"""Metryki retrievera na poziomie dokumentów: recall@k, hit@1, MRR, separacja wyników.

Oczekiwane dokumenty podajemy jako URL-e (porównanie po `make_doc_id`, więc odporne na
parametry śledzące, wielkość liter itp.). Twierdzenia bez oczekiwanych dokumentów służą
do oceny, czy `rerank_score` pozwala się wstrzymać (najlepszy wynik powinien być niski).
"""

from dataclasses import dataclass
from statistics import mean

from ..schemas import Passage
from .ingest import make_doc_id


@dataclass(frozen=True)
class ClaimRetrievalResult:
    claim_id: str
    expected: frozenset[str]  # doc_id
    ranked_docs: tuple[str, ...]  # doc_id w kolejności pierwszego wystąpienia
    top_score: float

    @property
    def recall(self) -> float | None:
        if not self.expected:
            return None
        return len(self.expected & set(self.ranked_docs)) / len(self.expected)

    @property
    def reciprocal_rank(self) -> float | None:
        if not self.expected:
            return None
        for rank, doc in enumerate(self.ranked_docs, 1):
            if doc in self.expected:
                return 1.0 / rank
        return 0.0


def evaluate_claim(claim_id: str, expected_urls: list[str], passages: list[Passage]):
    ranked: list[str] = []
    for p in passages:
        if p.doc_id not in ranked:
            ranked.append(p.doc_id)
    return ClaimRetrievalResult(
        claim_id=claim_id,
        expected=frozenset(make_doc_id(u) for u in expected_urls),
        ranked_docs=tuple(ranked),
        top_score=max((p.rerank_score for p in passages), default=0.0),
    )


def summarize(results: list[ClaimRetrievalResult]) -> dict:
    answerable = [r for r in results if r.expected]
    unanswerable = [r for r in results if not r.expected]
    hits = [r for r in answerable if r.ranked_docs and r.ranked_docs[0] in r.expected]
    summary = {
        "n_claims": len(results),
        "n_answerable": len(answerable),
        "recall_at_k": round(mean(r.recall for r in answerable), 4) if answerable else None,
        "hit_at_1": round(len(hits) / len(answerable), 4) if answerable else None,
        "mrr": round(mean(r.reciprocal_rank for r in answerable), 4) if answerable else None,
        # separacja: najsłabsze trafienie vs najmocniejszy wynik bez pokrycia w źródłach
        "min_top_score_answerable": round(min((r.top_score for r in hits), default=0.0), 4),
        "max_top_score_unanswerable": (
            round(max(r.top_score for r in unanswerable), 4) if unanswerable else None
        ),
    }
    return summary
