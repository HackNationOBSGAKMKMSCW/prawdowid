import asyncio
from datetime import date

from inputDataAnalysis import analyze_async
from inputDataAnalysis.manipulation import build_manipulation_result
from inputDataAnalysis.models import (
    LLMDatesResponse,
    LLMManipulationResponse,
    TruthSource,
)

TEXT = (
    "To skandaliczna zdrada rządu! Przestępczość rośnie: w lutym 2024 było o 15% więcej kradzieży "
    "niż w styczniu. Eksperci twierdzą, że będzie tylko gorzej."
)
SOURCE = TruthSource(
    id="kgp",
    content="Luty jest co roku miesiącem z wyraźnie wyższą liczbą kradzieży niż styczeń. "
    "W 2023 r. liczba kradzieży spadła o 8%.",
)


def frag(**kw):
    base = dict(
        quote="",
        category="EMOTIONAL_LANGUAGE",
        subtype="",
        indicators=[],
        test_answer="",
        explanation="",
        confidence=0.9,
        attribution="author",
        source_id="",
        source_evidence="",
    )
    return {**base, **kw}


def response(*fragments) -> LLMManipulationResponse:
    return LLMManipulationResponse.model_validate({"fragments": list(fragments)})


def test_fragments_located_categorized_and_counted():
    resp = response(
        frag(quote="skandaliczna zdrada rządu", indicators=["Słownictwo nacechowane emocjonalnie"]),
        frag(quote="skandaliczna zdrada rządu", category="EXAGGERATION", confidence=0.6),
        frag(
            quote="w lutym 2024 było o 15% więcej kradzieży niż w styczniu",
            category="CHERRY_PICKING",
            source_id="kgp",
            source_evidence="Luty jest co roku miesiącem z wyraźnie wyższą liczbą kradzieży niż styczeń.",
        ),
        frag(quote="Eksperci twierdzą", category="LACK_OF_SOURCE", subtype="none"),
        frag(quote="tego nie ma w tekście ani trochę", category="FEAR_APPEAL"),
        frag(quote="będzie tylko gorzej", category="FEAR_APPEAL", confidence=0.1),
    )
    result = build_manipulation_result(TEXT, [SOURCE], resp)

    assert result.manipulation_detected is True
    assert result.dropped_fragments == 1
    assert [f.category for f in result.fragments] == [
        "EMOTIONAL_LANGUAGE",
        "EXAGGERATION",
        "CHERRY_PICKING",
        "LACK_OF_SOURCE",
    ]
    assert result.counts["EMOTIONAL_LANGUAGE"] == 1
    assert result.counts["FEAR_APPEAL"] == 0
    for f in result.fragments:
        assert TEXT[f.start : f.end] == f.quote
    cherry = result.fragments[2]
    assert cherry.source_evidence is not None and cherry.source_evidence.source_id == "kgp"
    assert result.fragments[3].subtype == "none"
    assert result.fragments[0].category_name.startswith("A. Język emocjonalny")
    assert 0 < result.score <= 100


def test_evidence_not_in_source_is_dropped_but_fragment_kept():
    resp = response(
        frag(
            quote="Przestępczość rośnie",
            category="CHERRY_PICKING",
            source_id="kgp",
            source_evidence="Zmyślony cytat, którego w źródle nie ma wcale.",
        )
    )
    result = build_manipulation_result(TEXT, [SOURCE], resp)
    assert result.fragments[0].source_evidence is None


def test_quoted_attribution_weighs_less():
    author = build_manipulation_result(TEXT, [], response(frag(quote="skandaliczna zdrada rządu")))
    quoted = build_manipulation_result(
        TEXT, [], response(frag(quote="skandaliczna zdrada rządu", attribution="quoted"))
    )
    assert quoted.score < author.score


def test_neutral_text():
    result = build_manipulation_result("Rada przyjęła budżet.", [], response())
    assert result.manipulation_detected is False
    assert result.score == 0
    assert set(result.counts.values()) == {0}


def test_pipeline_with_fake_llm():
    async def fake_call(system, user, schema):
        assert "<tekst>" in user
        if schema is LLMManipulationResponse:
            return response(frag(quote="skandaliczna zdrada rządu"))
        return LLMDatesResponse(
            article_date_in_text="", text_category="other", recency_framing=0.0, dates=[]
        )

    result = asyncio.run(
        analyze_async(
            TEXT, [{"id": "kgp", "text": SOURCE.content}], date(2024, 4, 1), call=fake_call
        )
    )
    assert result.manipulation.counts["EMOTIONAL_LANGUAGE"] == 1
    assert result.dates.dates_consistent is True
    assert result.dates.article_date == date(2024, 4, 1)
