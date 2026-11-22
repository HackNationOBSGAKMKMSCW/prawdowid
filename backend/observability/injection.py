"""Independent prompt-injection heuristics (scenario E), used by modules without a sanitizer.

The textAnalysis ``InputSanitizer`` has its own patterns; this detector covers the other
entry points (e.g. inputDataAnalysis user text and truth sources) so every untrusted
text is checked at least once. Detection only logs, it never changes the input.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

PATTERNS: tuple[str, ...] = (
    r"zignoruj\s+(wszystkie\s+)?(poprzednie|powyższe|wcześniejsze)\s+(instrukcje|polecenia|zasady)",
    r"ignore\s+(all\s+)?(previous|prior|above)\s+(instructions|prompts|rules)",
    r"disregard\s+(all\s+)?(previous|prior|above)",
    r"zapomnij\s+o\s+(wszystkim|zasadach|instrukcjach)",
    r"jesteś\s+teraz\b",
    r"you\s+are\s+now\b",
    r"od\s+teraz\s+(jesteś|odpowiadasz|działasz)",
    r"act\s+as\s+(a\s+|an\s+)?(different|new|unrestricted)",
    r"system\s*prompt",
    r"(ujawnij|pokaż|wypisz)\s+(swój\s+|swoje\s+)?(prompt|instrukcj)",
    r"reveal\s+(your\s+)?(system\s+)?(prompt|instructions)",
    r"developer\s+mode|tryb\s+dewelopera",
    r"\bjailbreak\b|\bDAN\b",
    r"(oceń|oznacz|zwróć)\s+(ten\s+)?tekst\s+jako\s+(wiarygodny|prawdziwy|neutralny)",
    r"(rate|mark|classify)\s+this\s+(text|article)\s+as\s+(true|reliable|neutral|credible)",
    r"<\s*/?\s*(system|assistant|untrusted_text|instructions?)\s*>",
    r"\[\s*(system|inst)\s*\]|<\|im_(start|end)\|>",
)

_COMPILED = tuple(re.compile(pattern, re.IGNORECASE) for pattern in PATTERNS)


@dataclass(frozen=True)
class InjectionMatch:
    pattern: str
    snippet: str
    start: int


def scan(text: str, *, context_chars: int = 30) -> InjectionMatch | None:
    """Return the first match (pattern + short snippet around it) or None."""
    if not text:
        return None
    for regex in _COMPILED:
        match = regex.search(text)
        if match:
            left = max(0, match.start() - context_chars)
            right = min(len(text), match.end() + context_chars)
            snippet = " ".join(text[left:right].split())
            return InjectionMatch(pattern=regex.pattern, snippet=snippet, start=match.start())
    return None
