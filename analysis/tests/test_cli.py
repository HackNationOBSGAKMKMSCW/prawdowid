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


def test_load_user_sources_reads_fetched_at(tmp_path):
    path = tmp_path / "zrodla.json"
    path.write_text(
        json.dumps(
            [{"text": "T", "published_at": "2024-01-01", "fetched_at": "2026-11-20T10:00:00Z"}]
        ),
        encoding="utf-8",
    )
    [source] = cli.load_user_sources(path)
    assert source.published_at == "2024-01-01" and source.fetched_at == "2026-11-20T10:00:00Z"


def _fake_result():
    from tests.test_output import sample

    return sample()


def test_cli_prints_compact_json_by_default_and_full_with_flag(monkeypatch, capsysbinary):
    async def fake_run_text(text, **kwargs):
        return _fake_result()

    monkeypatch.setattr(cli, "run_text", fake_run_text)
    assert cli.main(["Polska weszła do UE w 2004 roku."]) == 0
    compact_out = json.loads(capsysbinary.readouterr().out.decode("utf-8"))
    assert "text" not in compact_out["sources"][0]
    assert "context" not in compact_out["claims"][0]

    assert cli.main(["--pelny", "Polska weszła do UE w 2004 roku."]) == 0
    full_out = json.loads(capsysbinary.readouterr().out.decode("utf-8"))
    assert full_out["sources"][0]["text"]
    assert full_out["claims"][0]["context"] == "Tekst użytkownika."
