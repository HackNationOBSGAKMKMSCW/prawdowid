"""Wykrywanie prób wstrzyknięcia instrukcji w tekście źródeł (przy ingeście).

To tylko sygnał zapisany w payloadzie pasażu (`injection_flags`). Decyzję, co z nim
zrobić (rekord `security_event`, wykluczenie pasażu), podejmuje `verdict/security.py`.
Tekst źródła zawsze pozostaje danymi, nie instrukcją.
"""

import re

_PATTERNS: dict[str, re.Pattern[str]] = {
    # „zignoruj / pomiń / zapomnij (wszystkie) poprzednie instrukcje”
    "ignore_instructions": re.compile(
        r"\b(zignoruj|ignoruj|pomiń|pomin|zapomnij|odrzuć)\w*\s+(\w+\s+){0,3}"
        r"(instrukcj|polece|wytyczn|zasad|regu)\w*"
        r"|\b(ignore|disregard|forget)\s+(all\s+|any\s+)?(the\s+)?"
        r"(previous|prior|above|earlier)\s+(instructions|prompts?|rules)",
        re.IGNORECASE,
    ),
    # polecenie wydania konkretnego werdyktu; tylko tryb rozkazujący, bo „oceniamy jako”
    # w fact-checku to relacja, nie polecenie
    "verdict_command": re.compile(
        r"\b(oceń|oznacz|uznaj|zaklasyfikuj|sklasyfikuj|potraktuj|traktuj)\s+(\w+\s+){0,4}"
        r"(jako|za)\s+(potwierdzon|prawdziw|fałszyw|falszyw|wiarygodn)\w*"
        r"|\b(mark|rate|classify)\s+(\w+\s+){0,4}as\s+(true|confirmed|false|verified)",
        re.IGNORECASE,
    ),
    # zmiana roli modelu
    "role_override": re.compile(
        r"\b(jesteś\s+teraz|od\s+teraz\s+jesteś|udawaj,?\s+że|wciel\s+się)"
        r"|\b(you\s+are\s+now|act\s+as|pretend\s+to\s+be)\b",
        re.IGNORECASE,
    ),
    # odwołania do promptu systemowego / znaczniki ról i tagów
    "prompt_markup": re.compile(
        r"(prompt\w*\s+systemow\w*|system\s+prompt|<\|im_(start|end)\|>"
        r"|</?\s*(source|system|instructions?)\s*>|^\s*(system|assistant|user)\s*:)",
        re.IGNORECASE | re.MULTILINE,
    ),
}


def detect_injection(text: str) -> list[str]:
    """Nazwy wykrytych wzorców (posortowane); pusta lista = brak sygnałów."""
    return sorted(name for name, pattern in _PATTERNS.items() if pattern.search(text))
