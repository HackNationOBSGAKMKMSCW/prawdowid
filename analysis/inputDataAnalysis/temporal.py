"""Część B: spójność dat tekstu ze źródłami prawdy.

LLM tylko wyciąga daty i dopasowuje je do źródeł. Normalizacja, reguły i opisy (szablony)
są deterministyczne. Reguły to czyste funkcje na ``DateItem``, więc testy obywają się bez API.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date, timedelta

from . import prompts
from .dates import (
    WEEKDAYS_NOM,
    TimeRef,
    dist,
    fmt_at,
    fmt_day,
    fmt_days,
    fmt_from,
    fmt_on,
    humanize_days,
    parse_relative,
    parse_weekday,
)
from .llm import StructuredCall, structured_call
from .models import (
    DateIssue,
    DatesResult,
    ExtractedDate,
    LLMDatesResponse,
    LLMSourceMatch,
    SkippedCheck,
    TruthSource,
)
from .spans import locate_quote

TOL_DAYS = 1
HIGH_MISMATCH_DAYS = 30
RECENCY_THRESHOLD = 0.6
STALE_DAYS = 365
# Po ilu dniach zdarzenie przestaje być „bieżące” dla danej kategorii tekstu.
FRESHNESS_DAYS = {"breaking": 3, "political_legal": 30, "economic": 365, "other": 30}

_SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2}


@dataclass
class SourceMatch:
    source: TruthSource
    quote: str
    ref: TimeRef | None
    status: str = "unknown"  # occurred | planned | unknown


@dataclass
class DateItem:
    id: str
    quote: str
    start: int
    end: int
    what: str
    role: str
    tense: str
    ref: TimeRef | None
    recency: float = 0.0
    absolute_given: bool = False
    relative_expression: str = ""
    relative_ref: TimeRef | None = None
    weekday_mentioned: str = ""
    match: SourceMatch | None = None


@dataclass
class _Ctx:
    items: list[DateItem]
    t_a: date | None
    category: str
    sources: Sequence[TruthSource]
    issues: list[DateIssue] = field(default_factory=list)
    skipped: dict[tuple[str, str], SkippedCheck] = field(default_factory=dict)

    def skip(self, check: str, reason: str) -> None:
        self.skipped.setdefault((check, reason), SkippedCheck(check=check, reason=reason))

    def add(
        self,
        code: str,
        severity: str,
        description: str,
        item: DateItem | None = None,
        delta: int | None = None,
    ) -> None:
        match = item.match if item else None
        self.issues.append(
            DateIssue(
                code=code,
                severity=severity,
                description=description,
                input_quote=item.quote if item else None,
                start=item.start if item else None,
                end=item.end if item else None,
                source_id=match.source.id if match else None,
                source_quote=match.quote if match else None,
                delta_days=delta,
            )
        )


# --- reguły -----------------------------------------------------------------------------------


def _check_weekday(ctx: _Ctx, it: DateItem) -> None:
    if not it.weekday_mentioned or not it.absolute_given:
        return
    if it.ref is None or it.ref.granularity != "day":
        return
    mentioned = parse_weekday(it.weekday_mentioned)
    actual = it.ref.start.weekday()
    if mentioned is not None and mentioned != actual:
        ctx.add(
            "INTERNAL_INCONSISTENCY",
            "medium",
            f"Tekst podaje, że {fmt_day(it.ref.start)} to {WEEKDAYS_NOM[mentioned]}, "
            f"ale ten dzień to {WEEKDAYS_NOM[actual]}.",
            it,
        )


def _check_relative_vs_absolute(ctx: _Ctx, it: DateItem) -> None:
    if not (it.relative_expression and it.absolute_given and it.ref and it.relative_ref):
        return
    d = dist(it.ref, it.relative_ref)
    if d > TOL_DAYS:
        ctx.add(
            "INTERNAL_INCONSISTENCY",
            "medium",
            f"Tekst określa »{it.what}« jako »{it.relative_expression}« ({fmt_at(it.relative_ref)}), "
            f"a jednocześnie datuje je {fmt_on(it.ref)}.",
            it,
            d,
        )


def _check_order(ctx: _Ctx, it: DateItem) -> None:
    """Zdarzenie opisane jako przeszłe, ale datowane w samym tekście po jego publikacji."""
    if ctx.t_a is None or it.ref is None or it.tense != "past":
        return
    if it.role not in ("event", "data_as_of"):
        return
    if it.ref.start > ctx.t_a + timedelta(days=TOL_DAYS):
        ctx.add(
            "INTERNAL_INCONSISTENCY",
            "medium",
            f"Tekst z {fmt_day(ctx.t_a)} opisuje »{it.what}« jako przeszłe, "
            f"choć sam datuje je {fmt_on(it.ref)}.",
            it,
            (it.ref.start - ctx.t_a).days,
        )


def _check_mismatch(ctx: _Ctx, it: DateItem) -> None:
    m = it.match
    if m is None or m.ref is None or it.ref is None or it.role == "publication":
        return
    d = dist(it.ref, m.ref)
    if d > TOL_DAYS:
        ctx.add(
            "DATE_MISMATCH",
            "high" if d > HIGH_MISMATCH_DAYS else "medium",
            f"Tekst datuje »{it.what}« {fmt_on(it.ref)}, a źródło »{m.source.label}« "
            f"{fmt_on(m.ref)} (różnica {fmt_days(d)}).",
            it,
            d,
        )


def _check_outdated(ctx: _Ctx, it: DateItem) -> None:
    m = it.match
    if m is None or ctx.t_a is None or m.status == "planned":
        return
    if it.role != "event" or it.tense == "future" or it.recency < RECENCY_THRESHOLD:
        return
    # Bez daty zdarzenia w źródle wystarczy górne ograniczenie: zdarzenie nastąpiło
    # najpóźniej w dniu publikacji źródła.
    if m.ref is not None:
        event_end = m.ref.end
    elif m.status == "occurred" and m.source.published_at:
        event_end = m.source.published_at
    else:
        return
    age = (ctx.t_a - event_end).days
    if age > FRESHNESS_DAYS.get(ctx.category, FRESHNESS_DAYS["other"]):
        ctx.add(
            "OUTDATED_AS_CURRENT",
            "high",
            f"Tekst przedstawia »{it.what}« jako bieżące, choć według źródła »{m.source.label}« "
            f"wydarzyło się {humanize_days(age)} przed publikacją tekstu.",
            it,
            age,
        )


def _check_anachronism(ctx: _Ctx, it: DateItem) -> None:
    m = it.match
    if m is None or m.ref is None or ctx.t_a is None or m.status == "planned":
        return
    if it.tense not in ("past", "present") or it.role == "future":
        return
    if m.ref.start > ctx.t_a + timedelta(days=TOL_DAYS):
        ctx.add(
            "ANACHRONISM",
            "high",
            f"Tekst z {fmt_day(ctx.t_a)} opisuje »{it.what}«, które według źródła "
            f"»{m.source.label}« nastąpiło dopiero {fmt_at(m.ref)}.",
            it,
            (m.ref.start - ctx.t_a).days,
        )


def _check_future_as_past(ctx: _Ctx, it: DateItem) -> None:
    m = it.match
    if m is None or m.status != "planned" or it.tense != "past" or it.role == "future":
        return
    # Jeśli plan miał się zrealizować przed publikacją tekstu, mógł się już ziścić.
    if ctx.t_a and m.ref and ctx.t_a > m.ref.end + timedelta(days=TOL_DAYS):
        return
    plan = f"to plan {fmt_on(m.ref)}" if m.ref else "to dopiero zapowiedź"
    ctx.add(
        "FUTURE_AS_PAST",
        "high",
        f"Tekst podaje »{it.what}« jako fakt dokonany, a według źródła »{m.source.label}« {plan}.",
        it,
    )


def _check_stale(ctx: _Ctx, it: DateItem) -> None:
    if it.role != "data_as_of" or ctx.t_a is None or it.recency < RECENCY_THRESHOLD:
        return
    ref = it.ref or (it.match.ref if it.match else None)
    if ref is None:
        return
    age = (ctx.t_a - ref.end).days
    if age > STALE_DAYS:
        ctx.add(
            "STALE_DATA",
            "medium",
            f"Dane o »{it.what}« pochodzą {fmt_from(ref)}, a tekst z {fmt_day(ctx.t_a)} "
            "przedstawia je jako aktualne.",
            it,
            age,
        )


def _check_before_sources(ctx: _Ctx) -> None:
    if ctx.t_a is None:
        return
    matched = {it.match.source.id: it.match.source for it in ctx.items if it.match}
    published = [s.published_at for s in matched.values() if s.published_at]
    if not published:
        ctx.skip("BEFORE_SOURCES", "żadne dopasowane źródło nie ma daty publikacji")
        return
    earliest = min(published)
    if ctx.t_a < earliest - timedelta(days=TOL_DAYS):
        ctx.add(
            "BEFORE_SOURCES",
            "low",
            f"Tekst z {fmt_day(ctx.t_a)} ukazał się przed najwcześniejszą publikacją "
            f"w dopasowanych źródłach ({fmt_day(earliest)}).",
            delta=(earliest - ctx.t_a).days,
        )


_ITEM_RULES = (
    _check_weekday,
    _check_relative_vs_absolute,
    _check_order,
    _check_mismatch,
    _check_outdated,
    _check_anachronism,
    _check_future_as_past,
    _check_stale,
)


def evaluate(
    items: Sequence[DateItem],
    t_a: date | None,
    category: str = "other",
    sources: Sequence[TruthSource] = (),
    skipped: Sequence[SkippedCheck] = (),
) -> tuple[list[DateIssue], list[SkippedCheck]]:
    """Uruchamia wszystkie reguły. Zwraca ``(issues, skipped_checks)``."""
    ctx = _Ctx(list(items), t_a, category, sources)
    for s in skipped:
        ctx.skip(s.check, s.reason)
    if t_a is None:
        for check in ("OUTDATED_AS_CURRENT", "ANACHRONISM", "STALE_DATA", "BEFORE_SOURCES"):
            ctx.skip(check, "brak daty publikacji tekstu")
    if not sources:
        for check in (
            "DATE_MISMATCH",
            "OUTDATED_AS_CURRENT",
            "ANACHRONISM",
            "FUTURE_AS_PAST",
            "BEFORE_SOURCES",
        ):
            ctx.skip(check, "brak źródeł prawdy")
    for it in ctx.items:
        for rule in _ITEM_RULES:
            rule(ctx, it)
    if sources:
        _check_before_sources(ctx)
    issues = sorted(
        ctx.issues,
        key=lambda i: (_SEVERITY_ORDER[i.severity], i.start if i.start is not None else -1),
    )
    return issues, list(ctx.skipped.values())


# --- normalizacja odpowiedzi LLM --------------------------------------------------------------


def resolve_article_date(article_date: date | None, response: LLMDatesResponse) -> date | None:
    if article_date:
        return article_date
    ref = TimeRef.from_iso(response.article_date_in_text)
    if ref and ref.granularity == "day":
        return ref.start
    for d in response.dates:
        if d.role == "publication":
            ref = TimeRef.from_iso(d.iso_start, d.iso_end, d.granularity)
            if ref and ref.granularity == "day":
                return ref.start
    return None


def build_items(
    text: str,
    sources: Sequence[TruthSource],
    response: LLMDatesResponse,
    t_a: date | None,
) -> tuple[list[DateItem], list[SkippedCheck]]:
    """Odpowiedź LLM → ``DateItem`` z offsetami, przeliczonymi datami względnymi i zweryfikowanym
    dopasowaniem do źródeł (cytat ze źródła musi w nim faktycznie występować)."""
    by_id = {s.id: s for s in sources}
    items: list[DateItem] = []
    skipped: list[SkippedCheck] = []

    for d in response.dates:
        span = locate_quote(text, d.quote)
        if span is None:
            continue
        ref = TimeRef.from_iso(d.iso_start, d.iso_end, d.granularity)
        relative = d.relative_expression.strip()
        relative_ref = None
        if relative:
            if t_a is not None:
                relative_ref = parse_relative(relative, t_a)
                if relative_ref is not None and not d.absolute_given:
                    ref = relative_ref
            else:
                skipped.append(
                    SkippedCheck(
                        check="INTERNAL_INCONSISTENCY",
                        reason=f"nie można przeliczyć »{relative}« bez daty publikacji tekstu",
                    )
                )
                if not d.absolute_given:
                    ref = None

        items.append(
            DateItem(
                id=d.id,
                quote=text[span[0] : span[1]],
                start=span[0],
                end=span[1],
                what=d.what.strip() or d.quote.strip(),
                role=d.role,
                tense=d.tense,
                ref=ref,
                recency=min(max(d.recency_framing, 0.0), 1.0),
                absolute_given=d.absolute_given,
                relative_expression=relative,
                relative_ref=relative_ref,
                weekday_mentioned=d.weekday_mentioned.strip(),
                match=_build_match(d.match, by_id),
            )
        )
    return items, skipped


def _build_match(m: LLMSourceMatch, by_id: dict[str, TruthSource]) -> SourceMatch | None:
    if not m.found:
        return None
    source = by_id.get(m.source_id.strip())
    if source is None:
        return None
    span = locate_quote(source.content, m.source_quote)
    if span is None:
        return None
    ref = TimeRef.from_iso(m.iso_start, m.iso_end, m.granularity)
    relative = m.relative_expression.strip()
    if relative and source.published_at:
        ref = parse_relative(relative, source.published_at) or ref
    return SourceMatch(
        source=source,
        quote=source.content[span[0] : span[1]],
        ref=ref,
        status=m.status,
    )


# --- API --------------------------------------------------------------------------------------


async def analyze_dates(
    text: str,
    sources: Sequence[TruthSource],
    article_date: date | None = None,
    *,
    call: StructuredCall = structured_call,
) -> DatesResult:
    if not text.strip():
        return DatesResult(dates_consistent=True, article_date=article_date)
    response = await call(
        prompts.DATES_SYSTEM,
        prompts.dates_user(text, sources, article_date),
        LLMDatesResponse,
    )
    return build_dates_result(text, sources, response, article_date)


def build_dates_result(
    text: str,
    sources: Sequence[TruthSource],
    response: LLMDatesResponse,
    article_date: date | None = None,
) -> DatesResult:
    """Czysta funkcja: odpowiedź LLM → ``DatesResult``."""
    t_a = resolve_article_date(article_date, response)
    items, skipped = build_items(text, sources, response, t_a)
    issues, skipped_checks = evaluate(items, t_a, response.text_category, sources, skipped)
    return DatesResult(
        dates_consistent=not any(i.severity in ("medium", "high") for i in issues),
        article_date=t_a,
        text_category=response.text_category,
        issues=issues,
        extracted=[_to_extracted(it) for it in items],
        unverified=[
            f"»{it.quote}« ({it.what})"
            for it in items
            if it.match is None and it.role in ("event", "future", "data_as_of")
        ],
        skipped_checks=skipped_checks,
    )


def _to_extracted(it: DateItem) -> ExtractedDate:
    m = it.match
    return ExtractedDate(
        id=it.id,
        quote=it.quote,
        start=it.start,
        end=it.end,
        what=it.what,
        role=it.role,
        tense=it.tense,
        date_from=it.ref.start if it.ref else None,
        date_to=it.ref.end if it.ref else None,
        granularity=it.ref.granularity if it.ref else "unknown",
        recency_framing=round(it.recency, 2),
        source_id=m.source.id if m else None,
        source_quote=m.quote if m else None,
        source_date_from=m.ref.start if m and m.ref else None,
        source_date_to=m.ref.end if m and m.ref else None,
    )
