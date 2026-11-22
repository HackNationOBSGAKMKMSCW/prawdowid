"""Rerank raw hits from all sources against the claim's search queries.

Site search engines (gov.pl) match words with OR, and listings/feeds are not
query-aware at all, so every hit is re-scored locally:

* a hit must cover the query's content words (all of a one- or two-word query,
  2 of 3, half of a longer one) for at least one query;
* survivors are ordered by BM25 over title + snippet + URL slug, with a small
  bonus for fact-checkers and recent publications;
* the URL must belong to the source's whitelisted domains, duplicates (same
  URL or same title) are merged and per-source/total limits apply.
"""

import math
from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from urllib.parse import urlsplit

from articleScraping.url_validation import InvalidUrlError, validate_url

from .models import EvidenceHit, TrustedSource
from .text import stems, url_words

_K1 = 1.2
_B = 0.75


@dataclass(frozen=True)
class RankedQuery:
    text: str
    stems: frozenset[str]

    @property
    def required(self) -> int:
        size = len(self.stems)
        if size <= 2:
            return size
        return math.ceil(0.6 * size) if size == 3 else math.ceil(0.5 * size)


def prepare_queries(queries: Iterable[str]) -> list[RankedQuery]:
    prepared: list[RankedQuery] = []
    seen: set[frozenset[str]] = set()
    for query in queries:
        query_stems = frozenset(stems(query))
        if query_stems and query_stems not in seen:
            seen.add(query_stems)
            prepared.append(RankedQuery(query, query_stems))
    return prepared


def _document(hit: EvidenceHit) -> list[str]:
    return stems(f"{hit.title} {hit.title} {hit.snippet} {url_words(hit.url)}")


def coverage_ok(query: RankedQuery, document: set[str], *, relaxed: bool = False) -> bool:
    matched = len(query.stems & document)
    needed = max(1, math.ceil(len(query.stems) / 2)) if relaxed else query.required
    return matched >= needed


def _recency_bonus(published_at: datetime | None, now: datetime) -> float:
    if published_at is None:
        return 0.0
    moment = published_at if published_at.tzinfo else published_at.replace(tzinfo=UTC)
    age_days = max(0.0, (now - moment).total_seconds() / 86_400)
    return 0.3 * math.exp(-age_days / 365)


def rank_hits(
    hits: Sequence[EvidenceHit],
    queries: Sequence[str],
    sources: dict[str, TrustedSource],
    *,
    relaxed_sources: frozenset[str] = frozenset(),
    max_hits: int = 10,
    max_hits_per_source: int = 3,
    now: datetime | None = None,
) -> list[EvidenceHit]:
    """Filter, score and limit hits; returns at most ``max_hits`` in score order.

    ``relaxed_sources`` holds source ids whose results are already ranked by the
    provider against the claim (fact-check search), so half coverage suffices.
    """

    prepared = prepare_queries(queries)
    if not prepared:
        return []
    now = now or datetime.now(UTC)

    candidates: list[tuple[EvidenceHit, list[str]]] = []
    for hit in hits:
        source = sources.get(hit.source_id)
        if source is None:
            continue
        try:
            canonical = validate_url(hit.url)
        except InvalidUrlError:
            continue
        if not source.owns_url(urlsplit(canonical).hostname):
            continue
        candidates.append((hit.model_copy(update={"url": canonical}), _document(hit)))
    if not candidates:
        return []

    document_count = len(candidates)
    average_length = sum(len(doc) for _, doc in candidates) / document_count or 1.0
    frequency: Counter[str] = Counter()
    for _, doc in candidates:
        frequency.update(set(doc))

    def bm25(query: RankedQuery, doc: list[str]) -> float:
        counts = Counter(doc)
        score = 0.0
        for term in query.stems:
            tf = counts.get(term, 0)
            if not tf:
                continue
            idf = math.log(1 + (document_count - frequency[term] + 0.5) / (frequency[term] + 0.5))
            norm = tf * (_K1 + 1) / (tf + _K1 * (1 - _B + _B * len(doc) / average_length))
            score += idf * norm
        return score

    scored: dict[str, EvidenceHit] = {}
    for hit, doc in candidates:
        doc_set = set(doc)
        relaxed = hit.kind == "reference" or hit.source_id in relaxed_sources
        best: tuple[float, str] | None = None
        for query in prepared:
            if not coverage_ok(query, doc_set, relaxed=relaxed):
                continue
            value = bm25(query, doc) / max(1, len(query.stems))
            if best is None or value > best[0]:
                best = (value, query.text)
        if best is None:
            continue
        bonus = 0.2 if hit.trust == "fact_checker" else 0.0
        bonus += _recency_bonus(hit.published_at, now)
        if hit.kind == "reference":
            bonus -= 0.5  # live dashboards are context, not evidence
        ranked = hit.model_copy(update={"score": round(best[0] + bonus, 4), "query": best[1]})
        previous = scored.get(ranked.url)
        if previous is None or ranked.score > previous.score:
            scored[ranked.url] = ranked

    ordered = sorted(scored.values(), key=lambda item: item.score, reverse=True)
    per_source: Counter[str] = Counter()
    selected: list[EvidenceHit] = []
    seen_titles: set[str] = set()
    for hit in ordered:
        title_key = " ".join(stems(hit.title))
        if per_source[hit.source_id] >= max_hits_per_source or (title_key and title_key in seen_titles):
            continue
        seen_titles.add(title_key)
        per_source[hit.source_id] += 1
        selected.append(hit)
        if len(selected) >= max_hits:
            break
    return selected
