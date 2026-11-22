"""Run the analysis pipeline and optionally print its evidence.

Usage (from backend/): python -m scripts.smoke_pipeline [--json] [--no-scrape] [text]
"""

import argparse
import asyncio
import json
import sys

import observability
from pipeline import run_pipeline
from trustedSources.models import TrustedSearchReport

DEFAULT_TEXT = "Ocieplenie klimatu to fałsz i nie jest realne. Nie ma dowodu, że to wina człowieka."


def _print_trusted(trusted: TrustedSearchReport) -> None:
    print(
        f"[trustedSources] Źródła prawdy: {len(trusted.hits)} trafień z "
        f"{trusted.sources_queried} źródeł w {trusted.duration_ms} ms.",
        flush=True,
    )
    for hit in trusted.hits:
        date = hit.published_at.date().isoformat() if hit.published_at else "-"
        label = "sprawdź na bieżąco" if hit.kind == "reference" else date
        print(f"  [{hit.source_name}] {hit.title} ({label}) {hit.url}", flush=True)
    for failure in trusted.failures:
        print(f"  ! {failure.source_id}: {failure.kind}", flush=True)


async def main(text: str, as_json: bool, scrape: bool = True) -> int:
    final = await run_pipeline(text, scrape=scrape)
    results, report = final.reading_results, final.scraping_report
    if as_json:
        payload = final.to_dict()
        # Derived results are useful in smoke output; echoing submitted text is not.
        payload.pop("user_text", None)
        print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
    else:
        _print_trusted(final.trusted_sources)
        if report is not None:
            for article in report.articles:
                print(f"[articleScraping] {article.title or article.url} ({article.url})")
                print(article.text)
            for failure in report.failures:
                print(f"[articleScraping] {failure.kind}: {failure.url}")
    outcomes = [outcome for result in results for outcome in result.results]
    all_failed = bool(outcomes) and all(outcome.error is not None for outcome in outcomes)
    if all_failed:
        observability.log_abstain("search_failed", channel="smoke_pipeline")
    return 1 if all_failed else 0


async def _main_with_logging(text: str, as_json: bool, scrape: bool) -> int:
    with observability.request_scope("smoke_pipeline"):
        return await main(text, as_json, scrape)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("text", nargs="?", default=DEFAULT_TEXT)
    parser.add_argument("--json", action="store_true", dest="as_json")
    parser.add_argument(
        "--no-scrape",
        action="store_false",
        dest="scrape",
        help="skip extracting article text from discovered URLs (on by default)",
    )
    args = parser.parse_args()
    observability.init()
    sys.exit(asyncio.run(_main_with_logging(args.text, args.as_json, args.scrape)))
