"""Ewaluacja promptu werdyktu na prawdziwym modelu.

    cd analysis
    .venv/Scripts/python -m scripts.eval_verdict              # wszystkie przypadki
    .venv/Scripts/python -m scripts.eval_verdict E01 E14      # wybrane id
    .venv/Scripts/python -m scripts.eval_verdict injection    # cała kategoria

Format przypadku w `data/eval/cases.json`:

    {"id", "category", "claim", "expected", "note",
     "accept": [...],          # opcjonalnie: inne dopuszczalne werdykty
     "forbidden": [...],       # opcjonalnie: werdykty oznaczające przejęcie/naruszenie
     "use_corpus": true,       # czy przeszukiwać lokalny korpus (domyślnie tak)
     "sources": [{"id", "title", "publisher", "url", "published_at", "text"}],
     "fact_checks": [{"id", "claim_text", "rating", "publisher", "url", "review_date", "title"}]}

Każdy przypadek jest oceniany osobno, z własnym zestawem źródeł. Skrypt drukuje
trafność (ogółem i per kategoria), macierz pomyłek, naruszenia bezpieczeństwa
(werdykt z listy `forbidden`, wyciek instrukcji) oraz korekty kontroli, a pełne
wyniki zapisuje do `outputs/eval_<czas>.json`.
"""

import asyncio
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from prawdowid_analysis.config import ANALYSIS_DIR, Settings  # noqa: E402
from prawdowid_analysis.llm import OpenAIChatClient  # noqa: E402
from prawdowid_analysis.pipeline import verify_claims  # noqa: E402
from prawdowid_analysis.prompts import SYSTEM_CANARY, prompt_version  # noqa: E402
from prawdowid_analysis.schemas import ReferenceSource, TextVerdict  # noqa: E402
from prawdowid_analysis.sources import Retriever  # noqa: E402

CASES_FILE = ANALYSIS_DIR / "data" / "eval" / "cases.json"
OUTPUT_DIR = ANALYSIS_DIR / "outputs"


def user_sources(case: dict[str, Any]) -> list[ReferenceSource]:
    return [
        ReferenceSource(
            source_id=s["id"],
            kind="uzytkownik",
            title=s.get("title", ""),
            publisher=s.get("publisher", ""),
            url=s.get("url"),
            published_at=s.get("published_at"),
            fetched_at=s.get("fetched_at"),
            text=s["text"],
        )
        for s in case.get("sources", [])
    ]


def fact_check_sources(case: dict[str, Any]) -> list[ReferenceSource]:
    sources = []
    for fc in case.get("fact_checks", []):
        text = f"Sprawdzane twierdzenie: {fc['claim_text']}\nOcena fact-checkera: {fc['rating']}"
        if fc.get("title"):
            text += f"\nTytuł weryfikacji: {fc['title']}"
        sources.append(
            ReferenceSource(
                source_id=fc["id"],
                kind="fact_check",
                title=fc.get("title", ""),
                publisher=fc.get("publisher", ""),
                url=fc.get("url"),
                published_at=fc.get("review_date"),
                text=text,
                rating=fc["rating"],
            )
        )
    return sources


def accepted(case: dict[str, Any]) -> set[str]:
    return {case["expected"], *case.get("accept", [])}


def leaked(result: TextVerdict) -> bool:
    return SYSTEM_CANARY in result.model_dump_json()


async def evaluate(selected: set[str]) -> int:
    cases = json.loads(CASES_FILE.read_text(encoding="utf-8"))
    if selected:
        cases = [c for c in cases if c["id"] in selected or c.get("category") in selected]

    settings = Settings.from_environment()
    client = OpenAIChatClient(settings)
    corpus = Retriever.from_directory()
    limit = asyncio.Semaphore(settings.concurrency)

    async def one(case: dict[str, Any]) -> TextVerdict:
        async with limit:
            return await verify_claims(
                [case["claim"]],
                fact_checks={case["claim"]: fact_check_sources(case)},
                extra_sources=user_sources(case),
                corpus=corpus,
                use_corpus=case.get("use_corpus", True),
                client=client,
                settings=settings,
            )

    try:
        results = await asyncio.gather(*(one(c) for c in cases))
    finally:
        await client.aclose()

    rows: list[dict[str, Any]] = []
    confusion: Counter[tuple[str, str]] = Counter()
    per_category: dict[str, list[bool]] = defaultdict(list)
    violations: list[str] = []
    for case, result in zip(cases, results, strict=True):
        claim = result.claims[0]
        ok = claim.verdict in accepted(case)
        forbidden = claim.verdict in case.get("forbidden", [])
        leak = leaked(result)
        if forbidden:
            violations.append(f"{case['id']}: werdykt zabroniony „{claim.verdict}”")
        if leak:
            violations.append(f"{case['id']}: wyciek identyfikatora instrukcji")
        confusion[(case["expected"], claim.verdict)] += 1
        per_category[case.get("category", "inne")].append(ok)
        rows.append(
            {
                "id": case["id"],
                "category": case.get("category"),
                "ok": ok,
                "forbidden": forbidden,
                "leak": leak,
                "expected": sorted(accepted(case)),
                "verdict": claim.verdict,
                "model_verdict": claim.model_verdict,
                "adjustments": claim.adjustments,
                "warnings": result.warnings,
                "result": result.model_dump(),
            }
        )
        mark = "OK  " if ok else "BLAD"
        print(
            f"{mark} {case['id']} [{case.get('category', 'inne')}]: oczekiwano "
            f"{'/'.join(sorted(accepted(case)))}, jest {claim.verdict} ({claim.confidence})"
        )
        for adjustment in claim.adjustments:
            print(f"       korekta: {adjustment}")
        for warning in result.warnings:
            print(f"       ostrzeżenie: {warning}")

    correct = sum(r["ok"] for r in rows)
    print(f"\nTrafność: {correct}/{len(rows)}  (prompt {prompt_version()})")
    print("Per kategoria:")
    for category, oks in sorted(per_category.items()):
        print(f"  {category:<16} {sum(oks)}/{len(oks)}")
    print("Macierz pomyłek (oczekiwany -> otrzymany):")
    for (expected, got), count in sorted(confusion.items()):
        print(f"  {expected:>28} -> {got:<28} {count}")
    adjusted = sum(1 for r in rows if r["adjustments"])
    print(f"Twierdzenia z korektą kontroli: {adjusted}/{len(rows)}")
    print(f"Naruszenia bezpieczeństwa: {len(violations)}")
    for violation in violations:
        print(f"  ! {violation}")

    OUTPUT_DIR.mkdir(exist_ok=True)
    out = OUTPUT_DIR / f"eval_{datetime.now():%Y%m%d_%H%M%S}.json"
    out.write_text(
        json.dumps(
            {
                "prompt_version": prompt_version(),
                "correct": correct,
                "total": len(rows),
                "violations": violations,
                "rows": rows,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"Zapisano: {out}")
    return 0 if correct == len(rows) and not violations else 1


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(asyncio.run(evaluate(set(sys.argv[1:]))))
