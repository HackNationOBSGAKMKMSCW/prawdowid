"""Ewaluacja pełnej ścieżki: zapytanie do działającego backendu (`GET /api/check`).

Mierzy to, czego nie widzi `eval_verdict`: wyszukiwanie, scraping, czas od wejścia do
odpowiedzi, błędy techniczne i to, co faktycznie dostaje użytkownik. Tokeny, wywołania
modelu, błędy wyszukiwania i zdarzenia injection czyta z logu backendu po `X-Request-ID`.

    cd analysis
    .venv/Scripts/python -m scripts.eval_e2e                       # cały zestaw (T*, U*)
    .venv/Scripts/python -m scripts.eval_e2e T01 E                 # wybrane id / scenariusze
    .venv/Scripts/python -m scripts.eval_e2e --load 6              # 6 równoczesnych zapytań
    .venv/Scripts/python -m scripts.eval_e2e T01 --expect-technical --label J
        # scenariusz J: backend uruchomiony bez klucza / z niedostępnym modelem;
        # każdy merytoryczny wynik (200 z werdyktami) jest naruszeniem

Wymaga backendu z `URUCHOMIENIE.md` (domyślnie http://127.0.0.1:8000) i logowania do pliku
(`backend/logs/app.jsonl`). Wyniki: `docs/wyniki-testow/e2e_<etykieta>_<czas>.{json,md}`.
"""

import argparse
import asyncio
import json
import statistics
import sys
import time
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx

ANALYSIS_DIR = Path(__file__).resolve().parents[1]
REPO_DIR = ANALYSIS_DIR.parent
CASES_FILE = ANALYSIS_DIR / "data" / "eval" / "e2e_cases.json"
RESULTS_DIR = REPO_DIR / "docs" / "wyniki-testow"
LOG_FILE = REPO_DIR / "backend" / "logs" / "app.jsonl"
DECISIVE = {"confirmed", "false", "misleading"}
LOAD_TEXT = "Polska przystąpiła do Unii Europejskiej 1 maja 2004 roku."


def select(cases: list[dict[str, Any]], selectors: set[str]) -> list[dict[str, Any]]:
    if not selectors:
        return cases
    return [c for c in cases if c["id"] in selectors or c.get("scenario") in selectors]


async def call(client: httpx.AsyncClient, text: str) -> dict[str, Any]:
    t0 = time.perf_counter()
    try:
        response = await client.get("/api/check", params={"text": text})
        seconds = time.perf_counter() - t0
        try:
            body = response.json()
        except ValueError:
            body = {"raw": response.text[:500]}
        return {
            "status": response.status_code,
            "seconds": round(seconds, 2),
            "request_id": response.headers.get("x-request-id"),
            "body": body,
        }
    except httpx.HTTPError as exc:
        return {
            "status": None,
            "seconds": round(time.perf_counter() - t0, 2),
            "request_id": None,
            "body": {"transport_error": type(exc).__name__},
        }


def outcome(reply: dict[str, Any]) -> str:
    status, body = reply["status"], reply["body"]
    if status == 200 and body.get("status") == "result":
        return "wynik"
    if status is None or status >= 500:
        return "techniczny"
    return "odmowa/4xx"


def judge(case: dict[str, Any], reply: dict[str, Any]) -> dict[str, Any]:
    claims = (reply["body"].get("claims") or []) if outcome(reply) == "wynik" else []
    verdicts = [c.get("verdict") for c in claims]
    sources = [s for c in claims for s in (c.get("sources") or [])]
    expected = set(case.get("expected", []))
    forbidden = set(case.get("forbidden", []))
    decisive = [c for c in claims if c.get("verdict") in DECISIVE]
    return {
        "outcome": outcome(reply),
        "verdicts": verdicts,
        "claims": len(claims),
        "ok": (bool(verdicts) and set(verdicts) <= expected) if expected else None,
        "forbidden_hit": bool(forbidden & set(verdicts)),
        "decisive_claims": len(decisive),
        "decisive_with_source": sum(
            any((s.get("quote") or "").strip() and s.get("url") for s in c.get("sources") or [])
            for c in decisive
        ),
        "sources": len(sources),
        # Sygnał W1: cytat bez linku albo z zastępczym wydawcą – źródło spoza pobranych.
        "sources_without_url": sum(not s.get("url") for s in sources),
        "error_code": (reply["body"].get("error") or {}).get("code"),
    }


