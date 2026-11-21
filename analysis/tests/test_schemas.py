import pytest
from pydantic import ValidationError

from prawdowid_analysis.schemas import ModelVerdict, ReferenceSource


def test_model_verdict_accepts_full_payload():
    payload = {
        "claim_interpretation": "Twierdzenie dotyczy stolicy Polski.",
        "verdict": "prawda",
        "confidence": "wysoka",
        "reasoning_steps": ["Krok 1"],
        "evidence": [{"source_id": "S1", "quote": "Warszawa jest stolicą", "stance": "potwierdza"}],
        "sources_reviewed": [{"source_id": "S1", "relevant": True, "why": "Wprost o stolicy"}],
        "conflicts": [],
        "missing_information": [],
        "explanation": "Źródło S1 wprost to potwierdza.",
    }
    parsed = ModelVerdict.model_validate(payload)
    assert parsed.verdict == "prawda"
    assert parsed.evidence[0].stance == "potwierdza"


@pytest.mark.parametrize("bad_verdict", ["true", "Prawda", "czesciowo", ""])
def test_model_verdict_rejects_unknown_verdict(bad_verdict):
    with pytest.raises(ValidationError):
        ModelVerdict.model_validate(
            {
                "claim_interpretation": "x",
                "verdict": bad_verdict,
                "confidence": "niska",
                "reasoning_steps": ["x"],
                "explanation": "x",
            }
        )


def test_model_verdict_requires_reasoning_and_explanation():
    with pytest.raises(ValidationError):
        ModelVerdict.model_validate(
            {
                "claim_interpretation": "x",
                "verdict": "prawda",
                "confidence": "niska",
                "reasoning_steps": [],
                "explanation": "",
            }
        )


def test_reference_source_requires_text():
    with pytest.raises(ValidationError):
        ReferenceSource(source_id="S1", kind="korpus", text="")
