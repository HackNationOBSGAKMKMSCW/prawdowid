"""Flagi werdyktu z jawnych reguł (bez LLM): sprzeczne źródła i nieaktualne źródła.

- `conflicting_sources`: wśród użytecznych dowodów (zweryfikowany cytat) są i takie, które
  potwierdzają, i takie, które obalają twierdzenie.
- `stale_source`: dowód rozstrzygający pochodzi ze źródła starszego niż próg zależny od
  typu twierdzenia (`published_at` względem `now`). Cytaty i opinie nie mają progu.
- `missing_context`, `source_status_warning`: na później (wymagają danych spoza dowodów).
"""

from datetime import UTC, date, datetime

from ..schemas import Claim, Passage
from .sources import EvidenceItem

# Po ilu dniach źródło jest nieaktualne dla danego typu twierdzenia. Stroić na public.
STALE_AFTER_DAYS: dict[str, int | None] = {
    "numeric": 365,  # dane liczbowe szybko się dezaktualizują
    "event": 365,
    "legal": 730,  # przepisy bywają nowelizowane
    "scientific": 1825,
    "quote": None,  # cytat nie traci ważności
    "opinion": None,
}


def today_utc() -> date:
    return datetime.now(UTC).date()


def parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def is_stale(passage: Passage, claim_type: str, now: date) -> bool:
    limit = STALE_AFTER_DAYS.get(claim_type)
    published = parse_date(passage.published_at)
    if limit is None or published is None:
        return False
    return (now - published).days > limit


def stale_items(items: list[EvidenceItem], claim: Claim, now: date) -> list[EvidenceItem]:
    return [i for i in items if is_stale(i.passage, claim.type, now)]


def has_conflict(items: list[EvidenceItem]) -> bool:
    stances = {i.stance for i in items}
    return "supports" in stances and "refutes" in stances


def compute_flags(claim: Claim, items: list[EvidenceItem], now: date) -> list[str]:
    """Flagi dla użytecznych dowodów (zweryfikowany cytat, stanowisko supports/refutes)."""
    flags = []
    if has_conflict(items):
        flags.append("conflicting_sources")
    if stale_items(items, claim, now):
        flags.append("stale_source")
    return flags
