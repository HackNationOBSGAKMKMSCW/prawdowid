"""Część A: wyciąganie i oznaczanie fragmentów manipulacyjnych (taksonomia A–G)."""

from __future__ import annotations

import math
import re
from collections.abc import Sequence
from datetime import date

from . import prompts
from .llm import StructuredCall, structured_call
from .models import (
    CATEGORY_CODES,
    LLMManipulationResponse,
    ManipulationFragment,
    ManipulationResult,
    SourceEvidence,
    TruthSource,
)
from .spans import locate_quote

MIN_CONFIDENCE = 0.3  # niżej fragment jest odrzucany jako szum
DETECTION_CONFIDENCE = 0.5  # od tego progu fragment przesądza o manipulation_detected
QUOTED_WEIGHT = 0.5  # relacjonowana cudza wypowiedź waży mniej niż teza autora
SCORE_SCALE = 3.0  # przy ~3 ważonych fragmentach na 100 słów score ≈ 63

_SUBTYPES = {"none", "unverifiable", "unreliable", "inadequate"}


async def analyze_manipulation(
    text: str,
    sources: Sequence[TruthSource],
    article_date: date | None = None,
    *,
    call: StructuredCall = structured_call,
) -> ManipulationResult:
    if not text.strip():
        return build_manipulation_result(text, sources, LLMManipulationResponse(fragments=[]))
    response = await call(
        prompts.manipulation_system(),
        prompts.manipulation_user(text, sources, article_date),
        LLMManipulationResponse,
    )
    return build_manipulation_result(text, sources, response)


def build_manipulation_result(
    text: str, sources: Sequence[TruthSource], response: LLMManipulationResponse
) -> ManipulationResult:
    """Czysta funkcja: odpowiedź LLM → wynik z offsetami, deduplikacją i scoringiem."""
    names = prompts.category_names()
    by_id = {s.id: s for s in sources}
    best: dict[tuple[int, int, str], ManipulationFragment] = {}
    dropped = 0

    for item in response.fragments:
        confidence = min(max(item.confidence, 0.0), 1.0)
        if confidence < MIN_CONFIDENCE:
            continue
        span = locate_quote(text, item.quote)
        if span is None:
            dropped += 1
            continue
        start, end = span

        subtype = item.subtype.strip().lower() if item.category == "LACK_OF_SOURCE" else ""
        fragment = ManipulationFragment(
            quote=text[start:end],
            start=start,
            end=end,
            category=item.category,
            category_name=names[item.category],
            subtype=subtype if subtype in _SUBTYPES else None,
            indicators=[i.strip() for i in item.indicators if i.strip()],
            test_answer=item.test_answer.strip(),
            explanation=item.explanation.strip(),
            confidence=round(confidence, 2),
            attribution=item.attribution,
            source_evidence=_verify_evidence(item.source_id, item.source_evidence, by_id),
        )
        key = (start, end, item.category)
        if key not in best or best[key].confidence < fragment.confidence:
            best[key] = fragment

    fragments = sorted(best.values(), key=lambda f: (f.start, f.end, f.category))
    counts = dict.fromkeys(CATEGORY_CODES, 0)
    for f in fragments:
        counts[f.category] += 1

    return ManipulationResult(
        manipulation_detected=any(f.confidence >= DETECTION_CONFIDENCE for f in fragments),
        score=score_fragments(text, fragments),
        counts=counts,
        fragments=fragments,
        dropped_fragments=dropped,
    )


def _verify_evidence(
    source_id: str, quote: str, sources: dict[str, TruthSource]
) -> SourceEvidence | None:
    """Dowód ze źródła trafia do wyniku tylko wtedy, gdy cytat naprawdę jest w źródle."""
    source = sources.get(source_id.strip())
    if source is None or not quote.strip():
        return None
    span = locate_quote(source.content, quote)
    if span is None:
        return None
    return SourceEvidence(source_id=source.id, quote=source.content[span[0] : span[1]])


def score_fragments(text: str, fragments: Sequence[ManipulationFragment]) -> int:
    """0–100: gęstość fragmentów (na 100 słów) ważona pewnością i atrybucją, nasycana wykładniczo."""
    if not fragments:
        return 0
    words = max(len(re.findall(r"\w+", text)), 1)
    weight = sum(
        f.confidence * (QUOTED_WEIGHT if f.attribution == "quoted" else 1.0) for f in fragments
    )
    density = weight / max(words / 100, 1.0)
    return round(100 * (1 - math.exp(-density / SCORE_SCALE)))
