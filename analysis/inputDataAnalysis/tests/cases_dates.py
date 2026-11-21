"""Przypadki dla ``dates.py``: TimeRef, dist, wyrażenia względne, dni tygodnia, formatowanie."""

from __future__ import annotations

from collections.abc import Callable
from datetime import date

from inputDataAnalysis.dates import (
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
    plural,
)

from .case_base import Case, d, iso, ref_str

BASE = date(2024, 3, 20)  # środa


# --- DT: TimeRef.from_iso ---------------------------------------------------------------------


def _dt(cid: str, title: str, args: tuple[str, ...], exp: tuple[str, str, str] | None) -> Case:
    def check() -> None:
        got = TimeRef.from_iso(*args)
        if exp is None:
            assert got is None
        else:
            assert got is not None
            assert (got.start.isoformat(), got.end.isoformat(), got.granularity) == exp

    wej = "from_iso(" + ", ".join(repr(a) for a in args) + ")"
    ocz = "None" if exp is None else f"{exp[0]} … {exp[1]}, granularity={exp[2]}"
    return Case(cid, "DT", title, wej, ocz, check)


DT_CASES = [
    _dt("DT01", "pełna data dzienna", ("2024-03-12",), ("2024-03-12", "2024-03-12", "day")),
    _dt("DT02", "sam miesiąc", ("2024-03",), ("2024-03-01", "2024-03-31", "month")),
    _dt("DT03", "luty w roku przestępnym", ("2024-02",), ("2024-02-01", "2024-02-29", "month")),
    _dt("DT04", "luty w roku zwykłym", ("2023-02",), ("2023-02-01", "2023-02-28", "month")),
    _dt("DT05", "miesiąc 30-dniowy", ("2024-04",), ("2024-04-01", "2024-04-30", "month")),
    _dt("DT06", "sam rok", ("2024",), ("2024-01-01", "2024-12-31", "year")),
    _dt("DT07", "kwartał Q1", ("2024-Q1",), ("2024-01-01", "2024-03-31", "quarter")),
    _dt("DT08", "kwartał małą literą", ("2024-q4",), ("2024-10-01", "2024-12-31", "quarter")),
    _dt("DT09", "kwartał bez myślnika", ("2024Q2",), ("2024-04-01", "2024-06-30", "quarter")),
    _dt("DT10", "kwartał Q3", ("2023-Q3",), ("2023-07-01", "2023-09-30", "quarter")),
    _dt("DT11", "datetime z godziną", ("2024-03-12T15:30:00",), ("2024-03-12", "2024-03-12", "day")),
    _dt("DT12", "datetime ze strefą Z", ("2024-03-12T00:00:00Z",), ("2024-03-12", "2024-03-12", "day")),
    _dt("DT13", "spacje wokół daty", (" 2024-03-12 ",), ("2024-03-12", "2024-03-12", "day")),
    _dt("DT14", "pusty napis", ("",), None),
    _dt("DT15", "same spacje", ("   ",), None),
    _dt("DT16", "tekst zamiast daty", ("nie data",), None),
    _dt("DT17", "miesiąc 13", ("2024-13",), None),
    _dt("DT18", "30 lutego", ("2024-02-30",), None),
    _dt("DT19", "29 lutego w roku zwykłym", ("2023-02-29",), None),
    _dt("DT20", "29 lutego w roku przestępnym", ("2024-02-29",), ("2024-02-29", "2024-02-29", "day")),
    _dt("DT21", "format polski DD.MM.RRRR nie jest ISO", ("12.03.2024",), None),
    _dt("DT22", "kwartał Q5", ("2024-Q5",), None),
    _dt("DT23", "rok dwucyfrowy", ("24",), None),
    _dt(
        "DT24",
        "przedział = pełny miesiąc → month",
        ("2024-03-01", "2024-03-31"),
        ("2024-03-01", "2024-03-31", "month"),
    ),
    _dt(
        "DT25",
        "przedział = pełny rok → year",
        ("2024-01-01", "2024-12-31"),
        ("2024-01-01", "2024-12-31", "year"),
    ),
    _dt(
        "DT26",
        "ten sam dzień jako przedział → day",
        ("2024-03-12", "2024-03-12"),
        ("2024-03-12", "2024-03-12", "day"),
    ),
    _dt(
        "DT27",
        "tydzień bez podpowiedzi → range",
        ("2024-03-10", "2024-03-16"),
        ("2024-03-10", "2024-03-16", "range"),
    ),
    _dt(
        "DT28",
        "tydzień z podpowiedzią week",
        ("2024-03-10", "2024-03-16", "week"),
        ("2024-03-10", "2024-03-16", "week"),
    ),
    _dt(
        "DT29",
        "kwartał jako przedział + podpowiedź quarter",
        ("2024-01-01", "2024-03-31", "quarter"),
        ("2024-01-01", "2024-03-31", "quarter"),
    ),
    _dt(
        "DT30",
        "od miesiąca do miesiąca",
        ("2024-03", "2024-05"),
        ("2024-03-01", "2024-05-31", "range"),
    ),
    _dt(
        "DT31",
        "koniec przed początkiem jest ignorowany",
        ("2024-03-20", "2024-03-10"),
        ("2024-03-20", "2024-03-20", "day"),
    ),
    _dt(
        "DT32",
        "nieczytelny koniec jest ignorowany",
        ("2024-03-12", "bzdura"),
        ("2024-03-12", "2024-03-12", "day"),
    ),
    _dt("DT33", "rok do roku", ("2024", "2025"), ("2024-01-01", "2025-12-31", "range")),
    _dt(
        "DT34",
        "podpowiedź month nie nadpisuje dnia",
        ("2024-03-12", "", "month"),
        ("2024-03-12", "2024-03-12", "day"),
    ),
    _dt(
        "DT35",
        "miesiąc + jego ostatni dzień → month",
        ("2024-01", "2024-01-31"),
        ("2024-01-01", "2024-01-31", "month"),
    ),
    _dt("DT36", "pusty początek, podany koniec", ("", "2024-03-12"), None),
]


