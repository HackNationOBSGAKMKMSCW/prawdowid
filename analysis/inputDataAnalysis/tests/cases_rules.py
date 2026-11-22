"""Przypadki dla ``temporal.py``: reguły dat, skipped_checks i budowanie wyniku z odpowiedzi LLM."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Sequence
from datetime import date
from typing import Any

from inputDataAnalysis.dates import TimeRef
from inputDataAnalysis.models import DatesResult, LLMDatesResponse, SkippedCheck, TruthSource
from inputDataAnalysis.temporal import (
    DateItem,
    SourceMatch,
    analyze_dates,
    build_dates_result,
    evaluate,
)

from .case_base import Case, d, day, iso

SRC_2019 = TruthSource(id="s1", title="PAP", content="...", published_at=date(2019, 6, 4))
SRC_2024 = TruthSource(id="s5", title="Agencja", content="...", published_at=date(2024, 1, 1))
SRC_NOPUB = TruthSource(id="s6", title="Raport", content="...")
SRC_NOTITLE = TruthSource(id="kgp", content="...", published_at=date(2019, 6, 4))

NO_SOURCES = "brak źródeł prawdy"
NO_DATE = "brak daty publikacji tekstu"
NO_PUB = "żadne dopasowane źródło nie ma daty publikacji"


def it(**kw: Any) -> DateItem:
    defaults: dict[str, Any] = dict(
        id="d1",
        quote="cytat",
        start=0,
        end=5,
        what="zawalenie mostu",
        role="event",
        tense="past",
        ref=None,
    )
    return DateItem(**{**defaults, **kw})


def m(src: TruthSource, ref: TimeRef | None, status: str = "occurred", quote: str = "cytat") -> SourceMatch:
    return SourceMatch(src, quote, ref, status)


Expected = Sequence[tuple[str, str, int | None]]


def _fmt_expect(expect: Expected) -> str:
    if not expect:
        return "brak problemów"
    parts = []
    for code, sev, delta in expect:
        parts.append(f"{code} ({sev}" + (f", Δ={delta} dni)" if delta is not None else ")"))
    return " → ".join(parts)


def _rule(
    cid: str,
    title: str,
    wejscie: str,
    items: Sequence[DateItem],
    *,
    t_a: date | None = None,
    category: str = "other",
    sources: Sequence[TruthSource] = (),
    expect: Expected = (),
    description: str = "",
    contains: str = "",
    known_bug: str = "",
) -> Case:
    def check() -> None:
        issues, _ = evaluate(items, t_a, category, sources)
        assert [(i.code, i.severity, i.delta_days) for i in issues] == list(expect)
        if description:
            assert issues[0].description == description
        if contains:
            assert contains in issues[0].description, issues[0].description

    ctx = [f"t_A={t_a or 'brak'}"]
    if category != "other":
        ctx.append(f"kategoria={category}")
    ocz = _fmt_expect(expect)
    if description:
        ocz += f"; opis: „{description}”"
    elif contains:
        ocz += f"; opis zawiera „{contains}”"
    return Case(cid, "RU", title, f"{wejscie} [{', '.join(ctx)}]", ocz, check, known_bug)


T_OUT = d("2024-03-12")  # data tekstu dla OUTDATED_AS_CURRENT
T_ANA = d("2024-03-01")  # dla ANACHRONISM / FUTURE_AS_PAST / STALE_DATA
T_REL = d("2024-03-20")  # dla dat względnych i kolejności


def _cur(ref: TimeRef | None, src: TruthSource = SRC_2024, **kw: Any) -> DateItem:
    """Zdarzenie przedstawione jako bieżące (tense=present, recency=0.9)."""
    status = kw.pop("status", "occurred")
    return it(**{"tense": "present", "recency": 0.9, "match": m(src, ref, status), **kw})


def _past(src_ref: TimeRef | None, src: TruthSource = SRC_NOPUB, status: str = "occurred", **kw: Any) -> DateItem:
    return it(**{"match": m(src, src_ref, status), **kw})


def _wd(ref: TimeRef, weekday: str, **kw: Any) -> DateItem:
    return it(
        **{"quote": f"{weekday} {ref.start}", "ref": ref, "absolute_given": True, "weekday_mentioned": weekday, **kw}
    )


def _rel(abs_ref: TimeRef, expr: str, rel_ref: TimeRef | None, **kw: Any) -> DateItem:
    return it(
        **{
            "ref": abs_ref,
            "absolute_given": True,
            "relative_expression": expr,
            "relative_ref": rel_ref,
            **kw,
        }
    )


def _stale(ref: TimeRef | None, **kw: Any) -> DateItem:
    return it(**{"role": "data_as_of", "tense": "present", "what": "bezrobocie", "recency": 0.8, "ref": ref, **kw})


SRC_MAR20 = TruthSource(id="s3", title="TVN", content="...", published_at=date(2024, 3, 20))
SRC_MAR15 = TruthSource(id="s4", title="RMF", content="...", published_at=date(2024, 3, 15))
SRC_JAN = TruthSource(id="s7", title="Wcześniejsze", content="...", published_at=date(2024, 1, 1))
SRC_JUN = TruthSource(id="s8", title="Raport", content="...", published_at=date(2024, 6, 1))


RU_CASES = [
    # --- DATE_MISMATCH ---
    _rule(
        "RU01",
        "DATE_MISMATCH: 2 lata różnicy",
        "tekst 2024-03-12, źródło »PAP« 2022-03-12",
        [it(ref=day("2024-03-12"), match=m(SRC_2019, day("2022-03-12")))],
        sources=[SRC_2019],
        expect=[("DATE_MISMATCH", "high", 731)],
        description="Tekst datuje »zawalenie mostu« na 12 marca 2024, a źródło »PAP« na 12 marca 2022 (różnica 731 dni).",
    ),
    _rule(
        "RU02",
        "DATE_MISMATCH: 2 dni → średnia",
        "tekst 2024-03-12, źródło 2024-03-14",
        [it(ref=day("2024-03-12"), match=m(SRC_2019, day("2024-03-14")))],
        sources=[SRC_2019],
        expect=[("DATE_MISMATCH", "medium", 2)],
    ),
    _rule(
        "RU03",
        "tolerancja +1 dzień",
        "tekst 2024-03-12, źródło 2024-03-13",
        [it(ref=day("2024-03-12"), match=m(SRC_2019, day("2024-03-13")))],
        sources=[SRC_2019],
    ),
    _rule(
        "RU04",
        "tolerancja −1 dzień",
        "tekst 2024-03-12, źródło 2024-03-11",
        [it(ref=day("2024-03-12"), match=m(SRC_2019, day("2024-03-11")))],
        sources=[SRC_2019],
    ),
    _rule(
        "RU05",
        "granica 30 dni → nadal średnia",
        "tekst 2024-03-01, źródło 2024-03-31",
        [it(ref=day("2024-03-01"), match=m(SRC_2019, day("2024-03-31")))],
        sources=[SRC_2019],
        expect=[("DATE_MISMATCH", "medium", 30)],
    ),
    _rule(
        "RU06",
        "31 dni → wysoka",
        "tekst 2024-03-01, źródło 2024-04-01",
        [it(ref=day("2024-03-01"), match=m(SRC_2019, day("2024-04-01")))],
        sources=[SRC_2019],
        expect=[("DATE_MISMATCH", "high", 31)],
    ),
    _rule(
        "RU07",
        "„marzec 2024” vs 15.03.2024 → zgodne",
        "tekst 2024-03 (miesiąc), źródło 2024-03-15",
        [it(ref=iso("2024-03"), match=m(SRC_2019, day("2024-03-15")))],
        sources=[SRC_2019],
    ),
    _rule(
        "RU08",
        "miesiąc vs dzień poza nim",
        "tekst 2024-03 (miesiąc), źródło 2024-04-02",
        [it(ref=iso("2024-03"), match=m(SRC_2019, day("2024-04-02")))],
        sources=[SRC_2019],
        expect=[("DATE_MISMATCH", "medium", 2)],
        description="Tekst datuje »zawalenie mostu« na marzec 2024, a źródło »PAP« na 2 kwietnia 2024 (różnica 2 dni).",
    ),
    _rule(
        "RU09",
        "rok vs dzień tuż przed nim (w tolerancji)",
        "tekst 2024 (rok), źródło 2023-12-31",
        [it(ref=iso("2024"), match=m(SRC_2019, day("2023-12-31")))],
        sources=[SRC_2019],
    ),
    _rule(
        "RU10",
        "rok vs rok",
        "tekst 2019 (rok), źródło 2021 (rok)",
        [it(ref=iso("2019"), match=m(SRC_2019, iso("2021")))],
        sources=[SRC_2019],
        expect=[("DATE_MISMATCH", "high", 367)],
        contains="na 2019 r., a źródło »PAP« na 2021 r.",
    ),
    _rule(
        "RU11",
        "rola publication nie jest porównywana",
        "role=publication, tekst 2024-03-12, źródło 2022-03-12",
        [it(role="publication", ref=day("2024-03-12"), match=m(SRC_2019, day("2022-03-12")))],
        sources=[SRC_2019],
    ),
    _rule(
        "RU12",
        "źródło bez daty zdarzenia",
        "tekst 2024-03-12, źródło: brak daty",
        [it(ref=day("2024-03-12"), match=m(SRC_2019, None))],
        sources=[SRC_2019],
    ),
    _rule(
        "RU13",
        "tekst bez daty zdarzenia",
        "tekst: brak daty, źródło 2022-03-12",
        [it(ref=None, match=m(SRC_2019, day("2022-03-12")))],
        sources=[SRC_2019],
    ),
    _rule(
        "RU14",
        "źródło bez tytułu → w opisie id",
        "źródło id=kgp bez tytułu, tekst 2024-03-12, źródło 2022-03-12",
        [it(ref=day("2024-03-12"), match=m(SRC_NOTITLE, day("2022-03-12")))],
        sources=[SRC_NOTITLE],
        expect=[("DATE_MISMATCH", "high", 731)],
        contains="a źródło »kgp«",
    ),
    # --- OUTDATED_AS_CURRENT ---
    _rule(
        "RU15",
        "breaking: 4 dni > 3 dni",
        "bieżące (recency 0.9), źródło 2024-03-08",
        [_cur(day("2024-03-08"))],
        t_a=T_OUT,
        category="breaking",
        sources=[SRC_2024],
        expect=[("OUTDATED_AS_CURRENT", "high", 4)],
        description="Tekst przedstawia »zawalenie mostu« jako bieżące, choć według źródła »Agencja« wydarzyło się 4 dni przed publikacją tekstu.",
    ),
    _rule(
        "RU16",
        "breaking: dokładnie 3 dni → OK",
        "bieżące, źródło 2024-03-09",
        [_cur(day("2024-03-09"))],
        t_a=T_OUT,
        category="breaking",
        sources=[SRC_2024],
    ),
    _rule(
        "RU17",
        "polityczne: 31 dni > 30",
        "bieżące, źródło 2024-02-10",
        [_cur(day("2024-02-10"))],
        t_a=T_OUT,
        category="political_legal",
        sources=[SRC_2024],
        expect=[("OUTDATED_AS_CURRENT", "high", 31)],
    ),
    _rule(
        "RU18",
        "polityczne: dokładnie 30 dni → OK",
        "bieżące, źródło 2024-02-11",
        [_cur(day("2024-02-11"))],
        t_a=T_OUT,
        category="political_legal",
        sources=[SRC_2024],
    ),
    _rule(
        "RU19",
        "gospodarcze: 367 dni > 365",
        "bieżące, źródło 2023-03-11",
        [_cur(day("2023-03-11"))],
        t_a=T_OUT,
        category="economic",
        sources=[SRC_2024],
        expect=[("OUTDATED_AS_CURRENT", "high", 367)],
        contains="1 rok przed publikacją",
    ),
    _rule(
        "RU20",
        "gospodarcze: 193 dni → OK",
        "bieżące, źródło 2023-09-01",
        [_cur(day("2023-09-01"))],
        t_a=T_OUT,
        category="economic",
        sources=[SRC_2024],
    ),
    _rule(
        "RU21",
        "kategoria other: próg 30 dni",
        "bieżące, źródło 2024-02-10",
        [_cur(day("2024-02-10"))],
        t_a=T_OUT,
        sources=[SRC_2024],
        expect=[("OUTDATED_AS_CURRENT", "high", 31)],
    ),
    _rule(
        "RU22",
        "nieznana kategoria → próg jak other",
        "bieżące, źródło 2024-02-10",
        [_cur(day("2024-02-10"))],
        t_a=T_OUT,
        category="sport",
        sources=[SRC_2024],
        expect=[("OUTDATED_AS_CURRENT", "high", 31)],
    ),
    _rule(
        "RU23",
        "recency 0.59 < 0.6 → OK",
        "recency 0.59, źródło 2019-06-03",
        [_cur(day("2019-06-03"), SRC_2019, recency=0.59)],
        t_a=T_OUT,
        category="breaking",
        sources=[SRC_2019],
    ),
    _rule(
        "RU24",
        "recency dokładnie 0.6 → flaga",
        "recency 0.6, źródło 2019-06-03",
        [_cur(day("2019-06-03"), SRC_2019, recency=0.6)],
        t_a=T_OUT,
        category="breaking",
        sources=[SRC_2019],
        expect=[("OUTDATED_AS_CURRENT", "high", 1744)],
        description="Tekst przedstawia »zawalenie mostu« jako bieżące, choć według źródła »PAP« wydarzyło się 4 lata przed publikacją tekstu.",
    ),
    _rule(
        "RU25",
        "zdarzenie zapowiadane (tense=future)",
        "tense=future, źródło 2019-06-03",
        [_cur(day("2019-06-03"), SRC_2019, tense="future")],
        t_a=T_OUT,
        category="breaking",
        sources=[SRC_2019],
    ),
    _rule(
        "RU26",
        "rola reference",
        "role=reference, źródło 2019-06-03",
        [_cur(day("2019-06-03"), SRC_2019, role="reference")],
        t_a=T_OUT,
        category="breaking",
        sources=[SRC_2019],
    ),
    _rule(
        "RU27",
        "źródło: plan, nie zdarzenie",
        "status=planned, tense=present, źródło 2019-06-03",
        [_cur(day("2019-06-03"), SRC_2019, status="planned")],
        t_a=T_OUT,
        category="breaking",
        sources=[SRC_2019],
    ),
    _rule(
        "RU28",
        "brak daty zdarzenia → data publikacji źródła",
        "źródło bez daty zdarzenia, status=occurred, published_at 2019-06-04",
        [_cur(None, SRC_2019)],
        t_a=T_OUT,
        category="breaking",
        sources=[SRC_2019],
        expect=[("OUTDATED_AS_CURRENT", "high", 1743)],
    ),
    _rule(
        "RU29",
        "brak daty zdarzenia i status unknown",
        "źródło bez daty zdarzenia, status=unknown",
        [_cur(None, SRC_2019, status="unknown")],
        t_a=T_OUT,
        category="breaking",
        sources=[SRC_2019],
    ),
    _rule(
        "RU30",
        "data miesięczna: liczy się koniec miesiąca",
        "bieżące, źródło 2024-02 (miesiąc)",
        [_cur(iso("2024-02"))],
        t_a=T_OUT,
        category="breaking",
        sources=[SRC_2024],
        expect=[("OUTDATED_AS_CURRENT", "high", 12)],
        contains="12 dni przed publikacją",
    ),
    _rule(
        "RU31",
        "zdarzenie po dacie tekstu ≠ nieaktualne",
        "bieżące, źródło 2024-03-12 (ten sam dzień)",
        [_cur(day("2024-03-12"))],
        t_a=T_OUT,
        category="breaking",
        sources=[SRC_2024],
    ),
    # --- ANACHRONISM ---
    _rule(
        "RU32",
        "ANACHRONISM: zdarzenie 90 dni po tekście",
        "przeszłe, źródło »Raport« 2024-05-30",
        [_past(day("2024-05-30"))],
        t_a=T_ANA,
        sources=[SRC_NOPUB],
        expect=[("ANACHRONISM", "high", 90)],
        description="Tekst z 1 marca 2024 opisuje »zawalenie mostu«, które według źródła »Raport« nastąpiło dopiero 30 maja 2024.",
    ),
    _rule(
        "RU33",
        "ANACHRONISM: +1 dzień w tolerancji",
        "przeszłe, źródło 2024-03-02",
        [_past(day("2024-03-02"))],
        t_a=T_ANA,
        sources=[SRC_NOPUB],
    ),
    _rule(
        "RU34",
        "ANACHRONISM: +2 dni",
        "przeszłe, źródło 2024-03-03",
        [_past(day("2024-03-03"))],
        t_a=T_ANA,
        sources=[SRC_NOPUB],
        expect=[("ANACHRONISM", "high", 2)],
    ),
    _rule(
        "RU35",
        "ANACHRONISM dla czasu teraźniejszego",
        "tense=present, źródło 2024-05-30",
        [_past(day("2024-05-30"), tense="present")],
        t_a=T_ANA,
        sources=[SRC_NOPUB],
        expect=[("ANACHRONISM", "high", 90)],
    ),
    _rule(
        "RU36",
        "zapowiedź (tense=future) to nie anachronizm",
        "tense=future, źródło 2024-05-30",
        [_past(day("2024-05-30"), tense="future")],
        t_a=T_ANA,
        sources=[SRC_NOPUB],
    ),
    _rule(
        "RU37",
        "rola future to nie anachronizm",
        "role=future, tense=past, źródło 2024-05-30",
        [_past(day("2024-05-30"), role="future")],
        t_a=T_ANA,
        sources=[SRC_NOPUB],
    ),
    _rule(
        "RU38",
        "status unknown też podlega regule",
        "status=unknown, źródło 2024-05-30",
        [_past(day("2024-05-30"), status="unknown")],
        t_a=T_ANA,
        sources=[SRC_NOPUB],
        expect=[("ANACHRONISM", "high", 90)],
    ),
    _rule(
        "RU39",
        "źródło z datą miesięczną",
        "przeszłe, źródło 2024-04 (miesiąc)",
        [_past(iso("2024-04"))],
        t_a=T_ANA,
        sources=[SRC_NOPUB],
        expect=[("ANACHRONISM", "high", 31)],
        contains="nastąpiło dopiero w kwietniu 2024.",
    ),
    _rule(
        "RU40",
        "DATE_MISMATCH + ANACHRONISM naraz",
        "tekst 2024-02-10, źródło 2024-05-30",
        [_past(day("2024-05-30"), ref=day("2024-02-10"))],
        t_a=T_ANA,
        sources=[SRC_NOPUB],
        expect=[("DATE_MISMATCH", "high", 110), ("ANACHRONISM", "high", 90)],
    ),
    _rule(
        "RU41",
        "ANACHRONISM + BEFORE_SOURCES",
        "przeszłe, źródło 2024-05-30 opublikowane 2024-06-01",
        [_past(day("2024-05-30"), SRC_JUN)],
        t_a=T_ANA,
        sources=[SRC_JUN],
        expect=[("ANACHRONISM", "high", 90), ("BEFORE_SOURCES", "low", 92)],
    ),
    # --- FUTURE_AS_PAST ---
    _rule(
        "RU42",
        "FUTURE_AS_PAST: plan na czerwiec 2025",
        "przeszłe, źródło: plan 2025-06",
        [_past(iso("2025-06"), status="planned")],
        t_a=T_ANA,
        sources=[SRC_NOPUB],
        expect=[("FUTURE_AS_PAST", "high", None)],
        description="Tekst podaje »zawalenie mostu« jako fakt dokonany, a według źródła »Raport« to plan na czerwiec 2025.",
    ),
    _rule(
        "RU43",
        "FUTURE_AS_PAST: plan bez daty",
        "przeszłe, źródło: plan bez daty",
        [_past(None, status="planned")],
        t_a=T_ANA,
        sources=[SRC_NOPUB],
        expect=[("FUTURE_AS_PAST", "high", None)],
        contains="to dopiero zapowiedź.",
    ),
    _rule(
        "RU44",
        "plan z przeszłości mógł się już ziścić",
        "przeszłe, źródło: plan 2023-06",
        [_past(iso("2023-06"), status="planned")],
        t_a=T_ANA,
        sources=[SRC_NOPUB],
    ),
    _rule(
        "RU45",
        "plan kończy się dzień przed tekstem (tolerancja)",
        "przeszłe, źródło: plan 2024-02-29",
        [_past(day("2024-02-29"), status="planned")],
        t_a=T_ANA,
        sources=[SRC_NOPUB],
        expect=[("FUTURE_AS_PAST", "high", None)],
    ),
    _rule(
        "RU46",
        "plan kończy się 2 dni przed tekstem",
        "przeszłe, źródło: plan 2024-02-28",
        [_past(day("2024-02-28"), status="planned")],
        t_a=T_ANA,
        sources=[SRC_NOPUB],
    ),
    _rule(
        "RU47",
        "tekst w czasie teraźniejszym",
        "tense=present, źródło: plan 2025-06",
        [_past(iso("2025-06"), status="planned", tense="present")],
        t_a=T_ANA,
        sources=[SRC_NOPUB],
    ),
    _rule(
        "RU48",
        "tekst sam podaje to jako zapowiedź",
        "role=future, źródło: plan 2025-06",
        [_past(iso("2025-06"), status="planned", role="future")],
        t_a=T_ANA,
        sources=[SRC_NOPUB],
    ),
    _rule(
        "RU49",
        "FUTURE_AS_PAST bez daty tekstu",
        "przeszłe, źródło: plan 2025-06",
        [_past(iso("2025-06"), status="planned")],
        t_a=None,
        sources=[SRC_NOPUB],
        expect=[("FUTURE_AS_PAST", "high", None)],
    ),
    _rule(
        "RU50",
        "plan w przyszłości: FUTURE_AS_PAST, nie ANACHRONISM",
        "przeszłe, źródło: plan 2024-05-30",
        [_past(day("2024-05-30"), status="planned")],
        t_a=T_ANA,
        sources=[SRC_NOPUB],
        expect=[("FUTURE_AS_PAST", "high", None)],
    ),
    _rule(
        "RU51",
        "zdarzenie dokonane w przeszłości → OK",
        "przeszłe, źródło: occurred 2023-06",
        [_past(iso("2023-06"))],
        t_a=T_ANA,
        sources=[SRC_NOPUB],
    ),
    # --- INTERNAL_INCONSISTENCY: dzień tygodnia ---
    _rule(
        "RU52",
        "„środa 12 marca 2024” (wtorek)",
        "2024-03-12 + „środa”",
        [_wd(day("2024-03-12"), "środa", quote="w środę 12 marca 2024")],
        expect=[("INTERNAL_INCONSISTENCY", "medium", None)],
        description="Tekst podaje, że 12 marca 2024 to środa, ale ten dzień to wtorek.",
    ),
    _rule("RU53", "poprawny dzień tygodnia", "2024-03-12 + „wtorek”", [_wd(day("2024-03-12"), "wtorek")]),
    _rule("RU54", "odmiana „we wtorek”", "2024-03-12 + „we wtorek”", [_wd(day("2024-03-12"), "we wtorek")]),
    _rule(
        "RU55",
        "odmiana „w czwartek” (błędna)",
        "2024-03-12 + „w czwartek”",
        [_wd(day("2024-03-12"), "w czwartek")],
        expect=[("INTERNAL_INCONSISTENCY", "medium", None)],
    ),
    _rule(
        "RU56",
        "data nie podana wprost",
        "2024-03-12 + „środa”, absolute_given=False",
        [_wd(day("2024-03-12"), "środa", absolute_given=False)],
    ),
    _rule("RU57", "data miesięczna z dniem tygodnia", "2024-03 + „środa”", [_wd(iso("2024-03"), "środa")]),
    _rule("RU58", "nierozpoznany dzień tygodnia", "2024-03-12 + „jutro”", [_wd(day("2024-03-12"), "jutro")]),
    _rule(
        "RU59",
        "29 lutego 2024 to czwartek",
        "2024-02-29 + „piątek”",
        [_wd(day("2024-02-29"), "piątek")],
        expect=[("INTERNAL_INCONSISTENCY", "medium", None)],
        contains="ale ten dzień to czwartek.",
    ),
    _rule("RU60", "1 stycznia 2025 to środa", "2025-01-01 + „środa”", [_wd(day("2025-01-01"), "środa")]),
    _rule(
        "RU61",
        "Boże Narodzenie 2024 to środa",
        "2024-12-25 + „niedziela”",
        [_wd(day("2024-12-25"), "niedziela")],
        expect=[("INTERNAL_INCONSISTENCY", "medium", None)],
        contains="ale ten dzień to środa.",
    ),
    _rule("RU62", "skrót „Śr.”", "2024-03-13 + „Śr.”", [_wd(day("2024-03-13"), "Śr.")]),
    _rule(
        "RU63",
        "dzień tygodnia bez daty",
        "brak daty + „środa”",
        [it(absolute_given=True, weekday_mentioned="środa", ref=None)],
    ),
    # --- INTERNAL_INCONSISTENCY: względna vs bezwzględna ---
    _rule(
        "RU64",
        "„wczoraj” vs 2 marca",
        "abs 2024-03-02, „wczoraj” = 2024-03-19",
        [_rel(day("2024-03-02"), "wczoraj", day("2024-03-19"))],
        t_a=T_REL,
        expect=[("INTERNAL_INCONSISTENCY", "medium", 17)],
        description="Tekst określa »zawalenie mostu« jako »wczoraj« (19 marca 2024), a jednocześnie datuje je na 2 marca 2024.",
    ),
    _rule(
        "RU65",
        "„wczoraj” zgodne",
        "abs 2024-03-19, „wczoraj” = 2024-03-19",
        [_rel(day("2024-03-19"), "wczoraj", day("2024-03-19"))],
        t_a=T_REL,
    ),
    _rule(
        "RU66",
        "„wczoraj” ±1 dzień",
        "abs 2024-03-18, „wczoraj” = 2024-03-19",
        [_rel(day("2024-03-18"), "wczoraj", day("2024-03-19"))],
        t_a=T_REL,
    ),
    _rule(
        "RU67",
        "„wczoraj” o 2 dni obok",
        "abs 2024-03-17, „wczoraj” = 2024-03-19",
        [_rel(day("2024-03-17"), "wczoraj", day("2024-03-19"))],
        t_a=T_REL,
        expect=[("INTERNAL_INCONSISTENCY", "medium", 2)],
    ),
    _rule(
        "RU68",
        "„w tym miesiącu” zawiera dzień",
        "abs 2024-03-05, względne = 2024-03 (miesiąc)",
        [_rel(day("2024-03-05"), "w tym miesiącu", iso("2024-03"))],
        t_a=T_REL,
    ),
    _rule(
        "RU69",
        "„w zeszłym tygodniu” poza tygodniem",
        "abs 2024-03-05, względne = 2024-03-10…16 (week)",
        [_rel(day("2024-03-05"), "w zeszłym tygodniu", iso("2024-03-10", "2024-03-16", "week"))],
        t_a=T_REL,
        expect=[("INTERNAL_INCONSISTENCY", "medium", 5)],
        contains="jako »w zeszłym tygodniu« (w okresie 10–16 marca 2024)",
    ),
    _rule(
        "RU70",
        "nieprzeliczalne wyrażenie względne",
        "abs 2024-03-02, „niedawno” = brak",
        [_rel(day("2024-03-02"), "niedawno", None)],
        t_a=T_REL,
    ),
    _rule(
        "RU71",
        "brak daty bezwzględnej",
        "„wczoraj”, absolute_given=False",
        [_rel(day("2024-03-02"), "wczoraj", day("2024-03-19"), absolute_given=False)],
        t_a=T_REL,
    ),
    # --- INTERNAL_INCONSISTENCY: kolejność ---
    _rule(
        "RU72",
        "przeszłe zdarzenie po dacie tekstu",
        "przeszłe, tekst datuje 2024-05-01",
        [it(ref=day("2024-05-01"))],
        t_a=T_REL,
        expect=[("INTERNAL_INCONSISTENCY", "medium", 42)],
        description="Tekst z 20 marca 2024 opisuje »zawalenie mostu« jako przeszłe, choć sam datuje je na 1 maja 2024.",
    ),
    _rule("RU73", "+1 dzień w tolerancji", "przeszłe, 2024-03-21", [it(ref=day("2024-03-21"))], t_a=T_REL),
    _rule(
        "RU74",
        "+2 dni",
        "przeszłe, 2024-03-22",
        [it(ref=day("2024-03-22"))],
        t_a=T_REL,
        expect=[("INTERNAL_INCONSISTENCY", "medium", 2)],
    ),
    _rule("RU75", "zapowiedź w przyszłości", "tense=future, 2024-05-01", [it(ref=day("2024-05-01"), tense="future")], t_a=T_REL),
    _rule("RU76", "czas teraźniejszy", "tense=present, 2024-05-01", [it(ref=day("2024-05-01"), tense="present")], t_a=T_REL),
    _rule("RU77", "rola reference", "role=reference, 2024-05-01", [it(ref=day("2024-05-01"), role="reference")], t_a=T_REL),
    _rule(
        "RU78",
        "dane „na dzień” po dacie tekstu",
        "role=data_as_of, przeszłe, 2024-05-01",
        [it(ref=day("2024-05-01"), role="data_as_of")],
        t_a=T_REL,
        expect=[("INTERNAL_INCONSISTENCY", "medium", 42)],
    ),
    _rule("RU79", "bez daty tekstu nie ma kolejności", "przeszłe, 2024-05-01", [it(ref=day("2024-05-01"))]),
    _rule(
        "RU80",
        "miesiąc po dacie tekstu",
        "przeszłe, 2024-04 (miesiąc)",
        [it(ref=iso("2024-04"))],
        t_a=T_REL,
        expect=[("INTERNAL_INCONSISTENCY", "medium", 12)],
    ),
    # --- STALE_DATA ---
    _rule(
        "RU81",
        "dane z 2015 jako aktualne",
        "data_as_of 2015 (rok), recency 0.8",
        [_stale(iso("2015"))],
        t_a=T_ANA,
        expect=[("STALE_DATA", "medium", 2983)],
        description="Dane o »bezrobocie« pochodzą z 2015 r., a tekst z 1 marca 2024 przedstawia je jako aktualne.",
    ),
    _rule(
        "RU82",
        "dane z lutego 2023 (367 dni)",
        "data_as_of 2023-02 (miesiąc)",
        [_stale(iso("2023-02"))],
        t_a=T_ANA,
        expect=[("STALE_DATA", "medium", 367)],
        contains="pochodzą z lutego 2023",
    ),
    _rule("RU83", "dane z marca 2023 (336 dni) → OK", "data_as_of 2023-03 (miesiąc)", [_stale(iso("2023-03"))], t_a=T_ANA),
    _rule(
        "RU84",
        "granica: 366 dni",
        "data_as_of 2023-03-01",
        [_stale(day("2023-03-01"))],
        t_a=T_ANA,
        expect=[("STALE_DATA", "medium", 366)],
        contains="pochodzą z 1 marca 2023",
    ),
    _rule("RU85", "granica: 365 dni → OK", "data_as_of 2023-03-02", [_stale(day("2023-03-02"))], t_a=T_ANA),
    _rule("RU86", "brak ramowania „obecnie”", "data_as_of 2015, recency 0.5", [_stale(iso("2015"), recency=0.5)], t_a=T_ANA),
    _rule("RU87", "rola event to nie dane", "role=event, 2015, recency 0.8", [_stale(iso("2015"), role="event")], t_a=T_ANA),
    _rule(
        "RU88",
        "data danych ze źródła",
        "data_as_of bez daty w tekście, źródło 2015 (rok)",
        [_stale(None, match=m(SRC_NOPUB, iso("2015")))],
        t_a=T_ANA,
        sources=[SRC_NOPUB],
        expect=[("STALE_DATA", "medium", 2983)],
    ),
    _rule("RU89", "brak daty tekstu", "data_as_of 2015", [_stale(iso("2015"))]),
    _rule(
        "RU90",
        "dane kwartalne",
        "data_as_of 2022-Q4",
        [_stale(iso("2022-Q4"))],
        t_a=T_ANA,
        expect=[("STALE_DATA", "medium", 426)],
        contains="pochodzą z 4. kwartału 2022 r.",
    ),
    # --- BEFORE_SOURCES ---
    _rule(
        "RU91",
        "tekst 9 dni przed źródłem",
        "źródło »TVN« opublikowane 2024-03-20",
        [_past(day("2024-03-10"), SRC_MAR20)],
        t_a=d("2024-03-11"),
        sources=[SRC_MAR20],
        expect=[("BEFORE_SOURCES", "low", 9)],
        description="Tekst z 11 marca 2024 ukazał się przed najwcześniejszą publikacją w dopasowanych źródłach (20 marca 2024).",
    ),
    _rule(
        "RU92",
        "dzień przed źródłem (tolerancja)",
        "źródło opublikowane 2024-03-20",
        [_past(day("2024-03-10"), SRC_MAR20)],
        t_a=d("2024-03-19"),
        sources=[SRC_MAR20],
    ),
    _rule(
        "RU93",
        "2 dni przed źródłem",
        "źródło opublikowane 2024-03-20",
        [_past(day("2024-03-10"), SRC_MAR20)],
        t_a=d("2024-03-18"),
        sources=[SRC_MAR20],
        expect=[("BEFORE_SOURCES", "low", 2)],
    ),
    _rule(
        "RU94",
        "liczy się najwcześniejsze dopasowane źródło",
        "źródła opublikowane 2024-03-20 i 2024-03-15",
        [_past(day("2024-03-09"), SRC_MAR20), _past(day("2024-03-09"), SRC_MAR15, id="d2")],
        t_a=d("2024-03-10"),
        sources=[SRC_MAR20, SRC_MAR15],
        expect=[("BEFORE_SOURCES", "low", 5)],
    ),
    _rule(
        "RU95",
        "niedopasowane źródło jest pomijane",
        "dopasowane 2024-03-20, niedopasowane 2024-01-01",
        [_past(day("2024-03-10"), SRC_MAR20)],
        t_a=d("2024-03-11"),
        sources=[SRC_MAR20, SRC_JAN],
        expect=[("BEFORE_SOURCES", "low", 9)],
    ),
    # --- sortowanie i kombinacje ---
    _rule(
        "RU96",
        "sortowanie: waga, potem pozycja",
        "3 daty: weekday@50 (medium), mismatch@10 (high), mismatch@30 (medium)",
        [
            _wd(day("2024-03-12"), "środa", id="a", start=50, end=60),
            it(id="b", start=10, end=15, ref=day("2024-03-12"), match=m(SRC_2019, day("2022-03-12"))),
            it(id="c", start=30, end=35, ref=day("2024-03-12"), match=m(SRC_2019, day("2024-03-14"))),
        ],
        sources=[SRC_2019],
        expect=[
            ("DATE_MISMATCH", "high", 731),
            ("DATE_MISMATCH", "medium", 2),
            ("INTERNAL_INCONSISTENCY", "medium", None),
        ],
    ),
    _rule(
        "RU97",
        "jedna data, dwa problemy",
        "„środa 12 marca 2024”, źródło 2022-03-12",
        [_wd(day("2024-03-12"), "środa", match=m(SRC_2019, day("2022-03-12")))],
        sources=[SRC_2019],
        expect=[("DATE_MISMATCH", "high", 731), ("INTERNAL_INCONSISTENCY", "medium", None)],
    ),
    _rule("RU98", "brak dat w tekście", "0 dat", [], t_a=T_ANA, sources=[SRC_2019]),
]


def _ru_fields() -> None:
    item = it(
        quote="12 marca 2024",
        start=7,
        end=20,
        ref=day("2024-03-12"),
        match=m(SRC_2019, day("2022-03-12"), quote="12 marca 2022"),
    )
    issues, _ = evaluate([item], None, sources=[SRC_2019])
    i = issues[0]
    assert (i.input_quote, i.start, i.end, i.source_id, i.source_quote) == (
        "12 marca 2024",
        7,
        20,
        "s1",
        "12 marca 2022",
    )


RU_CASES.append(
    Case(
        "RU99",
        "RU",
        "issue niesie cytaty, offsety i id źródła",
        "DATE_MISMATCH dla cytatu »12 marca 2024« @7–20, źródło s1 »12 marca 2022«",
        "input_quote, start=7, end=20, source_id=s1, source_quote wypełnione",
        _ru_fields,
    )
)


# --- SK: skipped_checks -----------------------------------------------------------------------


def _sk(
    cid: str,
    title: str,
    wejscie: str,
    items: Sequence[DateItem],
    t_a: date | None,
    sources: Sequence[TruthSource],
    exp: set[tuple[str, str]],
    pre: Sequence[SkippedCheck] = (),
) -> Case:
    def check() -> None:
        _, skipped = evaluate(items, t_a, "other", sources, pre)
        got = [(s.check, s.reason) for s in skipped]
        assert len(got) == len(set(got)), "duplikaty w skipped_checks"
        assert set(got) == exp

    ocz = "[]" if not exp else "; ".join(f"{c}: {r}" for c, r in sorted(exp))
    return Case(cid, "SK", title, wejscie, f"{len(exp)} wpisów: {ocz}", check)


_ALL_NO_SRC = {
    (c, NO_SOURCES)
    for c in ("DATE_MISMATCH", "OUTDATED_AS_CURRENT", "ANACHRONISM", "FUTURE_AS_PAST", "BEFORE_SOURCES")
}
_ALL_NO_DATE = {(c, NO_DATE) for c in ("OUTDATED_AS_CURRENT", "ANACHRONISM", "STALE_DATA", "BEFORE_SOURCES")}

SK_CASES = [
    _sk("SK01", "brak daty i brak źródeł", "t_A=brak, sources=[]", [it()], None, [], _ALL_NO_SRC | _ALL_NO_DATE),
    _sk("SK02", "jest data, brak źródeł", "t_A=2024-03-01, sources=[]", [it()], T_ANA, [], _ALL_NO_SRC),
    _sk("SK03", "są źródła, brak daty", "t_A=brak, sources=[PAP]", [it()], None, [SRC_2019], _ALL_NO_DATE),
    _sk(
        "SK04",
        "komplet danych",
        "t_A=2024-03-12, dopasowane źródło z published_at",
        [_cur(day("2024-03-11"))],
        T_OUT,
        [SRC_2024],
        set(),
    ),
    _sk(
        "SK05",
        "dopasowane źródło bez daty publikacji",
        "t_A=2024-03-01, źródło »Raport« bez published_at",
        [_past(day("2024-02-01"))],
        T_ANA,
        [SRC_NOPUB],
        {("BEFORE_SOURCES", NO_PUB)},
    ),
    _sk(
        "SK06",
        "źródła są, ale nic nie dopasowano",
        "t_A=2024-03-01, 0 dopasowań",
        [it(ref=day("2024-02-01"))],
        T_ANA,
        [SRC_2019],
        {("BEFORE_SOURCES", NO_PUB)},
    ),
    _sk(
        "SK07",
        "zduplikowane wpisy z wejścia są scalane",
        "2× ten sam SkippedCheck przekazany z build_items",
        [],
        T_ANA,
        [SRC_2019],
        {("INTERNAL_INCONSISTENCY", "x"), ("BEFORE_SOURCES", NO_PUB)},
        pre=[SkippedCheck(check="INTERNAL_INCONSISTENCY", reason="x")] * 2,
    ),
]


# --- BD: build_dates_result -------------------------------------------------------------------


def _match(**kw: Any) -> dict[str, Any]:
    base = dict(
        found=False,
        source_id="",
        source_quote="",
        iso_start="",
        iso_end="",
        granularity="unknown",
        relative_expression="",
        status="unknown",
    )
    return {**base, **kw}


def _llm(**kw: Any) -> dict[str, Any]:
    base: dict[str, Any] = dict(
        id="d1",
        quote="",
        what="",
        role="event",
        tense="past",
        iso_start="",
        iso_end="",
        granularity="unknown",
        absolute_given=False,
        relative_expression="",
        weekday_mentioned="",
        recency_framing=0.0,
        match=_match(),
    )
    return {**base, **kw}


def _resp(*dates: dict[str, Any], in_text: str = "", category: str = "other") -> LLMDatesResponse:
    return LLMDatesResponse.model_validate(
        dict(article_date_in_text=in_text, text_category=category, recency_framing=0.0, dates=list(dates))
    )


BD_TEXT = "Wczoraj, 2 marca 2024 r., zawalił się most. Właśnie zawalił się most w Toruniu. Dane z 2015 r."
BD_SRC = TruthSource(
    id="pap",
    title="PAP",
    published_at=date(2019, 6, 4),
    content="Wczoraj wieczorem zawaliło się przęsło mostu na Wiśle w Toruniu.",
)


def _bd(
    cid: str,
    title: str,
    wejscie: str,
    oczekiwane: str,
    response: LLMDatesResponse,
    verify: Callable[[DatesResult], None],
    *,
    text: str = BD_TEXT,
    sources: Sequence[TruthSource] = (BD_SRC,),
    article_date: date | None = None,
) -> Case:
    def check() -> None:
        verify(build_dates_result(text, list(sources), response, article_date))

    return Case(cid, "BD", title, wejscie, oczekiwane, check)


def _skipped(r: DatesResult) -> set[tuple[str, str]]:
    return {(s.check, s.reason) for s in r.skipped_checks}


def _bd_empty_text() -> None:
    async def never(*_: Any) -> Any:
        raise AssertionError("LLM nie powinien być wywołany dla pustego tekstu")

    r = asyncio.run(analyze_dates("   ", [BD_SRC], date(2024, 3, 1), call=never))
    assert r.dates_consistent is True and r.extracted == [] and r.article_date == date(2024, 3, 1)


def _assert(cond: bool, msg: str = "") -> None:
    assert cond, msg


BD_CASES = [
    _bd(
        "BD01",
        "parametr article_date ma pierwszeństwo",
        "article_date=2024-03-12, LLM: article_date_in_text=2020-01-01",
        "article_date = 2024-03-12",
        _resp(in_text="2020-01-01"),
        lambda r: _assert(r.article_date == d("2024-03-12")),
        article_date=d("2024-03-12"),
    ),
    _bd(
        "BD02",
        "data publikacji z treści tekstu",
        "article_date=None, LLM: article_date_in_text=2024-03-12",
        "article_date = 2024-03-12",
        _resp(in_text="2024-03-12"),
        lambda r: _assert(r.article_date == d("2024-03-12")),
    ),
    _bd(
        "BD03",
        "data publikacji tylko z miesiącem jest ignorowana",
        "article_date_in_text=2024-03",
        "article_date = None",
        _resp(in_text="2024-03"),
        lambda r: _assert(r.article_date is None),
    ),
    _bd(
        "BD04",
        "data publikacji z elementu role=publication",
        "element role=publication, iso 2024-03-15",
        "article_date = 2024-03-15",
        _resp(_llm(quote="Dane z 2015 r.", role="publication", iso_start="2024-03-15", iso_end="2024-03-15", granularity="day")),
        lambda r: _assert(r.article_date == d("2024-03-15")),
    ),
    _bd(
        "BD05",
        "publication z samym rokiem nie wystarcza",
        "element role=publication, iso 2024 (rok)",
        "article_date = None",
        _resp(_llm(quote="Dane z 2015 r.", role="publication", iso_start="2024-01-01", iso_end="2024-12-31", granularity="year")),
        lambda r: _assert(r.article_date is None),
    ),
    _bd(
        "BD06",
        "brak daty tekstu → reguły pominięte",
        "brak article_date i brak daty w tekście",
        "article_date=None; skipped zawiera OUTDATED_AS_CURRENT: brak daty publikacji tekstu",
        _resp(),
        lambda r: _assert(r.article_date is None and ("OUTDATED_AS_CURRENT", NO_DATE) in _skipped(r)),
    ),
    _bd(
        "BD07",
        "„wczoraj” przeliczone względem daty tekstu",
        "„Wczoraj” bez daty wprost, article_date=2024-03-20",
        "extracted[0].date_from = date_to = 2024-03-19",
        _resp(_llm(quote="Wczoraj", relative_expression="wczoraj", iso_start="2030-01-01")),
        lambda r: _assert(r.extracted[0].date_from == d("2024-03-19") == r.extracted[0].date_to),
        article_date=d("2024-03-20"),
    ),
    _bd(
        "BD08",
        "„wczoraj” bez daty tekstu",
        "„Wczoraj” bez daty wprost, article_date=None",
        "date_from=None; skipped: INTERNAL_INCONSISTENCY „nie można przeliczyć »wczoraj« bez daty publikacji tekstu”",
        _resp(_llm(quote="Wczoraj", relative_expression="wczoraj", iso_start="2024-03-19")),
        lambda r: _assert(
            r.extracted[0].date_from is None
            and ("INTERNAL_INCONSISTENCY", "nie można przeliczyć »wczoraj« bez daty publikacji tekstu")
            in _skipped(r)
        ),
    ),
    _bd(
        "BD09",
        "„Wczoraj, 2 marca” w tekście z 20 marca",
        "absolute 2024-03-02 + „wczoraj”, article_date=2024-03-20",
        "date_from=2024-03-02; INTERNAL_INCONSISTENCY (medium, Δ=17); dates_consistent=False",
        _resp(
            _llm(
                quote="Wczoraj, 2 marca 2024 r.",
                iso_start="2024-03-02",
                iso_end="2024-03-02",
                granularity="day",
                absolute_given=True,
                relative_expression="wczoraj",
            )
        ),
        lambda r: _assert(
            r.extracted[0].date_from == d("2024-03-02")
            and [(i.code, i.delta_days) for i in r.issues] == [("INTERNAL_INCONSISTENCY", 17)]
            and r.dates_consistent is False
        ),
        article_date=d("2024-03-20"),
    ),
    _bd(
        "BD10",
        "data względna w źródle liczona od jego publikacji",
        "źródło „Wczoraj wieczorem…” opublikowane 2019-06-04, LLM podał 2019-06-10",
        "source_date_from = 2019-06-03 (nadpisuje LLM)",
        _resp(
            _llm(
                quote="Właśnie zawalił się most w Toruniu",
                match=_match(
                    found=True,
                    source_id="pap",
                    source_quote="Wczoraj wieczorem zawaliło się przęsło mostu",
                    iso_start="2019-06-10",
                    iso_end="2019-06-10",
                    granularity="day",
                    relative_expression="Wczoraj",
                    status="occurred",
                ),
            )
        ),
        lambda r: _assert(r.extracted[0].source_date_from == d("2019-06-03")),
    ),
    _bd(
        "BD11",
        "nieznane id źródła",
        "match.source_id = „nie-ma”",
        "brak dopasowania; data w unverified",
        _resp(
            _llm(
                quote="Właśnie zawalił się most",
                what="zawalenie",
                match=_match(found=True, source_id="nie-ma", source_quote="Wczoraj wieczorem"),
            )
        ),
        lambda r: _assert(r.extracted[0].source_id is None and r.unverified == ["»Właśnie zawalił się most« (zawalenie)"]),
    ),
    _bd(
        "BD12",
        "found=false",
        "match.found = false",
        "unverified = [»Właśnie zawalił się most« (zawalenie)]",
        _resp(_llm(quote="Właśnie zawalił się most", what="zawalenie")),
        lambda r: _assert(r.unverified == ["»Właśnie zawalił się most« (zawalenie)"]),
    ),
    _bd(
        "BD13",
        "rola reference nie trafia do unverified",
        "role=reference bez dopasowania",
        "unverified = []",
        _resp(_llm(quote="Dane z 2015 r.", role="reference")),
        lambda r: _assert(r.unverified == []),
    ),
    _bd(
        "BD14",
        "rola publication nie trafia do unverified",
        "role=publication bez dopasowania",
        "unverified = []",
        _resp(_llm(quote="Dane z 2015 r.", role="publication")),
        lambda r: _assert(r.unverified == []),
    ),
    _bd(
        "BD15",
        "rola future i data_as_of trafiają do unverified",
        "role=future i role=data_as_of bez dopasowania",
        "unverified ma 2 wpisy",
        _resp(
            _llm(quote="zawalił się most.", role="future", what="a"),
            _llm(id="d2", quote="Dane z 2015 r.", role="data_as_of", what="b"),
        ),
        lambda r: _assert(len(r.unverified) == 2),
    ),
    _bd(
        "BD16",
        "recency_framing przycinane do [0, 1]",
        "recency 1.5 i −0.3",
        "recency_framing = 1.0 i 0.0",
        _resp(
            _llm(quote="Wczoraj", recency_framing=1.5),
            _llm(id="d2", quote="Dane z 2015 r.", recency_framing=-0.3),
        ),
        lambda r: _assert([e.recency_framing for e in r.extracted] == [1.0, 0.0]),
    ),
    _bd(
        "BD17",
        "pusty opis what → cytat",
        "what = „”",
        "what = „Dane z 2015 r.”",
        _resp(_llm(quote="Dane z 2015 r.", what="  ")),
        lambda r: _assert(r.extracted[0].what == "Dane z 2015 r."),
    ),
    _bd(
        "BD18",
        "zmyślony cytat jest odrzucany",
        "2 daty, w tym jedna z cytatem spoza tekstu",
        "extracted = [d1]",
        _resp(_llm(quote="Dane z 2015 r."), _llm(id="d2", quote="tego zdania w ogóle nie ma w tekście")),
        lambda r: _assert([e.id for e in r.extracted] == ["d1"]),
    ),
    _bd(
        "BD19",
        "tylko problem niskiej wagi",
        "tekst z 2024-03-11, źródło opublikowane 2024-03-20",
        "issues = [BEFORE_SOURCES (low)]; dates_consistent = True",
        _resp(
            _llm(
                quote="Właśnie zawalił się most",
                match=_match(
                    found=True,
                    source_id="s3",
                    source_quote="most",
                    iso_start="2024-03-10",
                    iso_end="2024-03-10",
                    granularity="day",
                    status="occurred",
                ),
            )
        ),
        lambda r: _assert([i.code for i in r.issues] == ["BEFORE_SOURCES"] and r.dates_consistent is True),
        sources=[TruthSource(id="s3", content="Runął most.", published_at=date(2024, 3, 20))],
        article_date=d("2024-03-11"),
    ),
    _bd(
        "BD20",
        "problem średniej wagi psuje spójność",
        "„środa 12 marca 2024” (wtorek)",
        "dates_consistent = False",
        _resp(
            _llm(
                quote="środa 12 marca 2024",
                iso_start="2024-03-12",
                iso_end="2024-03-12",
                granularity="day",
                absolute_given=True,
                weekday_mentioned="środa",
            )
        ),
        lambda r: _assert(r.dates_consistent is False),
        text="Było to w środa 12 marca 2024.",
    ),
    _bd(
        "BD21",
        "tekst bez dat",
        "LLM: dates = []",
        "dates_consistent = True, extracted = [], issues = []",
        _resp(),
        lambda r: _assert(r.dates_consistent and r.extracted == [] and r.issues == []),
    ),
    _bd(
        "BD22",
        "cytat odnaleziony bez względu na wielkość liter",
        "LLM: quote „właśnie zawalił się most” (mała litera)",
        "extracted[0].quote = „Właśnie zawalił się most” (z tekstu), start=44",
        _resp(_llm(quote="właśnie zawalił się most")),
        lambda r: _assert(r.extracted[0].quote == "Właśnie zawalił się most" and r.extracted[0].start == 44),
    ),
    _bd(
        "BD23",
        "cytat źródła z drobną literówką",
        "source_quote „Wczoraj wieczorem zawalilo się przęsło mostu”",
        "dopasowanie przyjęte; source_quote z oryginału źródła",
        _resp(
            _llm(
                quote="Właśnie zawalił się most",
                match=_match(
                    found=True,
                    source_id="pap",
                    source_quote="Wczoraj wieczorem zawalilo się przęsło mostu",
                    iso_start="2019-06-03",
                    granularity="day",
                    status="occurred",
                ),
            )
        ),
        lambda r: _assert(
            r.extracted[0].source_id == "pap"
            and r.extracted[0].source_quote is not None
            and r.extracted[0].source_quote in BD_SRC.content
        ),
    ),
    _bd(
        "BD24",
        "kategoria tekstu przekazana dalej",
        "text_category = economic",
        "text_category = economic",
        _resp(category="economic"),
        lambda r: _assert(r.text_category == "economic"),
    ),
    _bd(
        "BD25",
        "granularność week z LLM",
        "iso 2024-03-10…2024-03-16, granularity=week",
        "extracted[0].granularity = week",
        _resp(_llm(quote="Dane z 2015 r.", iso_start="2024-03-10", iso_end="2024-03-16", granularity="week")),
        lambda r: _assert(r.extracted[0].granularity == "week"),
    ),
    _bd(
        "BD26",
        "stary news jako bieżący (pełny przepływ)",
        "„Właśnie zawalił się most” (recency 0.95, breaking), źródło PAP 2019-06-03, tekst z 2024-03-12",
        "OUTDATED_AS_CURRENT (high, Δ=1744); dates_consistent = False",
        _resp(
            _llm(
                quote="Właśnie zawalił się most w Toruniu",
                recency_framing=0.95,
                match=_match(
                    found=True,
                    source_id="pap",
                    source_quote="zawaliło się przęsło mostu",
                    iso_start="2019-06-03",
                    iso_end="2019-06-03",
                    granularity="day",
                    status="occurred",
                ),
            ),
            category="breaking",
        ),
        lambda r: _assert(
            [(i.code, i.severity, i.delta_days) for i in r.issues] == [("OUTDATED_AS_CURRENT", "high", 1744)]
            and not r.dates_consistent
        ),
        article_date=d("2024-03-12"),
    ),
    _bd(
        "BD27",
        "offset problemu wskazuje cytat w tekście",
        "jak BD26",
        "text[issue.start:issue.end] == issue.input_quote",
        _resp(
            _llm(
                quote="Właśnie zawalił się most w Toruniu",
                recency_framing=0.95,
                match=_match(found=True, source_id="pap", source_quote="zawaliło się", iso_start="2019-06-03", granularity="day", status="occurred"),
            ),
            category="breaking",
        ),
        lambda r: _assert(all(BD_TEXT[i.start : i.end] == i.input_quote for i in r.issues if i.start is not None) and r.issues != []),
        article_date=d("2024-03-12"),
    ),
    Case(
        "BD28",
        "BD",
        "pusty tekst nie wywołuje LLM",
        "analyze_dates(„   ”) z atrapą LLM, która rzuca wyjątek",
        "dates_consistent = True, extracted = [], bez wywołania LLM",
        _bd_empty_text,
    ),
]
