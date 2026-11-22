"""Zmiany z panelu („Modele i źródła danych”) działają bez restartu we wszystkich etapach."""

from __future__ import annotations

import importlib

import pytest
from admin.runtime import RuntimeConfigStore
from verification._analysis import add_paths


@pytest.fixture
def runtime(monkeypatch, tmp_path):
    path = tmp_path / "runtime.json"
    monkeypatch.setenv("RUNTIME_CONFIG_FILE", str(path))
    for name, value in {
        "FREELLM_API_KEY": "klucz-z-env",
        "FREELLM_BASE_URL": "https://llm.example/v1",
        "FREELLM_MODEL": "model-z-env",
    }.items():
        monkeypatch.setenv(name, value)
    monkeypatch.delenv("TEXT_ANALYSIS_MODEL", raising=False)
    monkeypatch.delenv("API_READING_DISABLED_CLIENTS", raising=False)
    store = RuntimeConfigStore(path)
    yield store
    store.update({"llm": {"model": None}, "apis": {"disabled_clients": []}})
    from admin.runtime import apply_runtime_overrides

    apply_runtime_overrides()  # zdjęcie nadpisań przywraca zmienne sprzed testu


def test_input_analysis_follows_the_model_set_in_the_panel(runtime):
    add_paths()
    config = importlib.import_module("inputDataAnalysis.config")
    assert config.get_settings().model == "model-z-env"

    runtime.update({"llm": {"model": "model-z-panelu"}})
    assert config.get_settings().model == "model-z-panelu"  # bez restartu

    runtime.update({"llm": {"model": None}})
    assert config.get_settings().model == "model-z-env"  # zdjęte nadpisanie: wartość z .env


def test_text_analysis_and_verdict_follow_the_panel(runtime):
    from textAnalysis.settings import Settings

    add_paths()
    verdict = importlib.import_module("prawdowid_analysis.config")
    runtime.update({"llm": {"model": "model-z-panelu"}})
    assert Settings.from_environment().freellm_model == "model-z-panelu"
    assert verdict.Settings.from_environment().model == "model-z-panelu"


def test_disabled_api_client_is_skipped_on_the_next_query(runtime):
    from admin.runtime import apply_runtime_overrides
    from apiReading.registry import CLIENTS_BY_CATEGORY, clients_for_categories

    category, clients = next((c, v) for c, v in CLIENTS_BY_CATEGORY.items() if v)
    name = clients[0].name
    runtime.update({"apis": {"disabled_clients": [name]}})
    apply_runtime_overrides()
    selected, _ = clients_for_categories([category])
    assert name not in {c.name for c in selected}


def test_two_saves_in_the_same_tick_are_both_seen(runtime):
    """Inny proces (inna instancja) widzi każdy zapis, nawet z tym samym mtime."""
    reader = RuntimeConfigStore(runtime.path)
    runtime.update({"llm": {"model": "pierwszy"}})
    assert reader.load().llm.model == "pierwszy"
    runtime.update({"llm": {"model": "drugi"}})
    assert reader.load().llm.model == "drugi"