# --- DW: width_days ---------------------------------------------------------------------------


def _dw(cid: str, value: str, exp: int) -> Case:
    def check() -> None:
        assert iso(value).width_days == exp

    return Case(cid, "DW", f"szerokość {value}", f"from_iso({value!r}).width_days", str(exp), check)


DW_CASES = [
    _dw("DW01", "2024-03-12", 1),
    _dw("DW02", "2024-03", 31),
    _dw("DW03", "2024-02", 29),
    _dw("DW04", "2023-02", 28),
    _dw("DW05", "2024", 366),
    _dw("DW06", "2023", 365),
    _dw("DW07", "2024-Q1", 91),
    _dw("DW08", "2023-Q1", 90),
]


# --- DI: dist ---------------------------------------------------------------------------------


def _di(cid: str, title: str, a: TimeRef, b: TimeRef, exp: int) -> Case:
    def check() -> None:
        assert dist(a, b) == exp
        assert dist(b, a) == exp  # symetria

    return Case(cid, "DI", title, f"dist({ref_str(a)}, {ref_str(b)})", f"{exp} (symetrycznie)", check)


DI_CASES = [
    _di("DI01", "dzień w środku miesiąca", iso("2024-03"), iso("2024-03-15"), 0),
    _di("DI02", "ten sam dzień", iso("2024-03-12"), iso("2024-03-12"), 0),
    _di("DI03", "dni sąsiednie", iso("2024-03-12"), iso("2024-03-13"), 1),
    _di("DI04", "miesiąc i dzień po nim", iso("2024-03"), iso("2024-04-02"), 2),
    _di("DI05", "dwa lata", iso("2022-03-12"), iso("2024-03-12"), 731),
    _di("DI06", "sąsiednie lata", iso("2023"), iso("2024"), 1),
    _di("DI07", "lata 2020 i 2024", iso("2020"), iso("2024"), 1096),
    _di("DI08", "miesiąc w roku", iso("2024"), iso("2024-07"), 0),
    _di("DI09", "kwartał i dzień po nim", iso("2024-Q1"), iso("2024-04-01"), 1),
    _di("DI10", "przez 29 lutego", iso("2024-02-28"), iso("2024-03-01"), 2),
    _di("DI11", "bez 29 lutego", iso("2023-02-28"), iso("2023-03-01"), 1),
    _di("DI12", "przedział tygodniowy i dzień", iso("2024-03-10", "2024-03-16"), iso("2024-03-20"), 4),
    _di("DI13", "przełom roku", iso("2024-12-31"), iso("2025-01-01"), 1),
    _di("DI14", "nakładające się przedziały", iso("2024-03", "2024-05"), iso("2024-04", "2024-06"), 0),
    _di("DI15", "przedział zawarty w przedziale", iso("2024"), iso("2024-Q2"), 0),
]