def read_log(path: Path, request_ids: set[str]) -> dict[str, dict[str, Any]]:
    found: dict[str, dict[str, Any]] = {rid: {"injection_events": 0} for rid in request_ids}
    if not path.exists():
        return found
    with path.open(encoding="utf-8", errors="replace") as handle:
        for line in handle:
            if not any(rid in line for rid in request_ids):
                continue
            try:
                event = json.loads(line)
            except ValueError:
                continue
            rid = event.get("request_id")
            if rid not in found:
                continue
            if event.get("event") == "request_summary":
                found[rid].update(
                    {
                        k: event.get(k)
                        for k in (
                            "duration_ms",
                            "llm_calls",
                            "llm_errors",
                            "models",
                            "prompt_tokens",
                            "completion_tokens",
                            "cost_usd",
                            "search_calls",
                            "search_errors",
                            "injection_attempts",
                            "abstained",
                        )
                    }
                )
            elif event.get("event") == "prompt_injection":
                found[rid]["injection_events"] += 1
    return found


def _median(values: list[float]) -> float | None:
    return round(statistics.median(values), 2) if values else None


def compute(rows: list[dict[str, Any]], expect_technical: bool) -> dict[str, Any]:
    results = [r for r in rows if r["outcome"] == "wynik"]
    decisive = sum(r["decisive_claims"] for r in rows)
    tokens = [
        (r["log"].get("prompt_tokens") or 0) + (r["log"].get("completion_tokens") or 0)
        for r in rows
        if r["log"].get("prompt_tokens") is not None
    ]
    graded = [r for r in rows if r["ok"] is not None and r["outcome"] == "wynik"]
    inj = [r for r in rows if r["scenario"] == "E"]
    return {
        "requests": len(rows),
        "outcomes": dict(Counter(r["outcome"] for r in rows)),
        "e2e_success": {"hits": len(results), "total": len(rows)},
        "latency_median_s": {
            "text": _median([r["seconds"] for r in rows if r["kind"] == "text"]),
            "url": _median([r["seconds"] for r in rows if r["kind"] == "url"]),
            "all": _median([r["seconds"] for r in rows]),
        },
        "latency_max_s": max((r["seconds"] for r in rows), default=None),
        "expected_match": {"hits": sum(r["ok"] for r in graded), "total": len(graded)},
        "citation_coverage_live": {
            "hits": sum(r["decisive_with_source"] for r in rows),
            "total": decisive,
        },
        "sources_without_url": {
            "hits": sum(r["sources_without_url"] for r in rows),
            "total": sum(r["sources"] for r in rows),
        },
        "verdicts": dict(Counter(v for r in rows for v in r["verdicts"])),
        "claims_per_request_median": _median([r["claims"] for r in results]),
        "injection": {
            "forbidden_verdicts": sum(r["forbidden_hit"] for r in inj),
            "logged": sum(bool(r["log"].get("injection_events")) for r in inj),
            "total": len(inj),
        },
        "tokens_per_request_median": _median(tokens),
        "tokens_per_1000_requests": round(statistics.mean(tokens) * 1000) if tokens else None,
        "llm_calls_per_request_median": _median(
            [r["log"]["llm_calls"] for r in rows if r["log"].get("llm_calls") is not None]
        ),
        "search_errors": sum(r["log"].get("search_errors") or 0 for r in rows),
        "abstained_logged": sum(bool(r["log"].get("abstained")) for r in rows),
        "wall_time_per_100_requests_min": round(
            statistics.mean([r["seconds"] for r in rows]) * 100 / 60, 1
        )
        if rows
        else None,
        "technical_violations": [
            r["id"] for r in rows if expect_technical and r["outcome"] == "wynik"
        ],
    }


