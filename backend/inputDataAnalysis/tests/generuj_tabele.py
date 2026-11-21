"""Generuje OCZEKIWANE_WYNIKI.md z katalogu: ``python -m inputDataAnalysis.tests.generuj_tabele``."""

from pathlib import Path

from .case_base import GROUPS
from .katalog import ALL_CASES


def _cell(s: str) -> str:
    return s.replace("|", "\\|").replace("\n", " ")


def main() -> None:
    lines = [
        "# Oczekiwane wyniki testów modułu `inputDataAnalysis`",
        "",
        "Plik generowany: `python -m inputDataAnalysis.tests.generuj_tabele` (z katalogu `backend/`).",
        "Uruchomienie: `python -m pytest inputDataAnalysis/tests -v`. Przypadki `LV` wymagają `RUN_LLM_TESTS=1`.",
        "Kolumna „Status”: ✅ oczekiwany wynik jest wymagany; ⚠️ znany błąd (test `xfail`, opis pod tabelą).",
        "",
        f"Łącznie przypadków: **{len(ALL_CASES)}**.",
        "",
    ]
    for code, name in GROUPS.items():
        cases = [c for c in ALL_CASES if c.group == code]
        lines += [
            f"## {code}: {name} ({len(cases)})",
            "",
            "| ID | Przypadek | Wejście | Oczekiwany wynik | Status |",
            "|---|---|---|---|---|",
        ]
        for c in cases:
            status = "⚠️" if c.known_bug else "✅"
            lines.append(
                f"| {c.id} | {_cell(c.title)} | {_cell(c.wejscie)} | {_cell(c.oczekiwane)} | {status} |"
            )
        bugs = [c for c in cases if c.known_bug]
        if bugs:
            lines += ["", "Znane błędy:", *[f"- **{c.id}**: {c.known_bug}" for c in bugs]]
        lines.append("")
    out = Path(__file__).with_name("OCZEKIWANE_WYNIKI.md")
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"Zapisano {out} ({len(ALL_CASES)} przypadków)")


if __name__ == "__main__":
    main()