# --- RE: parse_relative -----------------------------------------------------------------------


def _re(
    cid: str,
    expr: str,
    exp: tuple[str, str, str] | None,
    base: date = BASE,
    known_bug: str = "",
) -> Case:
    def check() -> None:
        got = parse_relative(expr, base)
        if exp is None:
            assert got is None
        else:
            assert got is not None
            assert (got.start.isoformat(), got.end.isoformat(), got.granularity) == exp

    ocz = "None" if exp is None else f"{exp[0]} … {exp[1]}, {exp[2]}"
    return Case(cid, "RE", f"„{expr}”", f"parse_relative({expr!r}, {base})", ocz, check, known_bug)


RE_CASES = [
    _re("RE01", "wczoraj", ("2024-03-19", "2024-03-19", "day")),
    _re("RE02", "dzisiaj", ("2024-03-20", "2024-03-20", "day")),
    _re("RE03", "dziś", ("2024-03-20", "2024-03-20", "day")),
    _re("RE04", "przedwczoraj", ("2024-03-18", "2024-03-18", "day")),
    _re("RE05", "jutro", ("2024-03-21", "2024-03-21", "day")),
    _re("RE06", "pojutrze", ("2024-03-22", "2024-03-22", "day")),
    _re("RE07", "2 dni temu", ("2024-03-18", "2024-03-18", "day")),
    _re("RE08", "5 dni temu", ("2024-03-15", "2024-03-15", "day")),
    _re("RE09", "tydzień temu", ("2024-03-10", "2024-03-16", "week")),
    _re("RE10", "2 tygodnie temu", ("2024-03-03", "2024-03-09", "week")),
    _re("RE11", "w zeszłym tygodniu", ("2024-03-10", "2024-03-16", "week")),
    _re("RE12", "tydzień", ("2024-03-10", "2024-03-16", "week")),
    _re("RE13", "miesiąc temu", ("2024-02-01", "2024-02-29", "month")),
    _re("RE14", "3 miesiące temu", ("2023-12-01", "2023-12-31", "month")),
    _re("RE15", "miesiąc", ("2024-02-01", "2024-02-29", "month")),
    _re("RE16", "rok temu", ("2023-01-01", "2023-12-31", "year")),
    _re("RE17", "w zeszłym roku", ("2023-01-01", "2023-12-31", "year")),
    _re("RE18", "2 lata temu", ("2022-01-01", "2022-12-31", "year")),
    _re("RE19", "10 lat temu", ("2014-01-01", "2014-12-31", "year")),
    _re("RE20", "rok", ("2023-01-01", "2023-12-31", "year")),
    _re("RE21", "w poniedziałek", ("2024-03-18", "2024-03-18", "day")),
    _re("RE22", "wczoraj", ("2024-02-29", "2024-02-29", "day"), base=date(2024, 3, 1)),
    _re("RE23", "wczoraj", ("2024-12-31", "2024-12-31", "day"), base=date(2025, 1, 1)),
    _re("RE24", "", None),
    _re("RE25", "   ", None),
    _re("RE26", "niedawno", None),
    _re("RE27", "sdfsdf", None),
    _re(
        "RE28",
        "godzinę temu",
        ("2024-03-20", "2024-03-20", "day"),
        known_bug="dateparser nie rozpoznaje biernika „godzinę temu” i zwraca None",
    ),
]


