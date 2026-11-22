"""Run text analysis, API reading and the trusted-source search, then print the evidence.

Usage (from backend/): python -m scripts.smoke_pipeline [--json] [text]
"""

import argparse
import asyncio
import json
import sys

import apiReading
import articleScraping
import observability
import textAnalysis
import trustedSources

DEFAULT_TEXT = "Ocieplenie klimatu to fałsz i nie jest realne. Nie ma dowodu, że to wina człowieka."


def _print_trusted(trusted: trustedSources.TrustedSearchReport) -> None:
    print(
        f"[trustedSources] Źródła prawdy: {len(trusted.hits)} trafień z "
        f"{trusted.sources_queried} źródeł w {trusted.duration_ms} ms; zapytania: {trusted.queries}",
        flush=True,
    )
    for hit in trusted.hits:
        date = hit.published_at.date().isoformat() if hit.published_at else "-"
        label = "sprawdź na bieżąco" if hit.kind == "reference" else date
        print(f"  [{hit.source_name}] {hit.title} ({label}) {hit.url}", flush=True)
    for failure in trusted.failures:
        print(f"  ! {failure.source_id}: {failure.kind}", flush=True)


async def main(text: str, as_json: bool, scrape: bool = False) -> int:
    analysis = await textAnalysis.run(text)
    results, trusted = await asyncio.gather(apiReading.run(analysis), trustedSources.run(analysis))
    report = await articleScraping.run(analysis, results, trusted=trusted) if scrape else None
    if as_json:
        reading_payload = [r.model_dump(mode="json") for r in results]
        payload = (
            reading_payload
            if report is None
            else {
                "reading_results": reading_payload,
                "trusted_sources": trusted.model_dump(mode="json"),
                "scraping_report": report.model_dump(mode="json", exclude={"user_input"}),
            }
        )
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        _print_trusted(trusted)
    if not as_json and report is not None:
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
        "--scrape", action="store_true", help="extract article text from discovered URLs"
    )
    args = parser.parse_args()
    observability.init()
    sys.exit(asyncio.run(_main_with_logging(args.text, args.as_json, args.scrape)))
