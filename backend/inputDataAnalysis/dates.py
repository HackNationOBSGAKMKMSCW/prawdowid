"""Deterministyczne operacje na datach: przedziały, odległości, wyrażenia względne, formatowanie PL.

Każda data jest przedziałem ``[start, end]`` (włącznie), więc „marzec 2024” to
``[2024-03-01, 2024-03-31]``, a „12 marca 2024” to ``[2024-03-12, 2024-03-12]``.
"""

from __future__ import annotations

import calendar
import re
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

GRANULARITIES = ("day", "week", "month", "quarter", "year", "range", "unknown")

MONTHS_NOM = (
    "styczeń", "luty", "marzec", "kwiecień", "maj", "czerwiec",
    "lipiec", "sierpień", "wrzesień", "październik", "listopad", "grudzień",
)  # fmt: skip
MONTHS_GEN = (
    "stycznia", "lutego", "marca", "kwietnia", "maja", "czerwca",
    "lipca", "sierpnia", "września", "października", "listopada", "grudnia",
)  # fmt: skip
MONTHS_LOC = (
    "styczniu", "lutym", "marcu", "kwietniu", "maju", "czerwcu",
    "lipcu", "sierpniu", "wrześniu", "październiku", "listopadzie", "grudniu",
)  # fmt: skip
WEEKDAYS_NOM = ("poniedziałek", "wtorek", "środa", "czwartek", "piątek", "sobota", "niedziela")

# Odmiany i skróty nazw dni tygodnia („w środę”, „we wtorek”, „sob.”).
_WEEKDAY_FORMS: dict[str, int] = {}
for _number, _forms in enumerate(
    (
        "poniedziałek poniedziałku poniedziałkiem pon pn",
        "wtorek wtorku wtorkiem wt",
        "środa środę środy środzie środą śr sr",
        "czwartek czwartku czwartkiem czw cz",
        "piątek piątku piątkiem pt",
        "sobota sobotę soboty sobocie sobotą sob sb",
        "niedziela niedzielę niedzieli niedzielą niedz nd",
    )
):
    for _form in _forms.split():
        _WEEKDAY_FORMS[_form] = _number


@dataclass(frozen=True)
class TimeRef:
    """Przedział czasu z granularnością."""

    start: date
    end: date
    granularity: str = "day"

    @classmethod
    def day(cls, d: date) -> TimeRef:
        return cls(d, d, "day")

    @classmethod
    def from_iso(cls, iso_start: str, iso_end: str = "", granularity: str = "") -> TimeRef | None:
        """Buduje przedział z napisów ISO (``YYYY``, ``YYYY-MM``, ``YYYY-MM-DD``, ``YYYY-Qn``).

        Zwraca ``None``, gdy początku nie da się odczytać.
        """
        first = _parse_partial(iso_start)
        if first is None:
            return None
        start, end, gran = first
        if iso_end and iso_end.strip():
            second = _parse_partial(iso_end)
            if second is not None and second[1] >= start:
                end = second[1]
                gran = _infer_granularity(start, end)
        if granularity in ("week", "quarter") and gran == "range":
            gran = granularity
        return cls(start, end, gran)

    @property
    def width_days(self) -> int:
        return (self.end - self.start).days + 1


def _last_day(year: int, month: int) -> int:
    return calendar.monthrange(year, month)[1]


def _parse_partial(value: str) -> tuple[date, date, str] | None:
    s = (value or "").strip()
    if not s:
        return None
    s = s[:10] if re.match(r"^\d{4}-\d{2}-\d{2}T", s) else s
    try:
        if m := re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", s):
            d = date(int(m[1]), int(m[2]), int(m[3]))
            return d, d, "day"
        if m := re.fullmatch(r"(\d{4})-(\d{2})", s):
            y, mo = int(m[1]), int(m[2])
            return date(y, mo, 1), date(y, mo, _last_day(y, mo)), "month"
        if m := re.fullmatch(r"(\d{4})-?Q([1-4])", s, flags=re.IGNORECASE):
            y, q = int(m[1]), int(m[2])
            first_month = 3 * (q - 1) + 1
            last_month = first_month + 2
            return date(y, first_month, 1), date(y, last_month, _last_day(y, last_month)), "quarter"
        if m := re.fullmatch(r"(\d{4})", s):
            y = int(m[1])
            return date(y, 1, 1), date(y, 12, 31), "year"
    except ValueError:
        return None
    return None


def _infer_granularity(start: date, end: date) -> str:
    if start == end:
        return "day"
    if start.day == 1 and start.year == end.year:
        if start.month == end.month and end.day == _last_day(end.year, end.month):
            return "month"
        if (start.month, end.month, end.day) == (1, 12, 31):
            return "year"
    return "range"


def dist(a: TimeRef, b: TimeRef) -> int:
    """Odległość między przedziałami w dniach (0, gdy się nakładają)."""
    if a.end < b.start:
        return (b.start - a.end).days
    if b.end < a.start:
        return (a.start - b.end).days
    return 0


# --- wyrażenia względne -----------------------------------------------------------------------

_BARE_UNIT = re.compile(r"^(tydzień|tydzien|miesiąc|miesiac|rok|dzień|dzien)\b", re.IGNORECASE)