# --- WD: parse_weekday ------------------------------------------------------------------------


def _wd(cid: str, text: str | None, exp: int | None) -> Case:
    names = ["pon", "wt", "śr", "czw", "pt", "sob", "nd"]

    def check() -> None:
        assert parse_weekday(text) == exp

    ocz = "None" if exp is None else f"{exp} ({names[exp]})"
    return Case(cid, "WD", f"{text!r}", f"parse_weekday({text!r})", ocz, check)


WD_CASES = [
    _wd("WD01", "poniedziałek", 0),
    _wd("WD02", "w poniedziałek", 0),
    _wd("WD03", "pon.", 0),
    _wd("WD04", "wtorek", 1),
    _wd("WD05", "we wtorek", 1),
    _wd("WD06", "wt", 1),
    _wd("WD07", "środa", 2),
    _wd("WD08", "ŚRODA", 2),
    _wd("WD09", "w środę", 2),
    _wd("WD10", "śr.", 2),
    _wd("WD11", "czwartek", 3),
    _wd("WD12", "czw.", 3),
    _wd("WD13", "piątek", 4),
    _wd("WD14", "w piątek", 4),
    _wd("WD15", "pt", 4),
    _wd("WD16", "sobota", 5),
    _wd("WD17", "w sobotę", 5),
    _wd("WD18", "sob.", 5),
    _wd("WD19", "niedziela", 6),
    _wd("WD20", "w niedzielę", 6),
    _wd("WD21", "nd", 6),
    _wd("WD22", "Dziś w środę 12 marca", 2),
    _wd("WD23", "wtedy", None),
    _wd("WD24", "środowy", None),
    _wd("WD25", "", None),
    _wd("WD26", None, None),
    _wd("WD27", "12 marca 2024", None),
]


# --- FM: formatowanie -------------------------------------------------------------------------

DAY = iso("2024-03-12")
NEWYEAR = iso("2025-01-01")
MARCH = iso("2024-03")
DEC = iso("2023-12")
FEB = iso("2024-02")
NOV = iso("2024-11")
Y2015 = iso("2015")
Q2 = iso("2024-Q2")
RANGE = iso("2024-03-10", "2024-03-16")
CROSS = iso("2024-02-28", "2024-03-05")
WEEK = iso("2024-03-10", "2024-03-16", "week")


def _fm_ref(cid: str, fn: Callable[[TimeRef], str], ref: TimeRef, exp: str) -> Case:
    def check() -> None:
        assert fn(ref) == exp

    name = fn.__name__
    return Case(cid, "FM", f"{name} – {ref_str(ref)}", f"{name}({ref_str(ref)})", f"„{exp}”", check)


def _fm_val(cid: str, label: str, fn: Callable[[], str], exp: str) -> Case:
    def check() -> None:
        assert fn() == exp

    return Case(cid, "FM", label, label, f"„{exp}”", check)