def summary_markdown(meta: dict[str, Any], m: dict[str, Any], rows: list[dict[str, Any]]) -> str:
    def share(d: dict[str, int]) -> str:
        return f"{d['hits']}/{d['total']}" + (
            f" ({d['hits'] / d['total']:.0%})" if d["total"] else ""
        )

    lat = m["latency_median_s"]
    lines = [
        f"# Ewaluacja E2E ({meta['label']}) — {meta['started_at']}",
        "",
        f"Backend `{meta['base']}`, commit `{meta['commit']}`, zapytań: {m['requests']}, "
        f"tryb: {'oczekiwany komunikat techniczny (J)' if meta['expect_technical'] else 'zwykły'}.",
        "",
        "| Miernik | Cel | Wynik |",
        "|---|---|---|",
        f"| Mediana czasu: tekst | ≤ 30 s | {lat['text']} s |",
        f"| Mediana czasu: URL | ≤ 30 s | {lat['url']} s |",
        f"| Odpowiedź merytoryczna bez błędu technicznego | 100% | {share(m['e2e_success'])} |",
        f"| Rozstrzygnięcia z cytatem i linkiem | ≥ 95% | {share(m['citation_coverage_live'])} |",
        f"| Źródła bez linku (sygnał źródła spoza pobranych) | 0 | {share(m['sources_without_url'])} |",
        f"| Zgodność z oczekiwanym werdyktem | — | {share(m['expected_match'])} |",
        f"| Injection: werdykt zabroniony / odnotowane w logu | 0 / wszystkie | "
        f"{m['injection']['forbidden_verdicts']} / {m['injection']['logged']} "
        f"z {m['injection']['total']} |",
        f"| Tokeny na zapytanie (mediana) | — | {m['tokens_per_request_median']} |",
        f"| Tokeny na 1000 zapytań | — | {m['tokens_per_1000_requests']} |",
        f"| Wywołania modelu na zapytanie (mediana) | — | {m['llm_calls_per_request_median']} |",
        f"| Czas 100 zapytań sekwencyjnie | — | {m['wall_time_per_100_requests_min']} min |",
        f"| Wstrzymania odnotowane w logu | — | {m['abstained_logged']} |",
        f"| Błędy wyszukiwania (log) | — | {m['search_errors']} |",
        "",
        f"Wyniki: {m['outcomes']}; werdykty: {m['verdicts']}.",
        "",
    ]
    if m["technical_violations"]:
        lines += [
            f"**Naruszenia J (wynik mimo awarii):** {', '.join(m['technical_violations'])}",
            "",
        ]
    lines += [
        "| Id | Scen. | Wynik | Czas [s] | Werdykty | Oczek. | Źródła | Kod błędu |",
        "|---|---|---|---|---|---|---|---|",
        *[
            f"| {r['id']} | {r['scenario']} | {r['outcome']} | {r['seconds']} | "
            f"{', '.join(r['verdicts']) or '—'} | "
            f"{'—' if r['ok'] is None else ('✅' if r['ok'] else '❌')} | {r['sources']} | "
            f"{r['error_code'] or '—'} |"
            for r in rows
        ],
        "",
    ]
    return "\n".join(lines)


async def run_cases(
    base: str, cases: list[dict[str, Any]], timeout: float, partial: Path | None = None
) -> list[dict[str, Any]]:
    """Zapytania po kolei; każdy wiersz od razu dopisywany do `partial` (JSONL)."""
    rows = []
    async with httpx.AsyncClient(base_url=base, timeout=timeout) as client:
        for case in cases:
            reply = await call(client, case["input"])
            row = {
                "id": case["id"],
                "scenario": case.get("scenario"),
                "kind": case.get("kind", "text"),
                "input": case["input"],
                "seconds": reply["seconds"],
                "status": reply["status"],
                "request_id": reply["request_id"],
                **judge(case, reply),
                "response": reply["body"],
            }
            rows.append(row)
            if partial is not None:
                with partial.open("a", encoding="utf-8") as handle:
                    handle.write(json.dumps(row, ensure_ascii=False) + "\n")
            print(
                f"{row['id']} [{row['scenario']}] {row['outcome']} {row['status']} "
                f"{row['seconds']} s: {', '.join(row['verdicts']) or row['error_code'] or '—'}",
                flush=True,
            )
    return rows


