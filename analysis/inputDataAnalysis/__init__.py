"""Analiza tekstu użytkownika: fragmenty manipulacyjne (taksonomia A–G) i spójność dat ze źródłami.

Użycie::

    from inputDataAnalysis import analyze, analyze_async

    result = analyze(tekst, [{"id": "s1", "content": "...", "published_at": "2024-03-12"}])
    result.manipulation.fragments  # podejrzane fragmenty z kategorią
    result.dates.dates_consistent  # False → result.dates.issues[*].description
"""

from .llm import LLMError
from .models import (
    AnalysisResult,
    DateIssue,
    DatesResult,
    ExtractedDate,
    ManipulationFragment,
    ManipulationResult,
    SkippedCheck,
    SourceEvidence,
    TruthSource,
)
from .pipeline import analyze, analyze_async

__all__ = [
    "AnalysisResult",
    "DateIssue",
    "DatesResult",
    "ExtractedDate",
    "LLMError",
    "ManipulationFragment",
    "ManipulationResult",
    "SkippedCheck",
    "SourceEvidence",
    "TruthSource",
    "analyze",
    "analyze_async",
]
