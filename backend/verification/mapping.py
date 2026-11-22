"""Scraped articles -> source objects of the two assessment modules.

Both mappings use the same ids (``art1``, ``art2`` ...), so quotes cited by either
assessment can be linked back to ``ScrapingReport.articles`` on the front end.

Pages behind links the user pasted (``source="user_text"``) are never evidence: anyone
could link their own page and "confirm" a claim, and a checked link would be compared with
itself. Only fact-check publishers and trusted sites count. Articles whose text carries
instructions for the model are left out of the manipulation/date check as well (the claim
verdict quarantines them on its own).
"""

from __future__ import annotations

import logging
from typing import Any

from articleScraping.models import ScrapedArticle, ScrapingReport
from observability.injection import scan

from . import _analysis


def article_id(index: int) -> str:
    return f"art{index + 1}"


logger = logging.getLogger(__name__)
USER_LINK = "user_text"


def _usable(report: ScrapingReport) -> list[tuple[str, ScrapedArticle]]:
    """Evidence articles: with text and not from a link the user pasted (ids stay stable)."""
    return [
        (article_id(index), article)
        for index, article in enumerate(report.articles)
        if article.text.strip() and article.source != USER_LINK
    ]


def _without_injection(
    articles: list[tuple[str, ScrapedArticle]],
) -> list[tuple[str, ScrapedArticle]]:
    clean = []
    for source_id, article in articles:
        hit = scan(f"{article.title or ''}\n{article.text}")
        if hit is None:
            clean.append((source_id, article))
        else:
            logger.warning(
                "source_quarantined source_id=%s site=%s pattern=%s",
                source_id,
                article.site,
                hit.pattern[:80],
            )
    return clean


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
        for source_id, article in _without_injection(_usable(report))
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
