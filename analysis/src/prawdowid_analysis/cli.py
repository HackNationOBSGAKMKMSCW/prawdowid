"""CLI: werdykt dla tekstu, wynik jako JSON na stdout.

    python -m prawdowid_analysis.cli "Tekst do sprawdzenia."
    echo "Tekst" | python -m prawdowid_analysis.cli
    python -m prawdowid_analysis.cli --sources moje_zrodla.json "Tekst"
    python -m prawdowid_analysis.cli --backend "Tekst"   # textAnalysis + apiReading
    python -m prawdowid_analysis.cli --backend --fact-checks pelny-tekst "Tekst"

Plik `--sources` to lista obiektów {"id", "title", "publisher", "url",
"published_at", "text"} – źródła wzorcowe podane przez użytkownika.

`--backend` importuje pakiety z `../backend` (tylko odczyt, bez zmian w backendzie):
stwierdzenia wyciąga `textAnalysis`, a wpisy fact-checkingowe pobiera `apiReading`
(patrz `backend_bridge`). Logi backendu idą na stderr; stdout zawiera tylko JSON.

Kody wyjścia: 0 – sukces, 2 – brak konfiguracji modelu, 3 – błąd backendu.
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

from .backend_bridge import FACT_CHECK_MODES, BackendError, FactCheckMode, run_backend
from .llm import LLMConfigurationError
from .output import compact
from .pipeline import run, run_text
from .schemas import ReferenceSource, TextVerdict


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
            fetched_at=item.get("fetched_at"),
            text=item["text"],
        )
        for n, item in enumerate(raw, 1)
    ]


async def _run_with_backend(text: str, mode: FactCheckMode, **kwargs: Any) -> TextVerdict:
    output = await run_backend(text, mode)
    models = {"ekstrakcja_stwierdzen": output.extraction_model} if output.extraction_model else {}
    return await run(
        output.analysis,
        output.reading_results,
        warnings=output.warnings,
        models=models,
        **kwargs,
    )


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
    parser.add_argument(
        "--fact-checks",
        choices=FACT_CHECK_MODES,
        default="oba",
        help="Tryb wyszukiwania fact-checków przy --backend (domyślnie: oba)",
    )
    parser.add_argument("--output", type=Path, help="Zapisz JSON do pliku")
    parser.add_argument(
        "--pelny",
        action="store_true",
        help="Pełny wynik (z treścią źródeł, kontekstem i polami pustymi) zamiast skróconego",
    )
    args = parser.parse_args(argv)

    text = args.text if args.text is not None else sys.stdin.read()
    if not text.strip():
        parser.error("Podaj tekst do sprawdzenia.")

    kwargs: dict[str, Any] = {"use_corpus": not args.no_corpus}
    if args.sources:
        kwargs["extra_sources"] = load_user_sources(args.sources)

    try:
        coro = (
            _run_with_backend(text, args.fact_checks, **kwargs)
            if args.backend
            else run_text(text, **kwargs)
        )
        result = asyncio.run(coro)
    except LLMConfigurationError as exc:
        print(f"Błąd konfiguracji: {exc}", file=sys.stderr)
        return 2
    except BackendError as exc:
        print(f"Błąd backendu: {exc}", file=sys.stderr)
        return 3

    if args.pelny:
        payload = result.model_dump_json(indent=2)
    else:
        payload = json.dumps(compact(result), ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload, encoding="utf-8")
    _write_json(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
