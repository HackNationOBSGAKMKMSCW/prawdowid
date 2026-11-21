import os

import pytest

from prawdowid_analysis.config import Settings, backend_model

KEYS = (
    "FREELLM_API_KEY",
    "FREELLM_BASE_URL",
    "FREELLM_MODEL",
    "OPENAI_API_KEY",
    "LLM_MODEL",
    "GOOGLE_FACT_CHECK_API_KEY",
)


@pytest.fixture
def clean_env(monkeypatch):
    # Kopia środowiska: load_dotenv zapisuje do os.environ, a te wpisy nie mogą
    # przeciec do innych testów.
    isolated = {k: v for k, v in os.environ.items() if k not in KEYS}
    monkeypatch.setattr(os, "environ", isolated)
    return monkeypatch


def write(path, **values):
    path.write_text("".join(f"{k}={v}\n" for k, v in values.items()), encoding="utf-8")
    return path


def test_analysis_env_wins_over_backend_env(tmp_path, clean_env):
    analysis_env = write(tmp_path / "analysis.env", FREELLM_MODEL="model-analysis")
    backend_env = write(
        tmp_path / "backend.env",
        FREELLM_MODEL="model-backend",
        FREELLM_API_KEY="klucz-z-backendu",
        GOOGLE_FACT_CHECK_API_KEY="g",
    )
    settings = Settings.from_environment(analysis_env, backend_env)
    assert settings.model == "model-analysis"
    assert settings.api_key == "klucz-z-backendu", "brakujące wartości z backend/.env"
    assert backend_model() == "model-analysis", "backend dostanie ten sam model"


def test_process_environment_wins_over_files(tmp_path, clean_env):
    clean_env.setenv("FREELLM_MODEL", "model-z-procesu")
    analysis_env = write(tmp_path / "analysis.env", FREELLM_MODEL="model-analysis")
    settings = Settings.from_environment(analysis_env, tmp_path / "brak.env")
    assert settings.model == "model-z-procesu"


def test_defaults_and_legacy_names(tmp_path, clean_env):
    clean_env.setenv("OPENAI_API_KEY", "stary-klucz")
    settings = Settings.from_environment(tmp_path / "brak.env", tmp_path / "brak2.env")
    assert settings.api_key == "stary-klucz"
    assert settings.model == "gpt-4o-mini"
