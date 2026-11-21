"""Uruchamianie pakietów backendu (`textAnalysis`, `apiReading`) z poziomu analysis.

Backend jest importowany tylko w czasie działania (bez zmian w `backend/`):

- logi postępu backendu (`print` na stdout) są przekierowane na stderr, żeby
  stdout CLI zawierał wyłącznie JSON werdyktu;
- błąd ekstrakcji stwierdzeń (`textAnalysis`) jest zgłaszany jako `BackendError`
  z czytelnym komunikatem – bez stwierdzeń nie ma czego oceniać;
- błąd wyszukiwania fact-checków (`apiReading`) NIE przerywa analizy: werdykt
  powstaje z pozostałych źródeł, a ostrzeżenie trafia do wyniku.

Tryby wyszukiwania fact-checków (`FactCheckMode`):
- `stwierdzenia` – `apiReading.run()`: osobne zapytanie dla każdego stwierdzenia,
- `pelny-tekst` – `apiReading.run_full_text()`: jedno zapytanie całym tekstem,
- `oba` – oba powyższe (domyślnie; najwięcej trafień),
- `brak` – bez fact-checków.
"""

import contextlib
import importlib
import sys
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType
from typing import Any, Literal

from .config import ANALYSIS_DIR

BACKEND_DIR = ANALYSIS_DIR.parent / "backend"
FactCheckMode = Literal["stwierdzenia", "pelny-tekst", "oba", "brak"]
FACT_CHECK_MODES: tuple[str, ...] = ("stwierdzenia", "pelny-tekst", "oba", "brak")


class BackendError(RuntimeError):
    """Backend jest niedostępny albo nie wyodrębnił stwierdzeń."""


@dataclass
class BackendOutput:
    analysis: Any
    reading_results: list[Any] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def load_backend(backend_dir: Path = BACKEND_DIR) -> tuple[ModuleType, ModuleType]:
    if str(backend_dir) not in sys.path:
        sys.path.insert(0, str(backend_dir))
    try:
        with contextlib.redirect_stdout(sys.stderr):
            text_analysis = importlib.import_module("textAnalysis")
            api_reading = importlib.import_module("apiReading")
    except ImportError as exc:
        raise BackendError(
            f"Nie można zaimportować pakietów backendu z {backend_dir}: {exc}"
        ) from exc
    return text_analysis, api_reading


async def run_backend(
    text: str,
    mode: FactCheckMode = "oba",
    *,
    text_analysis: Any = None,
    api_reading: Any = None,
) -> BackendOutput:
    """Wyodrębnia stwierdzenia i pobiera fact-checki przez pakiety backendu."""
    if text_analysis is None or api_reading is None:
        text_analysis, api_reading = load_backend()

    with contextlib.redirect_stdout(sys.stderr):
        try:
            analysis = await text_analysis.run(text)
        except Exception as exc:  # backend zgłasza własne typy błędów
            raise BackendError(
                f"Ekstrakcja stwierdzeń (textAnalysis) nie powiodła się: "
                f"{type(exc).__name__}: {exc}"
            ) from exc

        output = BackendOutput(analysis=analysis)
        if mode in ("stwierdzenia", "oba"):
            try:
                output.reading_results.extend(await api_reading.run(analysis))
            except Exception as exc:
                output.warnings.append(_reading_failure("stwierdzeniami", exc))
        if mode in ("pelny-tekst", "oba"):
            runner = getattr(api_reading, "run_full_text", None)
            if runner is None:
                output.warnings.append(
                    "Backend nie udostępnia apiReading.run_full_text(); "
                    "wyszukiwanie pełnym tekstem pominięto."
                )
            else:
                try:
                    output.reading_results.append(await runner(analysis))
                except Exception as exc:
                    output.warnings.append(_reading_failure("pełnym tekstem", exc))
    return output


def _reading_failure(how: str, exc: Exception) -> str:
    return (
        f"Wyszukiwanie fact-checków {how} nie powiodło się ({type(exc).__name__}); "
        "werdykt opiera się na pozostałych źródłach."
    )
