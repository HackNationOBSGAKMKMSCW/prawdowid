"""Inspect and query the trusted-source whitelist (edit the list in whitelist.py).

Usage (from backend/):
    python -m trustedSources list
    python -m trustedSources check <id> | --all
    python -m trustedSources search "<teza>" [--raw] [--json]
        (frazy jak w pipeline: przez textAnalysis/LLM; --raw szuka dokładnie podanym tekstem)
    python -m trustedSources warm
"""

import argparse
import asyncio
import json
import sys

from .registry import RegistryError, default_registry
from .service import ensure_detected, queries_for_text, search, search_context, warm


def _print_sources() -> None:
    sources = default_registry().list()
    width = max((len(source.id) for source in sources), default=10)
    for source in sources:
        check = source.last_check
        status = "" if check is None else ("ok" if check.ok else f"ERR {check.error}")
        flag = " " if source.enabled else "x"
        print(f"{flag} {source.id:<{width}}  {source.adapter:<20} {status:<22} {source.url}")
    print(f"\n{len(sources)} sources (whitelist.py)")


async def _check(source_id: str | None) -> None:
    registry = default_registry()
    sources = registry.list() if source_id is None else [registry.get(source_id)]
    async with search_context() as ctx:
        updated = await ensure_detected(registry, ctx, sources, force=True)
    for source in updated:
        check = source.last_check
        result = (check.detail if check.ok else f"ERR {check.error}") if check else ""
        print(f"{source.id:<50} {source.adapter:<20} {result}")


async def _search(text: str, as_json: bool, raw: bool) -> None:
    queries = [text] if raw else await queries_for_text(text)
    report = await search(queries, detect_pending=True)
    if as_json:
        print(json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2))
        return
    print(f"queries: {report.queries}")
    print(f"{len(report.hits)} hits from {report.sources_queried} sources in {report.duration_ms} ms")
    for hit in report.hits:
        date = hit.published_at.date().isoformat() if hit.published_at else "-"
        print(f"  [{hit.kind}] {hit.score:5.2f} {hit.source_name} | {date} | {hit.title}\n        {hit.url}")
    for failure in report.failures:
        print(f"  ! {failure.source_id}: {failure.kind}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m trustedSources", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("list")
    check = commands.add_parser("check")
    check.add_argument("id", nargs="?")
    check.add_argument("--all", action="store_true")
    find = commands.add_parser("search")
    find.add_argument("text")
    find.add_argument("--json", action="store_true")
    find.add_argument("--raw", action="store_true")
    commands.add_parser("warm")
    args = parser.parse_args(argv)

    try:
        if args.command == "list":
            _print_sources()
        elif args.command == "check":
            if not args.all and not args.id:
                parser.error("check needs <id> or --all")
            asyncio.run(_check(None if args.all else args.id))
        elif args.command == "search":
            asyncio.run(_search(args.text, args.json, args.raw))
        elif args.command == "warm":
            print(asyncio.run(warm()))
    except RegistryError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