FM_CASES = [
    _fm_val("FM01", "fmt_day(2024-03-12)", lambda: fmt_day(d("2024-03-12")), "12 marca 2024"),
    _fm_val("FM02", "fmt_day(2025-01-01)", lambda: fmt_day(d("2025-01-01")), "1 stycznia 2025"),
    _fm_ref("FM03", fmt_on, DAY, "na 12 marca 2024"),
    _fm_ref("FM04", fmt_on, MARCH, "na marzec 2024"),
    _fm_ref("FM05", fmt_on, DEC, "na grudzień 2023"),
    _fm_ref("FM06", fmt_on, Y2015, "na 2015 r."),
    _fm_ref("FM07", fmt_on, Q2, "na 2. kwartał 2024 r."),
    _fm_ref("FM08", fmt_on, RANGE, "na okres 10–16 marca 2024"),
    _fm_ref("FM09", fmt_on, CROSS, "na okres 28 lutego 2024 – 5 marca 2024"),
    _fm_ref("FM10", fmt_on, WEEK, "na okres 10–16 marca 2024"),
    _fm_ref("FM11", fmt_at, DAY, "12 marca 2024"),
    _fm_ref("FM12", fmt_at, MARCH, "w marcu 2024"),
    _fm_ref("FM13", fmt_at, FEB, "w lutym 2024"),
    _fm_ref("FM14", fmt_at, NOV, "w listopadzie 2024"),
    _fm_ref("FM15", fmt_at, Y2015, "w 2015 r."),
    _fm_ref("FM16", fmt_at, Q2, "w 2. kwartale 2024 r."),
    _fm_ref("FM17", fmt_at, RANGE, "w okresie 10–16 marca 2024"),
    _fm_ref("FM18", fmt_from, DAY, "z 12 marca 2024"),
    _fm_ref("FM19", fmt_from, DEC, "z grudnia 2023"),
    _fm_ref("FM20", fmt_from, Y2015, "z 2015 r."),
    _fm_ref("FM21", fmt_from, Q2, "z 2. kwartału 2024 r."),
    _fm_ref("FM22", fmt_from, RANGE, "z okresu 10–16 marca 2024"),
    _fm_ref("FM23", fmt_from, NEWYEAR, "z 1 stycznia 2025"),
    _fm_val("FM24", "fmt_days(1)", lambda: fmt_days(1), "1 dzień"),
    _fm_val("FM25", "fmt_days(2)", lambda: fmt_days(2), "2 dni"),
    _fm_val("FM26", "fmt_days(5)", lambda: fmt_days(5), "5 dni"),
    _fm_val("FM27", "fmt_days(731)", lambda: fmt_days(731), "731 dni"),
    *[
        _fm_val(f"FM{28 + i}", f"plural({n}, rok/lata/lat)", lambda n=n: plural(n, "rok", "lata", "lat"), exp)
        for i, (n, exp) in enumerate(
            [
                (1, "1 rok"),
                (2, "2 lata"),
                (4, "4 lata"),
                (5, "5 lat"),
                (12, "12 lat"),
                (13, "13 lat"),
                (14, "14 lat"),
                (21, "21 lat"),
                (22, "22 lata"),
                (25, "25 lat"),
                (104, "104 lata"),
                (112, "112 lat"),
            ]
        )
    ],
    _fm_val(
        "FM40", "plural(2, miesiąc/…)", lambda: plural(2, "miesiąc", "miesiące", "miesięcy"), "2 miesiące"
    ),
    _fm_val(
        "FM41", "plural(5, miesiąc/…)", lambda: plural(5, "miesiąc", "miesiące", "miesięcy"), "5 miesięcy"
    ),
    _fm_val(
        "FM42",
        "plural(22, miesiąc/…)",
        lambda: plural(22, "miesiąc", "miesiące", "miesięcy"),
        "22 miesiące",
    ),
    *[
        _fm_val(f"FM{43 + i}", f"humanize_days({n})", lambda n=n: humanize_days(n), exp)
        for i, (n, exp) in enumerate(
            [
                (0, "0 dni"),
                (1, "1 dzień"),
                (59, "59 dni"),
                (60, "2 miesiące"),
                (89, "2 miesiące"),
                (150, "5 miesięcy"),
                (364, "12 miesięcy"),
                (365, "1 rok"),
                (730, "2 lata"),
                (1461, "4 lata"),
                (1744, "4 lata"),
                (1826, "5 lat"),
            ]
        )
    ],
]
