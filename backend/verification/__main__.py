"""CLI: python -m verification "tekst" [--jsonl]

Prints every part the moment it is ready. ``--jsonl`` prints one JSON event per line
(without ``user_input``, like scripts.smoke_pipeline).
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import sys
from typing import Any

import observability

from . import _analysis
from .models import VerificationEvent
from .service import stream


def _summary(event: VerificationEvent) -> list[str]:
    head = f"== {event.part} [{event.status}] {event.duration_ms} ms"
    if event.error is not None:
        return [head, f"   {event.error.kind}: {event.error.message}"]
    data: dict[str, Any] = event.data or {}
    if event.part == "evidence":
        scraping = data["scraping"]
        lines = [head, f"   twierdzenia: {data['statements']}"]
        lines.append(
            f"   artykuły: {len(scraping['articles'])} z {scraping['distinct_sites']} stron"
            f" (min. 2 strony: {'tak' if scraping['min_sites_met'] else 'nie'})"
        )
        lines += [f"   - {a['site']}: {a['title']} ({a['url']})" for a in scraping["articles"]]
        return lines
    if event.part == "input_analysis":
        manipulation, dates = data["manipulation"], data["dates"]
        lines = [
            head,
            f"   manipulacja: {manipulation['manipulation_detected']}"
            f" (wynik {manipulation['score']}/100)",
        ]
        lines += [f"   - {f['category']}: „{f['quote']}”" for f in manipulation["fragments"]]
        lines.append(f"   daty spójne: {dates['dates_consistent']}")
        lines += [f"   - {i['code']}: {i['description']}" for i in dates["issues"]]
        return lines
    lines = [head, f"   werdykt: {data['verdict']}: {data['summary']}"]
    lines += [f"   - {c['verdict']}: {c['claim']}" for c in data.get("claims", [])]
    return lines


async def _main(text: str, as_jsonl: bool) -> int:
    failed = 0
    out = sys.stdout  # results only; the modules' progress prints go to stderr
    with observability.request_scope("verification"), contextlib.redirect_stdout(sys.stderr):
        try:
            async for event in stream(text):
                failed += event.status == "error"
                if as_jsonl:
                    payload = event.model_dump(mode="json")
                    if event.part == "evidence" and payload["data"]:
                        payload["data"]["scraping"].pop("user_input", None)
                    print(json.dumps(payload, ensure_ascii=False), file=out, flush=True)
                else:
                    print("\n".join(_summary(event)), file=out, flush=True)
        finally:
            with contextlib.suppress(Exception):
                await _analysis.input_analysis().llm.reset_clients()
    return 1 if failed else 0


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("text")
    parser.add_argument("--jsonl", action="store_true")
    args = parser.parse_args()
    _analysis.add_paths()  # before init(): the inputDataAnalysis stage gets instrumented too
    observability.init()
    sys.exit(asyncio.run(_main(args.text, args.jsonl)))


if __name__ == "__main__":
    main()
