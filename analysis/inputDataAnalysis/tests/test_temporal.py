from datetime import date

from inputDataAnalysis.dates import TimeRef
from inputDataAnalysis.models import LLMDatesResponse, TruthSource
from inputDataAnalysis.temporal import DateItem, SourceMatch, build_dates_result, evaluate

SRC = TruthSource(id="s1", title="PAP", content="...", published_at=date(2019, 6, 4))


def item(**kw) -> DateItem:
    defaults = dict(
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


def codes(issues):
    return [i.code for i in issues]


def test_date_mismatch_high_with_description():
    it = item(
        ref=TimeRef.day(date(2024, 3, 12)),
        match=SourceMatch(SRC, "12 marca 2022", TimeRef.day(date(2022, 3, 12)), "occurred"),
    )
    issues, _ = evaluate([it], None, sources=[SRC])
    assert codes(issues) == ["DATE_MISMATCH"]
    assert issues[0].severity == "high"
    assert issues[0].delta_days == 731
    assert issues[0].description == (
        "Tekst datuje »zawalenie mostu« na 12 marca 2024, a źródło »PAP« na 12 marca 2022 "
        "(różnica 731 dni)."
    )
    assert issues[0].source_id == "s1"


def test_month_vs_day_inside_is_consistent():
    it = item(
        ref=TimeRef.from_iso("2024-03"),
        match=SourceMatch(SRC, "15.03.2024", TimeRef.day(date(2024, 3, 15)), "occurred"),
    )
    issues, _ = evaluate([it], date(2024, 4, 1), sources=[SRC])
    assert "DATE_MISMATCH" not in codes(issues)


def test_one_day_tolerance():
    it = item(
        ref=TimeRef.day(date(2024, 3, 12)),
        match=SourceMatch(SRC, "x", TimeRef.day(date(2024, 3, 13)), "occurred"),
    )
    issues, _ = evaluate([it], None, sources=[SRC])
    assert issues == []


def test_outdated_news_presented_as_current():
    it = item(
        tense="present",
        recency=0.9,
        match=SourceMatch(SRC, "Wczoraj zawaliło się", TimeRef.day(date(2019, 6, 3)), "occurred"),
    )
    issues, _ = evaluate([it], date(2024, 3, 12), category="breaking", sources=[SRC])
    assert "OUTDATED_AS_CURRENT" in codes(issues)
    issue = next(i for i in issues if i.code == "OUTDATED_AS_CURRENT")
    assert issue.severity == "high"
    assert "4 lata przed publikacją" in issue.description


def test_outdated_uses_source_publication_when_no_event_date():
    it = item(tense="present", recency=0.9, match=SourceMatch(SRC, "most", None, "occurred"))
    issues, _ = evaluate([it], date(2024, 3, 12), category="breaking", sources=[SRC])
    assert codes(issues) == ["OUTDATED_AS_CURRENT"]


def test_old_event_mentioned_historically_is_fine():
    it = item(
        recency=0.1,
        match=SourceMatch(SRC, "x", TimeRef.day(date(2019, 6, 3)), "occurred"),
    )
    issues, _ = evaluate([it], date(2024, 3, 12), category="breaking", sources=[SRC])
    assert "OUTDATED_AS_CURRENT" not in codes(issues)


def test_weekday_inconsistency():
    # 12 marca 2024 był wtorkiem
    it = item(
        quote="w środę 12 marca 2024",
        ref=TimeRef.day(date(2024, 3, 12)),
        absolute_given=True,
        weekday_mentioned="środa",
    )
    issues, _ = evaluate([it], None)
    assert codes(issues) == ["INTERNAL_INCONSISTENCY"]
    assert (
        issues[0].description == "Tekst podaje, że 12 marca 2024 to środa, ale ten dzień to wtorek."
    )


def test_relative_vs_absolute_inconsistency():
    it = item(
        ref=TimeRef.day(date(2024, 3, 2)),
        absolute_given=True,
        relative_expression="wczoraj",
        relative_ref=TimeRef.day(date(2024, 3, 19)),
    )
    issues, _ = evaluate([it], date(2024, 3, 20))
    assert codes(issues) == ["INTERNAL_INCONSISTENCY"]


def test_past_event_dated_after_publication():
    it = item(ref=TimeRef.day(date(2024, 5, 1)))
    issues, _ = evaluate([it], date(2024, 3, 20))
    assert codes(issues) == ["INTERNAL_INCONSISTENCY"]


def test_anachronism():
    src = TruthSource(id="s2", content="...", published_at=date(2024, 6, 1))
    it = item(match=SourceMatch(src, "x", TimeRef.day(date(2024, 5, 30)), "occurred"))
    issues, _ = evaluate([it], date(2024, 3, 1), sources=[src])
    assert "ANACHRONISM" in codes(issues)


def test_future_as_past():
    it = item(match=SourceMatch(SRC, "planowane otwarcie", TimeRef.from_iso("2025-06"), "planned"))
    issues, _ = evaluate([it], date(2024, 3, 1), sources=[SRC])
    assert "FUTURE_AS_PAST" in codes(issues)
    issue = next(i for i in issues if i.code == "FUTURE_AS_PAST")
    assert issue.description.endswith("to plan na czerwiec 2025.")


def test_future_as_past_not_flagged_after_plan_date():
    it = item(match=SourceMatch(SRC, "planowane", TimeRef.from_iso("2023-06"), "planned"))
    issues, _ = evaluate([it], date(2024, 3, 1), sources=[SRC])
    assert "FUTURE_AS_PAST" not in codes(issues)


def test_stale_data():
    it = item(role="data_as_of", what="bezrobocie", ref=TimeRef.from_iso("2015"), recency=0.8)
    issues, _ = evaluate([it], date(2024, 3, 1))
    assert codes(issues) == ["STALE_DATA"]
    assert issues[0].description.startswith("Dane o »bezrobocie« pochodzą z 2015 r.")


def test_before_sources_is_low_and_keeps_consistency():
    src = TruthSource(id="s3", content="...", published_at=date(2024, 3, 20))
    it = item(match=SourceMatch(src, "x", TimeRef.day(date(2024, 3, 10)), "occurred"))
    issues, _ = evaluate([it], date(2024, 3, 11), sources=[src])
    assert codes(issues) == ["BEFORE_SOURCES"]
    assert issues[0].severity == "low"


def test_missing_article_date_and_sources_are_reported_as_skipped():
    _, skipped = evaluate([item(ref=TimeRef.day(date(2024, 3, 1)))], None)
    checks = {s.check for s in skipped}
    assert {"OUTDATED_AS_CURRENT", "ANACHRONISM", "STALE_DATA", "DATE_MISMATCH"} <= checks


# --- pełna ścieżka od odpowiedzi LLM ---------------------------------------------------------


def _llm_item(**kw):
    base = dict(
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
        match=dict(
            found=False,
            source_id="",
            source_quote="",
            iso_start="",
            iso_end="",
            granularity="unknown",
            relative_expression="",
            status="unknown",
        ),
    )
    return {**base, **kw}


def test_build_dates_result_old_news_as_new():
    text = "PILNE! Właśnie zawalił się most na Wiśle w Toruniu. Dziś w środę 12 marca 2024 zamknięto rejon."
    src = TruthSource(
        id="pap",
        title="PAP",
        published_at=date(2019, 6, 4),
        content="Wczoraj wieczorem zawaliło się przęsło mostu na Wiśle w Toruniu.",
    )
    response = LLMDatesResponse.model_validate(
        dict(
            article_date_in_text="",
            text_category="breaking",
            recency_framing=0.95,
            dates=[
                _llm_item(
                    quote="Właśnie zawalił się most na Wiśle w Toruniu",
                    what="zawalenie mostu w Toruniu",
                    tense="past",
                    recency_framing=0.95,
                    match=dict(
                        found=True,
                        source_id="pap",
                        source_quote="Wczoraj wieczorem zawaliło się przęsło mostu",
                        iso_start="2019-06-03",
                        iso_end="2019-06-03",
                        granularity="day",
                        relative_expression="Wczoraj",
                        status="occurred",
                    ),
                ),
                _llm_item(
                    id="d2",
                    quote="Dziś w środę 12 marca 2024",
                    what="zamknięcie rejonu",
                    iso_start="2024-03-12",
                    iso_end="2024-03-12",
                    granularity="day",
                    absolute_given=True,
                    relative_expression="Dziś",
                    weekday_mentioned="środa",
                    recency_framing=0.9,
                ),
                _llm_item(id="d3", quote="tego zdania nie ma w tekście", what="halucynacja"),
            ],
        )
    )
    result = build_dates_result(text, [src], response, article_date=date(2024, 3, 12))

    assert result.dates_consistent is False
    found = codes(result.issues)
    assert "OUTDATED_AS_CURRENT" in found
    assert "INTERNAL_INCONSISTENCY" in found  # 12.03.2024 to wtorek
    assert [e.id for e in result.extracted] == ["d1", "d2"]  # halucynacja odrzucona
    assert result.extracted[0].source_date_from == date(2019, 6, 3)
    assert result.unverified == ["»Dziś w środę 12 marca 2024« (zamknięcie rejonu)"]
    for issue in result.issues:
        if issue.start is not None:
            assert text[issue.start : issue.end] == issue.input_quote


def test_hallucinated_source_quote_is_not_a_match():
    text = "Most zawalił się w 2019 roku."
    src = TruthSource(
        id="pap", content="Zawaliło się przęsło mostu.", published_at=date(2019, 6, 4)
    )
    response = LLMDatesResponse.model_validate(
        dict(
            article_date_in_text="",
            text_category="other",
            recency_framing=0.0,
            dates=[
                _llm_item(
                    quote="w 2019 roku",
                    what="zawalenie mostu",
                    iso_start="2019-01-01",
                    iso_end="2019-12-31",
                    granularity="year",
                    absolute_given=True,
                    match=dict(
                        found=True,
                        source_id="pap",
                        source_quote="Most zawalił się 3 czerwca 2015 r.",
                        iso_start="2015-06-03",
                        iso_end="2015-06-03",
                        granularity="day",
                        relative_expression="",
                        status="occurred",
                    ),
                )
            ],
        )
    )
    result = build_dates_result(text, [src], response)
    assert result.issues == []
    assert result.extracted[0].source_id is None
    assert result.unverified == ["»w 2019 roku« (zawalenie mostu)"]
