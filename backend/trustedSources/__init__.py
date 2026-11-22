"""Search a runtime-editable whitelist of trusted sites for material matching a claim.

Pipeline use::

    report = await trustedSources.run(analysis)          # TrustedSearchReport
    await articleScraping.run(analysis, results, trusted=report)

Sources are managed with ``python -m trustedSources`` or the REST router in
``trustedSources.api``; see README.md.
"""

from .models import EvidenceHit, SourceFailure, TrustedSearchReport, TrustedSource
from .registry import SourceRegistry, default_registry
from .service import queries_for, run, search, warm

__all__ = [
    "EvidenceHit",
    "SourceFailure",
    "SourceRegistry",
    "TrustedSearchReport",
    "TrustedSource",
    "default_registry",
    "queries_for",
    "run",
    "search",
    "warm",
]
