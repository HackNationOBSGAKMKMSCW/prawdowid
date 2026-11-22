import asyncio
from types import SimpleNamespace

import pytest

from prawdowid_analysis import cli
from prawdowid_analysis.backend_bridge import BackendError, run_backend


class FakeTextAnalysis:
    def __init__(self, error: Exception | None = None):
        self.error = error

    async def run(self, text):
        print("[textAnalysis] log na stdout")
        if self.error:
            raise self.error
        return SimpleNamespace(source_text=text, statements=["Stwierdzenie."], security_warnings=[])


class FakeApiReading:
    def __init__(self, fail_statements=False, fail_full=False, has_full_text=True):
        self.calls: list[str] = []
        self.fail_statements = fail_statements
        self.fail_full = fail_full
        if not has_full_text:
            self.run_full_text = None

    async def run(self, analysis):
        print("[apiReading] wyniki z treścią na stdout")
        self.calls.append("run")
        if self.fail_statements:
            raise ValueError("analysis must contain at least one statement to search")
        return [SimpleNamespace(request=SimpleNamespace(query="Stwierdzenie."), items=[])]

    async def run_full_text(self, analysis):
        self.calls.append("run_full_text")
        if self.fail_full:
            raise RuntimeError("timeout")
        return SimpleNamespace(request=SimpleNamespace(query=analysis.source_text), items=[])


def bridge(mode="oba", text_analysis=None, api_reading=None):
    return asyncio.run(
        run_backend(
            "Tekst.",
            mode,
            text_analysis=text_analysis or FakeTextAnalysis(),
            api_reading=api_reading or FakeApiReading(),
        )
    )


@pytest.mark.parametrize(
    ("mode", "expected_calls", "results"),
    [
        ("oba", ["run", "run_full_text"], 2),
        ("stwierdzenia", ["run"], 1),
        ("pelny-tekst", ["run_full_text"], 1),
        ("brak", [], 0),
    ],
)
def test_fact_check_modes(mode, expected_calls, results):
    reading = FakeApiReading()
    output = bridge(mode, api_reading=reading)
    assert reading.calls == expected_calls
    assert len(output.reading_results) == results
    assert output.warnings == []


def test_backend_logs_go_to_stderr_not_stdout(capsys):
    bridge()
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "[textAnalysis]" in captured.err and "[apiReading]" in captured.err


def test_text_analysis_failure_is_backend_error():
    with pytest.raises(BackendError, match="AnalysisError"):
        bridge(
            text_analysis=FakeTextAnalysis(error=type("AnalysisError", (RuntimeError,), {})("x"))
        )


def test_reading_failures_become_warnings_not_crash():
    output = bridge(api_reading=FakeApiReading(fail_statements=True, fail_full=True))
    assert output.reading_results == []
    assert len(output.warnings) == 2
    assert "pozostałych źródłach" in output.warnings[0]


def test_missing_run_full_text_is_reported():
    output = bridge("pelny-tekst", api_reading=FakeApiReading(has_full_text=False))
    assert "run_full_text" in output.warnings[0]


def test_cli_backend_error_returns_exit_code_3(monkeypatch, capsys):
    async def failing(text, mode):
        raise BackendError("Ekstrakcja stwierdzeń nie powiodła się")

    monkeypatch.setattr(cli, "run_backend", failing)
    assert cli.main(["--backend", "Tekst do sprawdzenia."]) == 3
    assert "Błąd backendu" in capsys.readouterr().err
