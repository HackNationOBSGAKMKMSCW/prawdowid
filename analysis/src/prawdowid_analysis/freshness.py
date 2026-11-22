"""Aktualność źródeł względem CZASU ZDARZENIA, którego dotyczy twierdzenie.

- Data odniesienia (`event_reference`) pochodzi z treści twierdzenia:
  * twierdzenie z datą („w 2014 roku”, „1 maja 2004”, „w kwietniu 2026”, „2004-05-01”)
    -> najpóźniejsza wymieniona data (dla roku: 31 grudnia, dla miesiąca: ostatni dzień),
    nie późniejsza niż dzień analizy;
  * twierdzenie o stanie obecnym („obecnie”, „teraz”, „dziś”…) albo bez daty
    -> dzień analizy.
- Wiek źródła = dni od publikacji (`published_at`) do daty odniesienia. Wartość ujemna
  oznacza źródło opublikowane PO zdarzeniu (relacja, podsumowanie) – nie jest stare.
- Źródło opublikowane wcześniej niż limit (`VERDICT_MAX_SOURCE_AGE_DAYS`, domyślnie 730 dni)
  PRZED datą odniesienia jest ARCHIWALNE względem tego twierdzenia: flaga, ostrzeżenie
  i atrybut w prompcie. To samo źródło może być archiwalne dla jednego twierdzenia,
  a aktualne dla innego.
- Data pobrania (`fetched_at`) mówi, kiedy system pozyskał treść – nie zastępuje daty
  publikacji. Źródło bez daty publikacji dostaje flagę `brak_daty_publikacji`, a z datą
  późniejszą niż dzień analizy – `data_publikacji_w_przyszlosci`.
- `recency_factor` preferuje źródła bliskie zdarzeniu (lub późniejsze od niego) przy
  wyborze fragmentów.
"""

import calendar
import contextlib
import re
from dataclasses import dataclass
from datetime import UTC, date, datetime

from .schemas import ReferenceSource

RECENCY_WEIGHT = 0.3  # maksymalna premia do wyniku wyszukiwania za świeżość (30%)

FLAG_ARCHIVAL = "material_archiwalny"
FLAG_NO_DATE = "brak_daty_publikacji"
FLAG_FUTURE_DATE = "data_publikacji_w_przyszlosci"

BASIS_EVENT_DATE = "data_zdarzenia_z_twierdzenia"
BASIS_PRESENT = "stan_obecny"
BASIS_NO_DATE = "brak_daty_zdarzenia"

MIN_YEAR = 1800
_PRESENT_RE = re.compile(
    r"\b(obecnie|aktualnie|teraz|dzi[sś]|dzisiaj|wsp[oó]łcze[sś]nie|w tej chwili|"
    r"obecn\w*|aktualn\w*|currently|nowadays|today|now)\b",
    re.IGNORECASE,
)
_MONTHS = {
    "stycz": 1, "lut": 2, "mar": 3, "kwie": 4, "maj": 5, "czerw": 6,
    "lip": 7, "sierp": 8, "wrze": 9, "pa[zź]dziern": 10, "listopad": 11, "grud": 12,
}  # fmt: skip
_MONTH_RE = "|".join(f"{stem}\\w*" for stem in _MONTHS)
# Liczby z jednostką nie są latami („2499 m”, „1603 m n.p.m.”, „2010 zł”).
_UNIT = r"(?!\s*(?:m\b|km|cm|mm|m²|ha|kg|g\b|t\b|zł|z[lł]|eur|usd|\$|%|proc|tys|mln|mld|os[oó]b|metr|mieszk))"
_ISO_DATE_RE = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
_DOT_DATE_RE = re.compile(r"\b(\d{1,2})\.(\d{1,2})\.(\d{4})\b")
_DAY_MONTH_YEAR_RE = re.compile(rf"\b(\d{{1,2}})\s+({_MONTH_RE})\s+(\d{{4}})\b", re.IGNORECASE)
_MONTH_YEAR_RE = re.compile(rf"\b({_MONTH_RE})\s+(\d{{4}})\b", re.IGNORECASE)
_YEAR_RE = re.compile(rf"\b(\d{{4}})\b{_UNIT}", re.IGNORECASE)


def utc_now() -> datetime:
    return datetime.now(UTC)


def iso_timestamp(moment: datetime) -> str:
    """Znacznik czasu ISO 8601 w UTC, z dokładnością do sekundy."""
    return moment.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_date(value: str | None) -> date | None:
    """Data z `YYYY-MM-DD` albo pełnego znacznika ISO; None, gdy nie da się odczytać."""
    if not value:
        return None
    try:
        return date.fromisoformat(value.strip()[:10])
    except ValueError:
        return None


@dataclass(frozen=True)
class EventReference:
    date: date
    basis: str  # BASIS_EVENT_DATE | BASIS_PRESENT | BASIS_NO_DATE


