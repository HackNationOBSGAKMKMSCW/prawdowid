"""Aggregate JSON Lines logs: ``python -m observability.report [path] [--json] [--since ISO]``.

Run from ``backend/``. Reads rotated files too (app.jsonl, app.jsonl.1, ...).
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from collections import Counter, defaultdict
from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import Any

from .logconfig import DEFAULT_LOG_FILE


def iter_events(path: Path, since: str | None = None) -> Iterator[dict[str, Any]]:
    files = sorted(path.parent.glob(path.name + ".*"), reverse=True) + [path]
    for file in files:
        if not file.is_file():
            continue
        with file.open(encoding="utf-8", errors="replace") as handle:
            for line in handle:
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if since and str(event.get("ts", "")) < since:
                    continue
                yield event


def _percentile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    if len(values) == 1:
        return values[0]
    return round(statistics.quantiles(values, n=100, method="inclusive")[int(q) - 1], 1)


def summarize(events: Iterable[dict[str, Any]]) -> dict[str, Any]:
    requests: list[dict[str, Any]] = []
    llm_by_model: dict[str, dict[str, float]] = defaultdict(
        lambda: {
            "calls": 0,
            "errors": 0,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "cost_usd": 0.0,
        }
    )
    llm_latency: list[float] = []
    search_errors: Counter[str] = Counter()
    search_latency: list[float] = []
    search_calls = 0
    injections: Counter[str] = Counter()
    injection_sources: Counter[str] = Counter()
    abstains: Counter[str] = Counter()
    empty_evidence: Counter[str] = Counter()
    stage_times: dict[str, list[float]] = defaultdict(list)
    errors = 0

    for event in events:
        name = event.get("event")
        if name == "request_summary":
            requests.append(event)
        elif name == "llm_call":
            row = llm_by_model[str(event.get("model"))]
            row["calls"] += 1
            row["errors"] += 0 if event.get("ok", True) else 1
            row["prompt_tokens"] += event.get("prompt_tokens") or 0
            row["completion_tokens"] += event.get("completion_tokens") or 0
            row["cost_usd"] = round(row["cost_usd"] + (event.get("cost_usd") or 0.0), 6)
            if event.get("latency_ms") is not None:
                llm_latency.append(float(event["latency_ms"]))
        elif name == "search_call":
            search_calls += 1
            if event.get("latency_ms") is not None:
                search_latency.append(float(event["latency_ms"]))
        elif name == "search_error":
            search_calls += 1
            search_errors[f"{event.get('provider')}:{event.get('error')}"] += 1
        elif name == "prompt_injection":
            injections[str(event.get("kind"))] += 1
            injection_sources[str(event.get("source"))] += 1
        elif name == "abstain":
            abstains[str(event.get("reason"))] += 1
        elif name == "evidence_empty":
            empty_evidence[str(event.get("reason"))] += 1
        elif name == "stage" and event.get("duration_ms") is not None:
            stage_times[str(event.get("stage_name"))].append(float(event["duration_ms"]))
        if event.get("level") in {"error", "critical"}:
            errors += 1

    durations = [float(r["duration_ms"]) for r in requests if r.get("duration_ms") is not None]
    costs = [float(r.get("cost_usd") or 0.0) for r in requests]
    return {
        "requests": {
            "count": len(requests),
            "failed": sum(1 for r in requests if not r.get("ok", True)),
            "abstained": sum(1 for r in requests if r.get("abstained")),
            "duration_ms_p50": _percentile(durations, 50),
            "duration_ms_p95": _percentile(durations, 95),
            "cost_usd_total": round(sum(costs), 6),
            "cost_usd_avg": round(sum(costs) / len(costs), 6) if costs else None,
            "cost_incomplete": sum(1 for r in requests if r.get("cost_complete") is False),
        },
        "llm": {
            "latency_ms_p50": _percentile(llm_latency, 50),
            "latency_ms_p95": _percentile(llm_latency, 95),
            "by_model": dict(llm_by_model),
        },
        "search": {
            "calls": search_calls,
            "errors": dict(search_errors),
            "latency_ms_p95": _percentile(search_latency, 95),
            "empty_evidence": dict(empty_evidence),
        },
        "prompt_injection": {"by_kind": dict(injections), "by_source": dict(injection_sources)},
        "abstain": dict(abstains),
        "stages_ms_p50": {k: _percentile(v, 50) for k, v in sorted(stage_times.items())},
        "error_lines": errors,
    }


def _print_text(report: dict[str, Any]) -> None:
    def section(title: str, data: Any, indent: int = 0) -> None:
        pad = "  " * indent
        if isinstance(data, dict):
            print(f"{pad}{title}:")
            if not data:
                print(f"{pad}  -")
            for key, value in data.items():
                section(str(key), value, indent + 1)
        else:
            print(f"{pad}{title}: {data}")

    for key, value in report.items():
        section(key, value)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Summarize observability JSONL logs.")
    parser.add_argument("path", nargs="?", default=str(DEFAULT_LOG_FILE))
    parser.add_argument("--json", action="store_true", help="print JSON instead of text")
    parser.add_argument("--since", help="ISO timestamp lower bound, e.g. 2026-11-21T10:00")
    args = parser.parse_args(argv)

    path = Path(args.path)
    if not path.exists() and not list(path.parent.glob(path.name + ".*")):
        print(f"No log file: {path}", file=sys.stderr)
        return 1
    report = summarize(iter_events(path, args.since))
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        _print_text(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
