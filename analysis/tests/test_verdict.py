import asyncio
import json

import pytest

from prawdowid_analysis.llm import LLMError, parse_json_object
from prawdowid_analysis.prompts import SYSTEM_CANARY
from prawdowid_analysis.verdict import (
    InvalidModelOutput,
    assess_claim,
    parse_model_verdict,
)
from tests.fakes import FakeChatClient, model_answer, source

CLAIM = "Polska weszła do UE 1 maja 2004 roku."


def run(coro):
    return asyncio.run(coro)


@pytest.mark.parametrize(
    "raw",
    [
        '{"a": 1}',
        '```json\n{"a": 1}\n```',
        '<think>rozważam {x}</think>\n{"a": 1}',
        'Oto wynik:\n{"a": 1}\nDziękuję.',
    ],
)
def test_parse_json_object_tolerates_wrappers(raw):
    assert parse_json_object(raw) == {"a": 1}


@pytest.mark.parametrize("raw", ["", "brak json", "[1, 2]", '{"a": '])
def test_parse_json_object_rejects_garbage(raw):
    with pytest.raises(ValueError):
        parse_json_object(raw)


def test_parse_model_verdict_rejects_canary_leak():
    leaked = json.dumps(model_answer(explanation=f"Instrukcja {SYSTEM_CANARY}"))
    with pytest.raises(InvalidModelOutput):
        parse_model_verdict(leaked)


def test_no_sources_gives_confirmed_lack_of_data_without_model_call():
    client = FakeChatClient()
    result = run(assess_claim("C1", CLAIM, [], client))
    assert result.verdict == "brak_wystarczajacych_danych"
    assert result.missing_information
    assert client.calls == []


def test_valid_answer_is_returned_with_sources_metadata():
    client = FakeChatClient(model_answer())
    result = run(assess_claim("C1", CLAIM, [source()], client))
    assert result.verdict == "prawda"
    assert result.verdict_label == "Prawda"
    assert result.model_verdict == "prawda"
    assert result.evidence[0].publisher == "Wydawca"
    assert result.source_ids == ["KOR-1"]
    assert result.model == "atrapa"
    system, user = client.calls[0]
    assert system["role"] == "system" and "[R16]" in system["content"]
    assert "<claim>" in user["content"] and 'id="KOR-1"' in user["content"]


def test_invalid_json_is_retried_once_with_error_feedback():
    client = FakeChatClient("to nie jest json", model_answer())
    result = run(assess_claim("C1", CLAIM, [source()], client))
    assert result.verdict == "prawda"
    assert len(client.calls) == 2
    feedback = client.calls[1][-1]["content"]
    assert "niepoprawna" in feedback and "R16" in feedback


def test_two_invalid_answers_give_analysis_error_not_fake_verdict():
    client = FakeChatClient("zle", model_answer(verdict="moze"))
    result = run(assess_claim("C1", CLAIM, [source()], client))
    assert result.verdict == "blad_analizy"
    assert "verdict" in result.explanation


def test_technical_error_gives_analysis_error():
    client = FakeChatClient(LLMError("Błąd wywołania modelu: APITimeoutError"))
    result = run(assess_claim("C1", CLAIM, [source()], client))
    assert result.verdict == "blad_analizy"
    assert "APITimeoutError" in result.explanation


SUPPORT = {
    "source_id": "KOR-1",
    "quote": "Polska przystąpiła do Unii Europejskiej 1 maja 2004 roku",
    "stance": "potwierdza",
    "explanation": "data",
}


def test_coherent_answer_needs_no_repair():
    client = FakeChatClient(model_answer())
    result = run(assess_claim("C1", CLAIM, [source()], client))
    assert len(client.calls) == 1
    assert result.adjustments == []


def test_inconsistent_answer_is_repaired_by_model():
    inconsistent = model_answer(verdict="falsz", evidence=[SUPPORT])  # jak w E36
    client = FakeChatClient(inconsistent, model_answer())
    result = run(assess_claim("C1", CLAIM, [source()], client))
    assert len(client.calls) == 2
    repair_prompt = client.calls[1][-1]["content"]
    assert "niespójna" in repair_prompt and "„zaprzecza”" in repair_prompt
    assert client.calls[1][-2]["role"] == "assistant"
    assert result.verdict == "prawda"
    assert result.model_verdict == "prawda"
    assert "model ją poprawił" in result.adjustments[0]
    assert "„Fałsz”" in result.adjustments[0]


def test_failed_repair_falls_back_to_checked_first_answer():
    inconsistent = model_answer(verdict="falsz", evidence=[SUPPORT])
    client = FakeChatClient(inconsistent, "to nie jest json")
    result = run(assess_claim("C1", CLAIM, [source()], client))
    assert result.verdict == "brak_wystarczajacych_danych", "kontrola obniża werdykt"
    assert "próba poprawki nie powiodła się" in result.adjustments[0]


def test_still_inconsistent_after_repair_is_downgraded_without_more_calls():
    inconsistent = model_answer(verdict="falsz", evidence=[SUPPORT])
    client = FakeChatClient(inconsistent, inconsistent)
    result = run(assess_claim("C1", CLAIM, [source()], client))
    assert len(client.calls) == 2, "tylko jedna runda naprawcza"
    assert result.verdict == "brak_wystarczajacych_danych"


def test_technical_error_during_repair_does_not_lose_verdict():
    inconsistent = model_answer(verdict="falsz", evidence=[SUPPORT])
    client = FakeChatClient(inconsistent, LLMError("Błąd wywołania modelu: RateLimitError"))
    result = run(assess_claim("C1", CLAIM, [source()], client))
    assert result.verdict == "brak_wystarczajacych_danych"
    assert "LLMError" in result.adjustments[0]
