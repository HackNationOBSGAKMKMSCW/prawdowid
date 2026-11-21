"""Map free-text fact-check ratings to a small set of verdicts.

Fact-checkers publish ratings as free text in many languages ("Fałsz",
"Mostly true", "Manipulacja"...). The adapter only needs a coarse class to pick
an icon and an overall summary, so this uses ordered keyword rules.
"""

import re
from collections import Counter
from collections.abc import Iterable
from enum import StrEnum


class Verdict(StrEnum):
    FALSE = "false"
    MISLEADING = "misleading"
    TRUE = "true"
    UNVERIFIED = "unverified"


class OverallVerdict(StrEnum):
    FALSE = "false"
    MISLEADING = "misleading"
    TRUE = "true"
    CONFLICTING = "conflicting"
    UNVERIFIED = "unverified"
    NO_DATA = "no_data"


# Order matters: the first matching rule wins. Qualified ratings ("częściowo
# fałsz", "half true") come before plain false/true, and negations
# ("nieprawda", "not true") come before "prawda"/"true".
_RULES: tuple[tuple[Verdict, re.Pattern[str]], ...] = tuple(
    (verdict, re.compile(pattern, re.IGNORECASE))
    for verdict, pattern in (
        (
            Verdict.UNVERIFIED,
            r"nieweryfikowaln|niesprawdzaln|unverifi|unproven|unsupported|"
            r"brak\s+dowod|brak\s+danych|no\s+evidence|not\s+enough|insufficient|research\s+in\s+progress",
        ),
        (Verdict.FALSE, r"mostly\s+(false|untrue)|raczej\s+(fałsz|falsz|nieprawd)"),
        (Verdict.TRUE, r"mostly\s+(true|correct|accurate)|raczej\s+prawd|w\s+większości\s+prawd"),
        (
            Verdict.MISLEADING,
            r"manipul|mislead|częściow|czesciow|partly|partial|half|mixture|mixed|"
            r"context|kontekst|wyrwan|exaggerat|przesad|distort|"
            r"niepełn|niepeln|in\s+part|satir|satyr|\bspin\b|cherry",
        ),
        (
            Verdict.FALSE,
            r"fałsz|falsz|nieprawd|false|fake|untrue|not\s+true|incorrect|wrong|"
            r"pants\s+on\s+fire|bezpodstawn|hoax|fabricat|zmyśl|zmysl|debunk|"
            r"\bmit\b|\bmyth|oszust|scam|nie\s+jest\s+prawd",
        ),
        (
            Verdict.TRUE,
            r"prawd|true|correct|accurate|potwierdz|confirmed|verified|rzeteln|\bfact\b",
        ),
    )
)


def classify_rating(rating: str | None) -> Verdict:
    """Classify one fact-check rating; unknown or empty ratings are unverified."""

    text = (rating or "").strip()
    if not text:
        return Verdict.UNVERIFIED
    for verdict, pattern in _RULES:
        if pattern.search(text):
            return verdict
    return Verdict.UNVERIFIED


def overall_verdict(verdicts: Iterable[Verdict]) -> OverallVerdict:
    """Combine per-review verdicts into one summary.

    True and false ratings together are reported as conflicting rather than
    averaged away. Otherwise the most frequent decisive class wins, with
    ties resolved towards the more cautious verdict.
    """

    counts = Counter(verdicts)
    if not counts:
        return OverallVerdict.NO_DATA

    false, misleading, true = (
        counts[Verdict.FALSE],
        counts[Verdict.MISLEADING],
        counts[Verdict.TRUE],
    )
    if false and true:
        return OverallVerdict.CONFLICTING
    if not (false or misleading or true):
        return OverallVerdict.UNVERIFIED
    if false >= misleading and false >= true:
        return OverallVerdict.FALSE
    if misleading >= true:
        return OverallVerdict.MISLEADING
    return OverallVerdict.TRUE
