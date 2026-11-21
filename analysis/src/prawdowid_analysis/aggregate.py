"""Werdykt zbiorczy dla całego tekstu, liczony regułą z werdyktów twierdzeń (bez LLM).

Reguły (w tej kolejności):
- brak twierdzeń                          -> nieweryfikowalny
- wszystkie twierdzenia: prawda           -> prawdziwy
- wszystkie twierdzenia: falsz            -> falszywy
- co najmniej jedno: falsz                -> zawiera_falsz
- co najmniej jedno: prawda (reszta nie)  -> czesciowo_potwierdzony
- wszystkie: blad_analizy                 -> blad_analizy
- pozostałe (brak danych, ew. z błędami)  -> brak_wystarczajacych_danych
"""

from collections import Counter
from collections.abc import Sequence

from .schemas import ClaimVerdict, TextVerdictValue


def _count(n: int, one: str, few: str, many: str) -> str:
    if n == 1:
        return f"{n} {one}"
    if n % 10 in (2, 3, 4) and n % 100 not in (12, 13, 14):
        return f"{n} {few}"
    return f"{n} {many}"


def aggregate(claims: Sequence[ClaimVerdict]) -> tuple[TextVerdictValue, str]:
    if not claims:
        return (
            "nieweryfikowalny",
            "Tekst nie zawiera twierdzeń faktograficznych, które można sprawdzić.",
        )

    counts = Counter(c.verdict for c in claims)
    total = len(claims)
    verdict: TextVerdictValue
    if counts["prawda"] == total:
        verdict = "prawdziwy"
    elif counts["falsz"] == total:
        verdict = "falszywy"
    elif counts["falsz"]:
        verdict = "zawiera_falsz"
    elif counts["prawda"]:
        verdict = "czesciowo_potwierdzony"
    elif counts["blad_analizy"] == total:
        verdict = "blad_analizy"
    else:
        verdict = "brak_wystarczajacych_danych"

    parts = [
        f"{counts[key]} – {label}"
        for key, label in (
            ("prawda", "prawda"),
            ("falsz", "fałsz"),
            ("brak_wystarczajacych_danych", "brak wystarczających danych"),
            ("blad_analizy", "błąd analizy"),
        )
        if counts[key]
    ]
    summary = (
        f"Sprawdzono {_count(total, 'twierdzenie', 'twierdzenia', 'twierdzeń')}: "
        + "; ".join(parts)
        + "."
    )
    return verdict, summary