def parse_relative(expression: str, base: date) -> TimeRef | None:
    """Liczy wyrażenie względne („wczoraj”, „3 dni temu”, „w zeszłym tygodniu”) względem ``base``.

    Dla wyrażeń tygodniowych, miesięcznych i rocznych zwraca szerszy przedział, żeby nie
    zgłaszać fałszywych niezgodności.
    """
    expr = (expression or "").strip()
    if not expr:
        return None
    parsed = _dateparse(expr, base)
    if parsed is None and _BARE_UNIT.match(expr):
        parsed = _dateparse("1 " + expr, base)
    if parsed is None:
        return None
    low = expr.lower()
    if "tydz" in low or "tygod" in low:
        return TimeRef(parsed - timedelta(days=3), parsed + timedelta(days=3), "week")
    if "miesi" in low:
        return TimeRef(
            date(parsed.year, parsed.month, 1),
            date(parsed.year, parsed.month, _last_day(parsed.year, parsed.month)),
            "month",
        )
    if re.search(r"\b(rok|roku|lat|lata)\b", low):
        return TimeRef(date(parsed.year, 1, 1), date(parsed.year, 12, 31), "year")
    return TimeRef.day(parsed)


def _dateparse(expr: str, base: date) -> date | None:
    import dateparser  # import leniwy: pierwszy import trwa ~1 s

    try:
        result = dateparser.parse(
            expr,
            languages=["pl"],
            settings={
                "RELATIVE_BASE": datetime.combine(base, time()),
                "PREFER_DATES_FROM": "past",
                "RETURN_AS_TIMEZONE_AWARE": False,
            },
        )
    except Exception:  # dateparser potrafi rzucić na egzotycznym wejściu
        return None
    return result.date() if result else None


# --- dzień tygodnia ---------------------------------------------------------------------------


def parse_weekday(text: str) -> int | None:
    """Zwraca numer dnia tygodnia (0 = poniedziałek) z polskiej nazwy w dowolnej odmianie."""
    for word in re.findall(r"\w+", (text or "").lower()):
        if word in _WEEKDAY_FORMS:
            return _WEEKDAY_FORMS[word]
    return None


# --- formatowanie PL --------------------------------------------------------------------------


def fmt_day(d: date) -> str:
    return f"{d.day} {MONTHS_GEN[d.month - 1]} {d.year}"


def _fmt_range(ref: TimeRef) -> str:
    if ref.start.year == ref.end.year and ref.start.month == ref.end.month:
        return f"{ref.start.day}–{ref.end.day} {MONTHS_GEN[ref.end.month - 1]} {ref.end.year}"
    return f"{fmt_day(ref.start)} – {fmt_day(ref.end)}"


def _quarter(ref: TimeRef) -> str:
    return f"{(ref.start.month - 1) // 3 + 1}. kwartał {ref.start.year} r."


def fmt_on(ref: TimeRef) -> str:
    """Forma po „datuje na …”: „na 12 marca 2024”, „na marzec 2024”, „na 2024 r.”."""
    g = ref.granularity
    if g == "day":
        return f"na {fmt_day(ref.start)}"
    if g == "month":
        return f"na {MONTHS_NOM[ref.start.month - 1]} {ref.start.year}"
    if g == "year":
        return f"na {ref.start.year} r."
    if g == "quarter":
        return f"na {_quarter(ref)}"
    return f"na okres {_fmt_range(ref)}"


def fmt_at(ref: TimeRef) -> str:
    """Forma okolicznika czasu: „12 marca 2024”, „w marcu 2024”, „w 2024 r.”."""
    g = ref.granularity
    if g == "day":
        return fmt_day(ref.start)
    if g == "month":
        return f"w {MONTHS_LOC[ref.start.month - 1]} {ref.start.year}"
    if g == "year":
        return f"w {ref.start.year} r."
    if g == "quarter":
        return f"w {(ref.start.month - 1) // 3 + 1}. kwartale {ref.start.year} r."
    return f"w okresie {_fmt_range(ref)}"


def fmt_from(ref: TimeRef) -> str:
    """Forma po „pochodzą …”: „z 12 marca 2015”, „z marca 2015”, „z 2015 r.”."""
    g = ref.granularity
    if g == "day":
        return f"z {fmt_day(ref.start)}"
    if g == "month":
        return f"z {MONTHS_GEN[ref.start.month - 1]} {ref.start.year}"
    if g == "year":
        return f"z {ref.start.year} r."
    if g == "quarter":
        return f"z {(ref.start.month - 1) // 3 + 1}. kwartału {ref.start.year} r."
    return f"z okresu {_fmt_range(ref)}"


def plural(n: int, one: str, few: str, many: str) -> str:
    """Polska odmiana liczebnika: 1 dzień, 2 dni, 5 dni; 1 rok, 3 lata, 5 lat."""
    if n == 1:
        return f"{n} {one}"
    if n % 10 in (2, 3, 4) and n % 100 not in (12, 13, 14):
        return f"{n} {few}"
    return f"{n} {many}"


def fmt_days(n: int) -> str:
    return plural(n, "dzień", "dni", "dni")


def humanize_days(days: int) -> str:
    """Przybliżony czas po polsku: „4 lata”, „3 miesiące”, „12 dni”."""
    if days >= 365:
        return plural(days // 365, "rok", "lata", "lat")
    if days >= 60:
        return plural(days // 30, "miesiąc", "miesiące", "miesięcy")
    return fmt_days(days)
