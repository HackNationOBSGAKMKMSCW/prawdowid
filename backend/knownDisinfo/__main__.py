"""CLI for the EUvsDisinfo check.

python -m knownDisinfo --health          # server status (no key needed)
python -m knownDisinfo --tools           # tools exposed by the MCP server
python -m knownDisinfo --search "query"  # raw search: claim_review cases only, no LLM
python -m knownDisinfo "twierdzenie"     # full check: queries, candidates, LLM decision
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from types import SimpleNamespace

import observability

from . import run
from .mcp import EUvsDisinfoMcp, McpError
from .settings import DisinfoSettings
from .store import McpDisinfoStore


async def _main(args: argparse.Namespace) -> int:
    settings = DisinfoSettings.from_environment()
    async with EUvsDisinfoMcp(settings) as mcp:
        try:
            if args.health:
                print(json.dumps(await mcp.health(), ensure_ascii=False))
                return 0
            if args.tools:
                for tool in await mcp.list_tools():
                    params = tool.get("inputSchema", {}).get("properties", {})
                    print(f"{tool['name']}({', '.join(params)}): {tool.get('description', '')}")
                return 0
            if args.search:
                cases = await McpDisinfoStore(mcp).search(args.search, settings.max_candidates)
                for case in cases:
                    print(f"- {case.title}\n  {case.url}\n  {case.summary[:200]}")
                print(f"({len(cases)} przypadków)")
                return 0
        except McpError as exc:
            print(exc, file=sys.stderr)
            return 1
    if not args.text:
        print("Podaj twierdzenie albo --health / --tools / --search.", file=sys.stderr)
        return 2
    result = await run(SimpleNamespace(statements=[args.text]), settings=settings)
    print(f"status: {result.status} ({result.duration_ms} ms)")
    for statement in result.statements:
        print(f"T{statement.index}: {statement.statement}")
        print(f"   zapytania: {statement.queries}")
        for candidate in statement.candidates:
            print(f"   - kandydat: {candidate.title} ({candidate.case_id})")
        if statement.match:
            print(f"   TRAFIENIE: {statement.match.title} ({statement.match.url})")
        else:
            print("   brak trafienia")
        if statement.reason:
            print(f"   uzasadnienie: {statement.reason}")
    for warning in result.warnings:
        print(f"! {warning}")
    return 0 if result.status != "error" else 1


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("text", nargs="?")
    parser.add_argument("--health", action="store_true")
    parser.add_argument("--tools", action="store_true")
    parser.add_argument("--search")
    args = parser.parse_args()
    observability.init()
    sys.exit(asyncio.run(_main(args)))


if __name__ == "__main__":
    main()
