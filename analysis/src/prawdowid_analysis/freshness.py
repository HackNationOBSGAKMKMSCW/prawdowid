"""Aktualność źródeł: wiek materiału, limit czasowy i oznaczanie materiałów archiwalnych.

- Wiek liczymy od daty publikacji (`published_at`) do dnia analizy. Data pobrania
  (`fetched_at`) mówi, kiedy system pozyskał treść – nie zastępuje daty publikacji.
- Źródło starsze niż limit (`VERDICT_MAX_SOURCE_AGE_DAYS`, domyślnie 730 dni) jest
  ARCHIWALNE: dostaje flagę, ostrzeżenie w wyniku i atrybut w prompcie.
- Źródło bez daty publikacji dostaje flagę `brak_daty_publikacji` – jego
  aktualności nie da się ocenić.
- `recency_factor` wspiera preferowanie aktualnych danych przy wyborze fragmentów:
  premia do wyniku BM25 maleje z wiekiem, więc nowsze źródło wygrywa z równie trafnym starszym.
"""

from datetime import UTC, date, datetime

from .schemas import ReferenceSource

RECENCY_WEIGHT = 0.3  # maksymalna premia do wyniku wyszukiwania za świeżość (30%)

FLAG_ARCHIVAL = "material_archiwalny"
FLAG_NO_DATE = "brak_daty_publikacji"
FLAG_FUTURE_DATE = "data_publikacji_w_przyszlosci"


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


def age_days(source: ReferenceSource, today: date) -> int | None:
    published = parse_date(source.published_at)
    return None if published is None else (today - published).days


def annotate(source: ReferenceSource, now: datetime, max_age_days: int) -> ReferenceSource:
    """Uzupełnia wiek i flagi aktualności źródła (bez zmiany treści)."""
    age = age_days(source, now.date())
    flags = [
        f
        for f in source.freshness_flags
        if f not in (FLAG_ARCHIVAL, FLAG_NO_DATE, FLAG_FUTURE_DATE)
    ]
    if age is None:
        flags.append(FLAG_NO_DATE)
    elif age < 0:
        flags.append(FLAG_FUTURE_DATE)
    elif age > max_age_days:
        flags.append(FLAG_ARCHIVAL)
    return source.model_copy(update={"age_days": age, "freshness_flags": flags})


def is_archival(source: ReferenceSource) -> bool:
    return FLAG_ARCHIVAL in source.freshness_flags


def recency_factor(source: ReferenceSource, max_age_days: int) -> float:
    """Malejąca ze świeżością premia w (0, 1]: 1.0 z dnia analizy, 0.5 na granicy limitu,
    0.33 przy dwukrotności limitu. Ściśle maleje, więc z dwóch równie trafnych źródeł
    nowsze zawsze wygrywa – także wśród archiwalnych. 0 bez daty (najniżej)."""
    if source.age_days is None or source.age_days < 0 or max_age_days <= 0:
        return 0.0
    return max_age_days / (max_age_days + source.age_days)


def archival_warning(source: ReferenceSource, max_age_days: int) -> str:
    years = (source.age_days or 0) / 365.25
    return (
        f"Źródło [{source.source_id}] to materiał archiwalny: opublikowane "
        f"{source.published_at} ({source.age_days} dni, ok. {years:.1f} r. temu), "
        f"limit aktualności {max_age_days} dni. Może nie odzwierciedlać obecnego stanu rzeczy."
    )
