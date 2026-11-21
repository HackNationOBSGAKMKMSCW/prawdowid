import json

from prawdowid_analysis import cli
from prawdowid_analysis.llm import LLMConfigurationError


def test_load_user_sources_assigns_ids_and_kind(tmp_path):
    path = tmp_path / "zrodla.json"
    path.write_text(
        json.dumps([{"title": "A", "text": "Treść A"}, {"id": "MOJE", "text": "Treść B"}]),
        encoding="utf-8",
    )
    sources = cli.load_user_sources(path)
    assert [s.source_id for s in sources] == ["UZ-1", "MOJE"]
    assert all(s.kind == "uzytkownik" for s in sources)


def test_missing_api_key_returns_exit_code_2(monkeypatch, capsys):
    async def failing_run_text(text, **kwargs):
        raise LLMConfigurationError("Ustaw FREELLM_API_KEY")

    monkeypatch.setattr(cli, "run_text", failing_run_text)
    assert cli.main(["Polska jest w Unii Europejskiej."]) == 2
    assert "FREELLM_API_KEY" in capsys.readouterr().err
