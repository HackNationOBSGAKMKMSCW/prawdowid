"""Ranga źródeł (T1–T4) i niezależność, wspólne dla flags.py, strength.py i rules.py.

Poziomy według architektury (docs/prawdowid-architektura-v3.html, „Ranking źródeł T1–T4”):
- T1: prawo, statystyki, badania (`official_primary`, `public_data`, `research`),
- T2: fact-checkerzy i agencje (`fact_check`, `news_agency`),
- T3: media (`media`): dowód pomocniczy, nie liczy się do progu werdyktu,
- T4: blogi, social media: tylko dowód, że twierdzenie krąży (brak takiego `source_type`
  w kontrakcie, więc nie występuje w korpusie).

Ranga zależy wyłącznie od typu źródła, nie od domeny, autora ani popularności.
Niezależność: dwa dowody z tego samego dokumentu albo od tego samego wydawcy liczą się
jako jedno źródło (np. komunikat urzędu i jego kopia w newsletterze tego urzędu).
"""

import re
from dataclasses import dataclass

from ..schemas import Evidence, Passage

SOURCE_TIER: dict[str, int] = {
    "official_primary": 1,
    "public_data": 1,
    "research": 1,
    "fact_check": 2,
    "news_agency": 2,
    "media": 3,
}
STRONG_TIERS = (1, 2)  # T1–T2: tylko one liczą się do progu `confirmed`/`false`
MIN_INDEPENDENT_STRONG = 2  # „min. 2 niezależne źródła T1–T2”

_WS_RE = re.compile(r"\s+")


def tier_of(passage: Passage) -> int:
    return SOURCE_TIER.get(passage.source_type, 4)


def is_strong(passage: Passage) -> bool:
    return tier_of(passage) in STRONG_TIERS


def publisher_key(passage: Passage) -> str:
    return _WS_RE.sub(" ", passage.publisher).strip().casefold()


@dataclass(frozen=True)
class EvidenceItem:
    """Dowód połączony z pasażem, z którego pochodzi."""

    evidence: Evidence
    passage: Passage

    @property
    def stance(self) -> str:
        return self.evidence.stance

    @property
    def tier(self) -> int:
        return tier_of(self.passage)


def independent_sources(items: list[EvidenceItem], *, strong_only: bool = False) -> int:
    """Liczba niezależnych źródeł: różni wydawcy (różne dokumenty jednego wydawcy = 1)."""
    return len({publisher_key(i.passage) for i in items if not strong_only or is_strong(i.passage)})
