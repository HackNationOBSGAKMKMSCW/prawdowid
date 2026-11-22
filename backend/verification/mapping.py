"""Scraped articles -> source objects of the two assessment modules.

Both mappings use the same ids (``art1``, ``art2`` ...), so quotes cited by either
assessment can be linked back to ``ScrapingReport.articles`` on the front end.
"""

from __future__ import annotations

from typing import Any

from articleScraping.models import ScrapedArticle, ScrapingReport

from . import _analysis


def article_id(index: int) -> str:
    return f"art{index + 1}"


def _usable(report: ScrapingReport) -> list[tuple[str, ScrapedArticle]]:
    return [
        (article_id(index), article)
        for index, article in enumerate(report.articles)
        if article.text.strip()
    ]


def to_truth_sources(report: ScrapingReport) -> list[dict[str, Any]]:
    """Sources for ``inputDataAnalysis.analyze_async`` (validated there as ``TruthSource``)."""
    return [
        {
            "id": source_id,
            "content": article.text,
            "title": article.title,
            "url": article.url,
            "published_at": article.published_at.date() if article.published_at else None,
        }
        for source_id, article in _usable(report)
    ]


def to_reference_sources(report: ScrapingReport) -> list[Any]:
    """``ReferenceSource`` objects for the claim verdict (document sources, ``kind="korpus"``)."""
    reference_source = _analysis.verdict_schemas().ReferenceSource
    fetched_at = report.finished_at.isoformat() if report.finished_at else None
    return [
        reference_source(
            source_id=source_id,
            kind="korpus",
            title=article.title or "",
            publisher=article.publisher or article.site or "",
            url=article.url,
            published_at=article.published_at.date().isoformat() if article.published_at else None,
            text=article.text,
            fetched_at=fetched_at,
        )
        for source_id, article in _usable(report)
    ]
