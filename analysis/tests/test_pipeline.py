import asyncio
import json
from types import SimpleNamespace

from prawdowid_analysis.config import Settings
from prawdowid_analysis.pipeline import run, run_text, split_sentences
from prawdowid_analysis.sources import Retriever
from tests.fakes import FakeChatClient, model_answer, source
from tests.test_adapters import FC_CLAIM, _reading_result

SETTINGS = Settings(
    api_key="x",
    base_url=None,
    model="atrapa",
    timeout=1,
    max_retries=0,
    json_mode=False,
    concurrency=1,
)
EU_CLAIM = "Polska przystąpiła do Unii Europejskiej 1 maja 2004 roku."


def corpus_answer():
    return model_answer(
        evidence=[
            {
                "source_id": "KOR-polska-ue",
                "quote": "Polska przystąpiła do Unii Europejskiej 1 maja 2004 roku",
                "stance": "potwierdza",
                "explanation": "data",
            }
        ],
        sources_reviewed=[],
    )


def test_split_sentences_drops_fragments():
    text = "Polska jest w UE od 2004 roku. Tak! Rysy mają 2499 metrów wysokości."
    assert split_sentences(text) == [
        "Polska jest w UE od 2004 roku.",
        "Rysy mają 2499 metrów wysokości.",
    ]


def test_run_text_uses_corpus_and_returns_json_serializable_result():
    client = FakeChatClient(corpus_answer())
    result = asyncio.run(run_text(EU_CLAIM, client=client, settings=SETTINGS))
    assert result.verdict == "prawdziwy"
    assert result.claims[0].claim_id == "T1"
    assert "KOR-polska-ue" in result.claims[0].source_ids
    assert result.claims[0].evidence[0].quote_verified
    assert any(s.source_id == "KOR-polska-ue" for s in result.sources)
    assert result.prompt_version.startswith("werdykt-v1-")
    json.loads(result.model_dump_json())


def test_claim_without_any_source_is_not_sent_to_model():
    client = FakeChatClient()
    result = asyncio.run(
        run_text(
            "Kwantowa chromodynamika opisuje gluony w hadronach.",
            client=client,
            settings=SETTINGS,
        )
    )
    assert result.verdict == "brak_wystarczajacych_danych"
    assert client.calls == []


def test_run_with_backend_objects_includes_fact_checks_and_warnings():
    statement = "Szczepionki zawierają mikroczipy."
    analysis = SimpleNamespace(
        statements=[statement], security_warnings=["podejrzany wzorzec"], language_code="pl"
    )
    reading = [_reading_result(statement, [FC_CLAIM], errors=[("google_fact_check", None)])]
    client = FakeChatClient(
        model_answer(verdict="brak_wystarczajacych_danych", evidence=[], missing_information=["x"])
    )
    result = asyncio.run(
        run(analysis, reading, client=client, settings=SETTINGS, corpus=Retriever([]))
    )
    user_message = client.calls[0][1]["content"]
    assert 'kind="fact_check"' in user_message
    assert "podejrzany wzorzec" in result.warnings
    assert any(s.kind == "fact_check" for s in result.sources)


def test_user_sources_are_always_shown_to_model():
    user_source = source("UZ-1", kind="uzytkownik", text="Dokument użytkownika o czymś.")
    client = FakeChatClient(
        model_answer(verdict="brak_wystarczajacych_danych", evidence=[], missing_information=["x"])
    )
    asyncio.run(
        run_text(
            "Zupełnie inne twierdzenie o pogodzie.",
            extra_sources=[user_source],
            client=client,
            settings=SETTINGS,
            use_corpus=False,
        )
    )
    assert 'id="UZ-1"' in client.calls[0][1]["content"]
