"""Prompt-injection heuristics shared by every entry point of untrusted text.

``scan`` checks user text, scraped articles and other sources; ``InputSanitizer``
(textAnalysis) uses the same patterns, and ``neutralize_tags`` defuses the tags that mark
roles and data blocks in our prompts. Before matching, text is normalized (NFKC,
invisible and bidi characters removed), so "z\u200bignoruj" or full-width letters do not
slip through. Polish patterns accept letters with and without diacritics.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

# Zero-width, bidi and other invisible characters used to split keywords.
INVISIBLE = re.compile("[\u00ad\u180e\u200b-\u200f\u202a-\u202e\u2060-\u2064\u2066-\u2069\ufeff]")

PATTERNS: tuple[str, ...] = (
    r"zignoruj\s+(wszystkie\s+)?(poprzednie|powy[zż]sze|wcze[sś]niejsze)\s+(instrukcje|polecenia|zasady)",
    r"ignore\s+(all\s+|any\s+|the\s+)?(previous|prior|above|earlier)\s+(instructions|prompts|rules)",
    r"disregard\s+(all\s+|any\s+|the\s+)?(previous|prior|above|earlier)",
    r"zapomnij\s+o\s+(wszystkim|zasadach|instrukcjach|poleceniach)",
    r"nie\s+stosuj\s+si[eę]\s+do\s+(poprzednich|powy[zż]szych|wcze[sś]niejszych)",
    r"jeste[sś]\s+teraz\b",
    r"you\s+are\s+now\b",
    r"od\s+teraz\s+(jeste[sś]|odpowiadasz|dzia[lł]asz)",
    r"act\s+as\s+(a\s+|an\s+)?(different|new|unrestricted)",
    r"system\s*prompt",
    r"(ujawnij|poka[zż]|wypisz)\s+(sw[oó]j\s+|swoje\s+)?(prompt|instrukcj)",
    r"reveal\s+(your\s+)?(system\s+)?(prompt|instructions)",
    r"developer\s+mode|tryb\s+dewelopera",
    r"\bjailbreak\b",
    r"(?-i:\bDAN\b)",  # only upper case: "dań" and the name "Dan" are ordinary words
    r"(oce[nń]|oznacz|zwr[oó][cć])\s+(ten\s+)?tekst\s+jako\s+(wiarygodny|prawdziwy|neutralny)",
    r"(rate|mark|classify)\s+this\s+(text|article|claim)\s+as\s+(true|reliable|neutral|credible)",
    r"<\s*/?\s*(system|assistant|untrusted_text|instructions?)\s*>",
    r"\[\s*/?\s*(system|inst)\s*\]|<\|im_(start|end)\|>",
)
_COMPILED = tuple(re.compile(pattern, re.IGNORECASE) for pattern in PATTERNS)

# Tags that delimit roles and data blocks in our prompts (and chat-template tokens).
_PROMPT_TAG = re.compile(
    r"<\s*/?\s*(?:untrusted_text|system|assistant|user|instructions?|tekst|zrodl[oa](?:_prawdy)?"
    r"|claim|source|context|zrodla)\b[^<>]{0,200}>|<\|[a-z_]{1,20}\|>",
    re.IGNORECASE,
)


def normalize(text: str) -> str:
    """NFKC and no invisible characters: what a model reads, without the disguise."""
    return INVISIBLE.sub("", unicodedata.normalize("NFKC", text))


def neutralize_tags(text: str) -> str:
    """Make prompt tags inert: ``<`` and ``>`` become ``‹`` and ``›`` (same length)."""
    return _PROMPT_TAG.sub(lambda m: m.group(0).replace("<", "‹").replace(">", "›"), text)


@dataclass(frozen=True)
class InjectionMatch:
    pattern: str
    snippet: str
    start: int


def scan(text: str, *, context_chars: int = 30) -> InjectionMatch | None:
    """Return the first match (pattern + short snippet around it) or None."""
    if not text:
        return None
    text = normalize(text)
    for regex in _COMPILED:
        match = regex.search(text)
        if match:
            left = max(0, match.start() - context_chars)
            right = min(len(text), match.end() + context_chars)
            snippet = " ".join(text[left:right].split())
            return InjectionMatch(pattern=regex.pattern, snippet=snippet, start=match.start())
    return None
