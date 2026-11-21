"""Testy zgodności analysis z formatem danych backendu.

- Fixture `tests/data/backend_contract.json` (zapis prawdziwych obiektów backendu)
  przechodzi przez potok zawsze, także bez dostępu do backendu.
- Gdy backend da się zaimportować: te same obiekty (żywe, nie zserializowane)
  przechodzą przez potok, a struktura pól musi zgadzać się z fixture. Zmiana
  formatu w backendzie wywraca ten test, zamiast po cichu gubić dane.
  Odświeżenie fixture po świadomej zmianie: `python -m tests.backend_objects`.
"""

import asyncio
import json

import pytest

from prawdowid_analysis.config import Settings
from prawdowid_analysis.pipeline import run
from prawdowid_analysis.sources import Retriever
from tests.backend_objects import FIXTURE, STATEMENTS, build, dump, import_backend
from tests.fakes import FakeChatClient, model_answer

SETTINGS = Settings(
    api_key="x",
    base_url=None,
    model="atrapa",
    timeout=1,
    max_retries=0,
    json_mode=False,
    concurrency=1,
)


def backend_or_skip():
    try:
        return import_backend()
    except ImportError as exc:
        pytest.skip(f"backend niedostępny: {exc}")


def run_pipeline(analysis, reading_results):
    client = FakeChatClient(
        model_answer(verdict="brak_wystarczajacych_danych", evidence=[], missing_information=["x"])
    )
    result = asyncio.run(
        run(analysis, reading_results, client=client, settings=SETTINGS, corpus=Retriever([]))
    )
    return result, client


def assert_contract(result, client):
    assert [c.claim for c in result.claims] == STATEMENTS
    # Twierdzenie o szczepionkach: wpis Google z run() i z run_full_text() (ten sam, bez duplikatu)
    assert len(client.calls) == 1
    message = client.calls[0][1]["content"]
    assert message.count('kind="fact_check"') == 1
    assert 'language="pl"' in message
    fact_checks = [s for s in result.sources if s.kind == "fact_check"]
    assert [s.publisher for s in fact_checks] == ["Demagog"]
    assert fact_checks[0].rating == "Fałsz"
    # Twierdzenie o Rysach: żadne źródło nie pasuje -> potwierdzony brak danych bez modelu
    assert result.claims[1].verdict == "brak_wystarczajacych_danych"
    # Ostrzeżenia: brak klucza (raz) i obcięte zapytanie pełnym tekstem
    assert sum("GOOGLE_FACT_CHECK_API_KEY" in w for w in result.warnings) == 1
    assert any("zapytań: 1 z 3" in w for w in result.warnings)
    assert any("1000 znaków" in w for w in result.warnings)


def test_serialized_backend_fixture_goes_through_pipeline():
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert_contract(*run_pipeline(data["analysis"], data["reading_results"]))


def test_live_backend_objects_go_through_pipeline():
    analysis, results = build(backend_or_skip())
    assert_contract(*run_pipeline(analysis, results))


def test_single_full_text_result_is_accepted():
    analysis, results = build(backend_or_skip())
    result, client = run_pipeline(analysis, results[-1])  # jak apiReading.run_full_text()
    assert client.calls and 'kind="fact_check"' in client.calls[0][1]["content"]
    assert any("1000 znaków" in w for w in result.warnings)


def _shape(value):
    if isinstance(value, dict):
        return {key: _shape(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_shape(value[0])] if value else []
    return type(value).__name__


def test_fixture_matches_current_backend_format():
    current = dump(*build(backend_or_skip()))
    stored = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert _shape(current) == _shape(stored), (
        "Backend zmienił format danych: sprawdź adapters.py i odśwież fixture "
        "(python -m tests.backend_objects)."
    )
