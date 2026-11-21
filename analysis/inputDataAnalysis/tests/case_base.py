"""Wspólna struktura przypadku testowego katalogu (patrz ``OCZEKIWANE_WYNIKI.md``).

Każdy przypadek niesie opis wejścia i oczekiwanego wyniku (do tabeli) oraz funkcję ``check``,
która wykonuje asercję. Dzięki temu tabela i testy zawsze są zgodne.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date

from inputDataAnalysis.dates import TimeRef


@dataclass(frozen=True)
class Case:
    id: str
    group: str
    title: str
    wejscie: str
    oczekiwane: str
    check: Callable[[], None]
    known_bug: str = ""  # niepusty → test oznaczony xfail(strict) z tym opisem


# Nazwy grup w kolejności, w jakiej występują w tabeli i w przebiegu testów.
GROUPS: dict[str, str] = {
    "DT": "TimeRef.from_iso: parsowanie dat ISO na przedziały",
    "DW": "TimeRef.width_days: szerokość przedziału",
    "DI": "dist(): odległość między przedziałami",
    "RE": "parse_relative(): wyrażenia względne (baza 2024-03-20, środa)",
    "WD": "parse_weekday(): polskie nazwy dni tygodnia",
    "FM": "Formatowanie dat i liczebników po polsku",
    "SP": "locate_quote(): odnajdywanie cytatów w tekście",
    "TS": "TruthSource: adapter źródeł prawdy",
    "RU": "Reguły dat: evaluate() na gotowych obiektach",
    "SK": "skipped_checks: pominięte reguły i powody",
    "BD": "build_dates_result(): odpowiedź LLM → DatesResult",
    "MA": "build_manipulation_result(): odpowiedź LLM → fragmenty",
    "SC": "score_fragments(): wynik 0–100",
    "PR": "Prompty: nagłówek i źródła",
    "PI": "Pipeline analyze()/analyze_async() z atrapą LLM",
    "LV": "Na żywo z LLM (wymaga klucza i RUN_LLM_TESTS=1)",
}


def ref_str(ref: TimeRef | None) -> str:
    """Zwięzły opis przedziału do tabeli."""
    if ref is None:
        return "brak daty"
    if ref.granularity == "day":
        return ref.start.isoformat()
    if ref.granularity == "month":
        return f"{ref.start:%Y-%m} (miesiąc)"
    if ref.granularity == "year":
        return f"{ref.start.year} (rok)"
    if ref.granularity == "quarter":
        return f"{ref.start.year}-Q{(ref.start.month - 1) // 3 + 1} (kwartał)"
    return f"{ref.start.isoformat()}…{ref.end.isoformat()} ({ref.granularity})"


def d(iso: str) -> date:
    return date.fromisoformat(iso)


def day(iso: str) -> TimeRef:
    return TimeRef.day(d(iso))


def iso(start: str, end: str = "", gran: str = "") -> TimeRef:
    ref = TimeRef.from_iso(start, end, gran)
    assert ref is not None, start
    return ref
