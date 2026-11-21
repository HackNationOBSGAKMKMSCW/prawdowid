"""CLI: werdykt dla tekstu, wynik jako JSON na stdout.

    python -m prawdowid_analysis.cli "Tekst do sprawdzenia."
    echo "Tekst" | python -m prawdowid_analysis.cli
    python -m prawdowid_analysis.cli --sources moje_zrodla.json "Tekst"
    python -m prawdowid_analysis.cli --backend "Tekst"   # textAnalysis + apiReading

Plik `--sources` to lista obiektów {"id", "title", "publisher", "url",
"published_at", "text"} – źródła wzorcowe podane przez użytkownika.

`--backend` importuje pakiety z `../backend` (tylko odczyt, bez zmian w backendzie):
stwierdzenia wyciąga `textAnalysis`, a wpisy fact-checkingowe pobiera `apiReading`.
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

from .config import ANALYSIS_DIR
from .llm import LLMConfigurationError
from .pipeline import run, run_text
from .schemas import ReferenceSource, TextVerdict

BACKEND_DIR = ANALYSIS_DIR.parent / "backend"


def load_user_sources(path: Path) -> list[ReferenceSource]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(raw, dict):
        raw = [raw]
    return [
        ReferenceSource(
            source_id=item.get("id") or f"UZ-{n}",
            kind="uzytkownik",
            title=item.get("title", ""),
            publisher=item.get("publisher", ""),
            url=item.get("url"),
            published_at=item.get("published_at"),
            text=item["text"],
        )
        for n, item in enumerate(raw, 1)
    ]


async def _run_with_backend(text: str, **kwargs: Any) -> TextVerdict:
    sys.path.insert(0, str(BACKEND_DIR))
    import apiReading  # noqa: PLC0415  (opcjonalna zależność uruchomieniowa)
    import textAnalysis  # noqa: PLC0415

    analysis = await textAnalysis.run(text)
    try:
        reading = await apiReading.run(analysis)
    except ValueError:  # brak stwierdzeń do wyszukania
        reading = []
    return await run(analysis, reading, **kwargs)


def _write_json(payload: str) -> None:
    sys.stdout.buffer.write(payload.encode("utf-8") + b"\n")
    sys.stdout.flush()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Werdykt prawdziwości tekstu (JSON).")
    parser.add_argument("text", nargs="?", help="Tekst do sprawdzenia (domyślnie stdin)")
    parser.add_argument("--sources", type=Path, help="Plik JSON ze źródłami wzorcowymi")
    parser.add_argument("--no-corpus", action="store_true", help="Pomiń lokalny korpus")
    parser.add_argument(
        "--backend", action="store_true", help="Użyj backend/textAnalysis i apiReading"
    )
    parser.add_argument("--output", type=Path, help="Zapisz JSON do pliku")
    args = parser.parse_args(argv)

    text = args.text if args.text is not None else sys.stdin.read()
    if not text.strip():
        parser.error("Podaj tekst do sprawdzenia.")

    kwargs: dict[str, Any] = {"use_corpus": not args.no_corpus}
    if args.sources:
        kwargs["extra_sources"] = load_user_sources(args.sources)

    try:
        coro = _run_with_backend(text, **kwargs) if args.backend else run_text(text, **kwargs)
        result = asyncio.run(coro)
    except LLMConfigurationError as exc:
        print(f"Błąd konfiguracji: {exc}", file=sys.stderr)
        return 2

    payload = result.model_dump_json(indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload, encoding="utf-8")
    _write_json(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