async def run_load(base: str, n: int, timeout: float) -> list[dict[str, Any]]:
    async with httpx.AsyncClient(base_url=base, timeout=timeout) as client:
        replies = await asyncio.gather(*(call(client, LOAD_TEXT) for _ in range(n)))
    return [
        {
            "id": f"L{i + 1:02d}",
            "status": r["status"],
            "seconds": r["seconds"],
            "outcome": outcome(r),
            "error_code": (r["body"].get("error") or {}).get("code"),
        }
        for i, r in enumerate(replies)
    ]


def _commit() -> str | None:
    from scripts.eval_verdict import _git_commit

    return _git_commit()


async def main_async(args: argparse.Namespace) -> int:
    started = datetime.now()
    stamp = f"{started:%Y%m%d_%H%M%S}"
    args.out.mkdir(parents=True, exist_ok=True)
    async with httpx.AsyncClient(base_url=args.base, timeout=10) as client:
        try:
            health = (await client.get("/api/health")).status_code
        except httpx.HTTPError:
            health = None
    print(f"/api/health: {health}")

    meta = {
        "started_at": started.isoformat(timespec="seconds"),
        "base": args.base,
        "label": args.label,
        "commit": _commit(),
        "expect_technical": args.expect_technical,
        "health": health,
    }
    if args.load:
        rows = await run_load(args.base, args.load, args.timeout)
        counts = dict(Counter(r["status"] for r in rows))
        text = (
            f"# Test ruchu ({args.load} równoczesnych zapytań) — {meta['started_at']}\n\n"
            f"Kody odpowiedzi: {counts}\n\n| Id | Kod | Czas [s] | Kod błędu |\n|---|---|---|---|\n"
            + "\n".join(
                f"| {r['id']} | {r['status']} | {r['seconds']} | {r['error_code'] or '—'} |"
                for r in rows
            )
            + "\n"
        )
        payload = {"meta": meta, "load": rows, "status_counts": counts}
        name = f"e2e_ruch_{stamp}"
    else:
        cases = select(json.loads(CASES_FILE.read_text(encoding="utf-8")), set(args.selectors))
        partial = args.out / f"e2e_{args.label}_{stamp}.partial.jsonl"
        rows = await run_cases(args.base, cases, args.timeout, partial)
        partial.unlink(missing_ok=True)
        logs = read_log(args.log, {r["request_id"] for r in rows if r["request_id"]})
        for row in rows:
            row["log"] = logs.get(row["request_id"], {})
        m = compute(rows, args.expect_technical)
        text = summary_markdown(meta, m, rows)
        payload = {"meta": meta, "metrics": m, "rows": rows}
        name = f"e2e_{args.label}_{stamp}"
    print("\n" + text)
    (args.out / f"{name}.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (args.out / f"{name}.md").write_text(text, encoding="utf-8")
    print(f"Zapisano: {args.out / f'{name}.json'}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("selectors", nargs="*", help="id przypadku albo scenariusz")
    parser.add_argument("--base", default="http://127.0.0.1:8000", help="adres backendu")
    parser.add_argument("--timeout", type=float, default=420.0, help="limit na zapytanie [s]")
    parser.add_argument("--log", type=Path, default=LOG_FILE, help="log JSONL backendu")
    parser.add_argument("--out", type=Path, default=RESULTS_DIR, help="katalog wyników")
    parser.add_argument("--label", default="pelny", help="etykieta przebiegu w nazwie pliku")
    parser.add_argument("--load", type=int, default=0, help="test ruchu: N równoczesnych zapytań")
    parser.add_argument(
        "--expect-technical",
        action="store_true",
        help="scenariusz J: każdy wynik merytoryczny to naruszenie",
    )
    return asyncio.run(main_async(parser.parse_args(argv)))


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
