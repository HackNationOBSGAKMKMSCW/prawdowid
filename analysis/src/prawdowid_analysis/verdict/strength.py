"""Siła werdyktu (`high`/`medium`/`low`) z jawnych czynników, nigdy z oceny modelu.

Czynniki (każdy trafia do `strength.factors` jako zdanie po polsku):
- liczba niezależnych źródeł T1–T2 po stronie werdyktu (i czy jest wśród nich T1),
- zgodność cytatów: wszystkie dowody mają cytat zweryfikowany w tekście źródła
  (inne nie są w ogóle brane pod uwagę),
- aktualność: źródła nieaktualne dla typu twierdzenia albo bez daty publikacji,
- sprzeczność: czy jakieś użyteczne źródło mówi coś przeciwnego.

Poziom:
- `high`: ≥ 3 niezależne źródła T1–T2 albo ≥ 2 z co najmniej jednym T1, bez sprzeczności,
  bez źródeł nieaktualnych i bez braków dat,
- `medium`: próg werdyktu spełniony (≥ 2 niezależne T1–T2), ale coś obniża pewność,
- `low`: próg niespełniony.
"""

from dataclasses import dataclass
from datetime import date

from ..schemas import Claim, Strength
from .flags import stale_items
from .sources import MIN_INDEPENDENT_STRONG, EvidenceItem, independent_sources, is_strong


@dataclass(frozen=True)
class StrengthFactors:
    independent_strong: int  # niezależni wydawcy T1–T2 po stronie werdyktu
    has_t1: bool
    weak_sources: int  # źródła T3+ po stronie werdyktu (nie liczą się do progu)
    verified_quotes: int
    stale: int
    missing_date: int
    conflicting: bool

    def level(self) -> str:
        if self.independent_strong < MIN_INDEPENDENT_STRONG:
            return "low"
        enough = self.independent_strong >= 3 or self.has_t1
        clean = not self.conflicting and self.stale == 0 and self.missing_date == 0
        return "high" if enough and clean else "medium"

    def describe(self) -> list[str]:
        tier = " (w tym T1)" if self.has_t1 else ""
        out = [
            f"{self.independent_strong} niezależnych źródeł T1–T2{tier}, "
            f"wymagane {MIN_INDEPENDENT_STRONG}",
            f"{self.verified_quotes} cytatów zweryfikowanych w tekście źródła",
        ]
        if self.weak_sources:
            out.append(f"{self.weak_sources} źródeł niższej rangi (T3+), nie liczą się do progu")
        if self.stale:
            out.append(f"{self.stale} źródeł nieaktualnych dla tego typu twierdzenia")
        if self.missing_date:
            out.append(f"{self.missing_date} źródeł bez daty publikacji")
        if self.conflicting:
            out.append("część źródeł mówi coś przeciwnego")
        return out


def strength_factors(
    claim: Claim, side: list[EvidenceItem], *, conflicting: bool, now: date
) -> StrengthFactors:
    """Czynniki dla dowodów po stronie werdyktu (`side`: same supports albo same refutes)."""
    return StrengthFactors(
        independent_strong=independent_sources(side, strong_only=True),
        has_t1=any(i.tier == 1 for i in side),
        weak_sources=independent_sources([i for i in side if not is_strong(i.passage)]),
        verified_quotes=sum(1 for i in side if i.evidence.quote_verified),
        stale=len(stale_items(side, claim, now)),
        missing_date=sum(1 for i in side if not i.passage.published_at),
        conflicting=conflicting,
    )


def compute_strength(factors: StrengthFactors) -> Strength:
    return Strength(level=factors.level(), factors=factors.describe())
