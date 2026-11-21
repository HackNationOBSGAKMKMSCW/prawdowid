from datetime import date

from inputDataAnalysis.dates import (
    TimeRef,
    dist,
    fmt_at,
    fmt_from,
    fmt_on,
    humanize_days,
    parse_relative,
    parse_weekday,
)


def test_from_iso_partial_forms():
    assert TimeRef.from_iso("2024-03") == TimeRef(date(2024, 3, 1), date(2024, 3, 31), "month")
    assert TimeRef.from_iso("2024") == TimeRef(date(2024, 1, 1), date(2024, 12, 31), "year")
    assert TimeRef.from_iso("2024-03-12") == TimeRef.day(date(2024, 3, 12))
    assert TimeRef.from_iso("2024-Q2").granularity == "quarter"
    assert TimeRef.from_iso("") is None
    assert TimeRef.from_iso("nie data") is None
    assert TimeRef.from_iso("2024-02-30") is None


def test_from_iso_infers_granularity_from_bounds():
    assert TimeRef.from_iso("2024-03-01", "2024-03-31").granularity == "month"
    assert TimeRef.from_iso("2024-01-01", "2024-12-31").granularity == "year"
    assert TimeRef.from_iso("2024-03-12", "2024-03-12").granularity == "day"
    assert TimeRef.from_iso("2024-03-10", "2024-03-16", "week").granularity == "week"


def test_dist_intervals():
    march = TimeRef.from_iso("2024-03")
    assert dist(march, TimeRef.day(date(2024, 3, 15))) == 0
    assert dist(march, TimeRef.day(date(2024, 4, 2))) == 2
    assert dist(TimeRef.day(date(2022, 3, 12)), TimeRef.day(date(2024, 3, 12))) == 731


def test_parse_relative():
    base = date(2024, 3, 20)
    assert parse_relative("wczoraj", base) == TimeRef.day(date(2024, 3, 19))
    assert parse_relative("3 dni temu", base) == TimeRef.day(date(2024, 3, 17))
    week = parse_relative("tydzień temu", base)
    assert week.granularity == "week" and week.start <= date(2024, 3, 13) <= week.end
    assert parse_relative("miesiąc temu", base).granularity == "month"
    assert parse_relative("2 lata temu", base) == TimeRef.from_iso("2022")
    assert parse_relative("niedawno", base) is None


def test_parse_weekday():
    assert parse_weekday("środa") == 2
    assert parse_weekday("w środę") == 2
    assert parse_weekday("we wtorek") == 1
    assert parse_weekday("niedzielę") == 6
    assert parse_weekday("wtedy") is None


def test_polish_formatting():
    day = TimeRef.day(date(2024, 3, 12))
    month = TimeRef.from_iso("2024-03")
    year = TimeRef.from_iso("2015")
    assert fmt_on(day) == "na 12 marca 2024"
    assert fmt_on(month) == "na marzec 2024"
    assert fmt_at(month) == "w marcu 2024"
    assert fmt_at(year) == "w 2015 r."
    assert fmt_from(year) == "z 2015 r."
    assert fmt_from(month) == "z marca 2024"
    assert humanize_days(4 * 365 + 10) == "4 lata"
    assert humanize_days(5 * 365) == "5 lat"
    assert humanize_days(90) == "3 miesiące"
    assert humanize_days(12) == "12 dni"
    assert humanize_days(1) == "1 dzień"