def _month(word: str) -> int | None:
    lowered = word.lower()
    for stem, number in _MONTHS.items():
        if re.match(stem.strip(), lowered):
            return number
    return None


def _valid(year: int, today: date) -> bool:
    return MIN_YEAR <= year <= today.year + 10


def _end_of_month(year: int, month: int) -> date:
    return date(year, month, calendar.monthrange(year, month)[1])


def event_dates(claim: str, today: date) -> list[date]:
    """Wszystkie daty zdarzeń wymienione w twierdzeniu (rok -> koniec roku, miesiąc -> koniec miesiąca)."""
    found: list[date] = []
    taken: list[tuple[int, int]] = []

    def add(span: tuple[int, int], value: date | None) -> None:
        if value is not None and not any(s <= span[0] < e for s, e in taken):
            taken.append(span)
            found.append(value)

    for m in _ISO_DATE_RE.finditer(claim):
        if _valid(int(m[1]), today):
            add(m.span(), parse_date(m[0]))
    for m in _DOT_DATE_RE.finditer(claim):
        if _valid(int(m[3]), today):
            with contextlib.suppress(ValueError):
                add(m.span(), date(int(m[3]), int(m[2]), int(m[1])))
    for m in _DAY_MONTH_YEAR_RE.finditer(claim):
        month = _month(m[2])
        if month and _valid(int(m[3]), today):
            with contextlib.suppress(ValueError):
                add(m.span(), date(int(m[3]), month, int(m[1])))
    for m in _MONTH_YEAR_RE.finditer(claim):
        month = _month(m[1])
        if month and _valid(int(m[2]), today):
            add(m.span(), _end_of_month(int(m[2]), month))
    for m in _YEAR_RE.finditer(claim):
        if _valid(int(m[1]), today):
            add(m.span(), date(int(m[1]), 12, 31))
    return found


def event_reference(claim: str, today: date) -> EventReference:
    """Data, względem której oceniamy, czy źródło jest stare."""
    if _PRESENT_RE.search(claim):
        return EventReference(today, BASIS_PRESENT)
    dates = event_dates(claim, today)
    if not dates:
        return EventReference(today, BASIS_NO_DATE)
    return EventReference(min(max(dates), today), BASIS_EVENT_DATE)


def age_days(source: ReferenceSource, reference: date) -> int | None:
    """Dni od publikacji do daty odniesienia (ujemne: źródło po zdarzeniu)."""
    published = parse_date(source.published_at)
    return None if published is None else (reference - published).days


def annotate(
    source: ReferenceSource, reference: date, today: date, max_age_days: int
) -> ReferenceSource:
    """Wiek i flagi aktualności źródła względem daty odniesienia twierdzenia."""
    age = age_days(source, reference)
    published = parse_date(source.published_at)
    flags = [
        f
        for f in source.freshness_flags
        if f not in (FLAG_ARCHIVAL, FLAG_NO_DATE, FLAG_FUTURE_DATE)
    ]
    if published is None:
        flags.append(FLAG_NO_DATE)
    elif published > today:
        flags.append(FLAG_FUTURE_DATE)
    elif age is not None and age > max_age_days:
        flags.append(FLAG_ARCHIVAL)
    return source.model_copy(update={"age_days": age, "freshness_flags": flags})


def claim_independent(source: ReferenceSource) -> ReferenceSource:
    """Źródło bez wieku i flagi archiwalnej – te zależą od twierdzenia (do list globalnych)."""
    flags = [f for f in source.freshness_flags if f != FLAG_ARCHIVAL]
    return source.model_copy(update={"age_days": None, "freshness_flags": flags})


def is_archival(source: ReferenceSource) -> bool:
    return FLAG_ARCHIVAL in source.freshness_flags


def recency_factor(source: ReferenceSource, max_age_days: int) -> float:
    """Premia w (0, 1]: 1.0 dla źródła z dnia zdarzenia lub późniejszego, 0.5 na granicy
    limitu, 0.33 przy dwukrotności. Z równie trafnych wygrywa bliższe zdarzeniu. 0 bez daty."""
    if source.age_days is None or max_age_days <= 0 or FLAG_FUTURE_DATE in source.freshness_flags:
        return 0.0
    return max_age_days / (max_age_days + max(source.age_days, 0))


def archival_warning(
    source: ReferenceSource, reference: EventReference, max_age_days: int, claim_id: str
) -> str:
    years = (source.age_days or 0) / 365.25
    what = (
        f"daty zdarzenia z twierdzenia ({reference.date.isoformat()})"
        if reference.basis == BASIS_EVENT_DATE
        else f"dnia analizy ({reference.date.isoformat()}, twierdzenie o stanie obecnym lub bez daty)"
    )
    return (
        f"{claim_id}: źródło [{source.source_id}] to materiał archiwalny – opublikowane "
        f"{source.published_at}, {source.age_days} dni (ok. {years:.1f} r.) przed datą "
        f"odniesienia, czyli względem {what}; limit {max_age_days} dni."
    )
