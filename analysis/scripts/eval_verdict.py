"""Ewaluacja promptu werdyktu na prawdziwym modelu.

    cd analysis
    .venv/Scripts/python -m scripts.eval_verdict            # wszystkie przypadki
    .venv/Scripts/python -m scripts.eval_verdict E01 E14    # wybrane

Każde twierdzenie z `data/eval/cases.json` jest oceniane osobno na lokalnym
korpusie wzorcowym. Skrypt drukuje trafność, macierz pomyłek i liczbę ingerencji
kontroli deterministycznej, a pełne wyniki zapisuje do `outputs/eval_<czas>.json`.
"""

import asyncio
import json
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from prawdowid_analysis.config import ANALYSIS_DIR  # noqa: E402
from prawdowid_analysis.pipeline import verify_claims  # noqa: E402
from prawdowid_analysis.prompts import prompt_version  # noqa: E402

CASES_FILE = ANALYSIS_DIR / "data" / "eval" / "cases.json"
OUTPUT_DIR = ANALYSIS_DIR / "outputs"


async def evaluate(selected: set[str]) -> int:
    cases = json.loads(CASES_FILE.read_text(encoding="utf-8"))
    if selected:
        cases = [c for c in cases if c["id"] in selected]
    result = await verify_claims([c["claim"] for c in cases])

    rows, confusion = [], Counter()
    for case, claim in zip(cases, result.claims, strict=True):
        ok = claim.verdict == case["expected"]
        confusion[(case["expected"], claim.verdict)] += 1
        rows.append(
            {
                "id": case["id"],
                "ok": ok,
                "expected": case["expected"],
                "verdict": claim.verdict,
                "model_verdict": claim.model_verdict,
                "adjustments": claim.adjustments,
                "result": claim.model_dump(),
            }
        )
        mark = "OK " if ok else "BLAD"
        print(f"{mark} {case['id']}: oczekiwano {case['expected']}, jest {claim.verdict}")
        for adjustment in claim.adjustments:
            print(f"      korekta: {adjustment}")

    correct = sum(r["ok"] for r in rows)
    print(f"\nTrafność: {correct}/{len(rows)}  (prompt {prompt_version()})")
    print("Macierz pomyłek (oczekiwany -> otrzymany):")
    for (expected, got), count in sorted(confusion.items()):
        print(f"  {expected:>28} -> {got:<28} {count}")
    adjusted = sum(1 for r in rows if r["adjustments"])
    print(f"Twierdzenia z korektą kontroli: {adjusted}/{len(rows)}")

    OUTPUT_DIR.mkdir(exist_ok=True)
    out = OUTPUT_DIR / f"eval_{datetime.now():%Y%m%d_%H%M%S}.json"
    out.write_text(
        json.dumps(
            {
                "prompt_version": prompt_version(),
                "correct": correct,
                "total": len(rows),
                "rows": rows,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"Zapisano: {out}")
    return 0 if correct == len(rows) else 1


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(asyncio.run(evaluate(set(sys.argv[1:]))))
