"""Przypadki dla ``spans.py``, ``models.TruthSource``, ``manipulation.py``, ``prompts.py`` i ``pipeline.py``."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import date, datetime
from typing import Any

import pytest
from pydantic import ValidationError

from inputDataAnalysis import LLMError, analyze, analyze_async
from inputDataAnalysis.manipulation import (
    analyze_manipulation,
    build_manipulation_result,
    score_fragments,
)
from inputDataAnalysis.models import (
    CATEGORY_CODES,
    LLMDatesResponse,
    LLMManipulationResponse,
    ManipulationFragment,
    ManipulationResult,
    TruthSource,
)
from inputDataAnalysis.prompts import (
    MAX_SOURCE_CHARS,
    MAX_TOTAL_SOURCE_CHARS,
    manipulation_user,
    render_sources,
)
from inputDataAnalysis.spans import locate_quote

from .case_base import Case

# --- SP: locate_quote -------------------------------------------------------------------------

SP_TEXT = "Rząd przyjął ustawę. To skandaliczna zdrada „elit” wobec narodu! Rząd przyjął też budżet – w całości."


def _sp(
    cid: str,
    title: str,
    quote: str,
    exp: str | None,
    *,
    text: str = SP_TEXT,
    hint: int = 0,
    exp_start: int | None = None,
    known_bug: str = "",
) -> Case:
    def check() -> None:
        span = locate_quote(text, quote, start_hint=hint)
        if exp is None:
            assert span is None, f"oczekiwano None, jest {span} = {text[span[0]:span[1]]!r}" if span else ""
            return
        assert span is not None
        assert text[span[0] : span[1]] == exp
        if exp_start is not None:
            assert span[0] == exp_start

    wej = f"quote={quote!r}" + (f", start_hint={hint}" if hint else "")
    if text != SP_TEXT:
        wej = f"text={text!r}, " + wej
    if exp is None:
        ocz = "None (odrzucony)"
    else:
        ocz = f"„{exp}”" + (f" od pozycji {exp_start}" if exp_start is not None else "")
    return Case(cid, "SP", title, wej, ocz, check, known_bug)


SP_CASES = [
    _sp("SP01", "dokładnie, początek tekstu", "Rząd przyjął", "Rząd przyjął", exp_start=0),
    _sp("SP02", "dokładnie, środek tekstu", "skandaliczna zdrada", "skandaliczna zdrada", exp_start=24),
    _sp("SP03", "dokładnie, koniec tekstu", "w całości.", "w całości.", exp_start=91),
    _sp("SP04", "powtórzony cytat + start_hint", "Rząd przyjął", "Rząd przyjął", hint=5, exp_start=65),
    _sp("SP05", "start_hint za ostatnim wystąpieniem → pierwsze", "Rząd przyjął", "Rząd przyjął", hint=90, exp_start=0),
    _sp("SP06", "wielkie litery", "RZĄD PRZYJĄŁ USTAWĘ", "Rząd przyjął ustawę", exp_start=0),
    _sp("SP07", "małe litery + start_hint", "rząd przyjął", "Rząd przyjął", hint=5, exp_start=65),
    _sp("SP08", "proste cudzysłowy zamiast „”", 'zdrada "elit"', "zdrada „elit”"),
    _sp("SP09", "cudzysłów francuski", "zdrada «elit»", "zdrada „elit”"),
    _sp("SP10", "dywiz zamiast półpauzy", "budżet - w całości", "budżet – w całości"),
    _sp("SP11", "spacje wokół cytatu", "  skandaliczna  ", "skandaliczna", exp_start=24),
    _sp(
        "SP12",
        "fuzzy: jedna literówka",
        "To skandaliczna zdrdda „elit” wobec narodu",
        "To skandaliczna zdrada „elit” wobec narodu",
    ),
    _sp(
        "SP13",
        "fuzzy: brak cudzysłowów wokół słowa",
        "skandaliczna zdrada elit wobec narodu",
        "skandaliczna zdrada „elit” wobec narodu",
        known_bug="zakres z partial_ratio_alignment ucina pierwszą i ostatnią literę "
        "(„kandaliczna … narod”); brak dociągania do granic słów",
    ),
    _sp("SP14", "krótki cytat z literówką (< 8 znaków)", "zdrda", None),
    _sp("SP15", "zmyślony cytat", "minister ukradł miliardy złotych", None),
    _sp("SP16", "pusty cytat", "", None),
    _sp("SP17", "cytat z samych spacji", "   ", None),
    _sp("SP18", "pusty tekst", "Rząd przyjął", None, text=""),
    _sp(
        "SP19",
        "cytat z dopisanym zmyślonym zdaniem",
        "To skandaliczna zdrada „elit” wobec narodu! Rząd przyjął też budżet – w całości. "
        "I jeszcze więcej tekstu którego nie ma",
        None,
        known_bug="cytat dłuższy niż tekst jest „odnajdywany” jako cały tekst, bo partial_ratio "
        "dopasowuje krótszy napis (tekst) do dłuższego (cytatu)",
    ),
    _sp("SP20", "słowa w innej kolejności", "narodu wobec elit zdrada skandaliczna", None),
    _sp("SP21", "cytat w polu z polskimi znakami", "zdrada „elit” wobec narodu!", "zdrada „elit” wobec narodu!"),
    _sp("SP22", "cytat = cały tekst", SP_TEXT, SP_TEXT, exp_start=0),
]


# --- TS: TruthSource --------------------------------------------------------------------------


def _ts(cid: str, title: str, data: dict[str, Any], exp: dict[str, Any] | None) -> Case:
    def check() -> None:
        if exp is None:
            with pytest.raises(ValidationError):
                TruthSource.model_validate(data)
            return
        s = TruthSource.model_validate(data)
        for key, value in exp.items():
            assert getattr(s, key) == value, key

    ocz = "ValidationError" if exp is None else ", ".join(f"{k}={v!s}" for k, v in exp.items())
    return Case(cid, "TS", title, repr(data), ocz, check)


TS_CASES = [
    _ts("TS01", "minimalne źródło", {"id": "s1", "content": "abc"}, {"id": "s1", "content": "abc", "published_at": None, "label": "s1"}),
    _ts("TS02", "aliasy source_id + text", {"source_id": "s2", "text": "abc"}, {"id": "s2", "content": "abc"}),
    _ts("TS03", "id liczbowe + body", {"id": 7, "body": "abc"}, {"id": "7", "content": "abc"}),
    _ts("TS04", "data ISO", {"id": "s", "content": "x", "published_at": "2024-03-12"}, {"published_at": date(2024, 3, 12)}),
    _ts("TS05", "datetime ze strefą Z", {"id": "s", "content": "x", "published_at": "2024-03-12T10:00:00Z"}, {"published_at": date(2024, 3, 12)}),
    _ts(
        "TS06",
        "datetime z przesunięciem +02:00",
        {"id": "s", "content": "x", "published_at": "2024-03-12T23:30:00+02:00"},
        {"published_at": date(2024, 3, 12)},
    ),
    _ts("TS07", "obiekt datetime", {"id": "s", "content": "x", "published_at": datetime(2024, 3, 12, 15, 0)}, {"published_at": date(2024, 3, 12)}),
    _ts("TS08", "alias date", {"id": "s", "content": "x", "date": "2024-01-05"}, {"published_at": date(2024, 1, 5)}),
    _ts("TS09", "alias publication_date", {"id": "s", "content": "x", "publication_date": "2024-01-06"}, {"published_at": date(2024, 1, 6)}),
    _ts("TS10", "tytuł jako etykieta", {"id": "s", "content": "x", "title": "PAP"}, {"label": "PAP"}),
    _ts("TS11", "url zachowany", {"id": "s", "content": "x", "url": "https://example.org/a"}, {"url": "https://example.org/a"}),
    _ts("TS12", "brak treści", {"id": "s"}, None),
    _ts("TS13", "brak id", {"content": "x"}, None),
    _ts("TS14", "nieczytelna data", {"id": "s", "content": "x", "published_at": "nie-data-wcale"}, None),
]


# --- MA: build_manipulation_result ------------------------------------------------------------

MA_TEXT = (
    "To skandaliczna zdrada rządu! Przestępczość rośnie: w lutym 2024 było o 15% więcej kradzieży "
    "niż w styczniu. Eksperci twierdzą, że będzie tylko gorzej."
)
MA_SRC = TruthSource(
    id="kgp",
    content="Luty jest co roku miesiącem z wyraźnie wyższą liczbą kradzieży niż styczeń. "
    "W 2023 r. liczba kradzieży spadła o 8%.",
)
EVIDENCE = "Luty jest co roku miesiącem z wyraźnie wyższą liczbą kradzieży niż styczeń."


def frag(**kw: Any) -> dict[str, Any]:
    base: dict[str, Any] = dict(
        quote="skandaliczna zdrada rządu",
        category="EMOTIONAL_LANGUAGE",
        subtype="",
        indicators=[],
        test_answer="",
        explanation="",
        confidence=0.9,
        attribution="author",
        source_id="",
        source_evidence="",
    )
    return {**base, **kw}


def build(*fragments: dict[str, Any]) -> ManipulationResult:
    resp = LLMManipulationResponse.model_validate({"fragments": list(fragments)})
    return build_manipulation_result(MA_TEXT, [MA_SRC], resp)


def _ma(
    cid: str,
    title: str,
    wejscie: str,
    oczekiwane: str,
    fragments: list[dict[str, Any]],
    verify: Callable[[ManipulationResult], bool],
) -> Case:
    def check() -> None:
        r = build(*fragments)
        assert verify(r), r.model_dump()

    return Case(cid, "MA", title, wejscie, oczekiwane, check)


def _ma_empty_text() -> None:
    async def never(*_: Any) -> Any:
        raise AssertionError("LLM nie powinien być wywołany dla pustego tekstu")

    r = asyncio.run(analyze_manipulation("  \n ", [], call=never))
    assert r.fragments == [] and r.score == 0 and r.manipulation_detected is False


_NAMES = {
    "EMOTIONAL_LANGUAGE": "A. Język emocjonalny",
    "FEAR_APPEAL": "B. Straszenie",
    "CONSPIRACY_FRAMING": "C. Sugerowanie spisku",
    "FALSE_URGENCY": "D. Fałszywa pilność",
    "LACK_OF_SOURCE": "E. Brak źródła",
    "EXAGGERATION": "F. Wyolbrzymienie",
    "CHERRY_PICKING": "G. Cherry-picking",
}

MA_CASES = [
    _ma("MA01", "confidence 0.29 → szum", "1 fragment, confidence=0.29", "fragments=[], dropped=0, detected=False",
        [frag(confidence=0.29)], lambda r: r.fragments == [] and r.dropped_fragments == 0 and not r.manipulation_detected),
    _ma("MA02", "confidence 0.3 → zostaje, ale nie przesądza", "confidence=0.3", "1 fragment, detected=False",
        [frag(confidence=0.3)], lambda r: len(r.fragments) == 1 and not r.manipulation_detected),
    _ma("MA03", "confidence 0.49", "confidence=0.49", "1 fragment, detected=False",
        [frag(confidence=0.49)], lambda r: len(r.fragments) == 1 and not r.manipulation_detected),
    _ma("MA04", "confidence 0.5 → wykryto", "confidence=0.5", "detected=True",
        [frag(confidence=0.5)], lambda r: r.manipulation_detected),
    _ma("MA05", "confidence > 1 przycięte", "confidence=1.7", "confidence=1.0",
        [frag(confidence=1.7)], lambda r: r.fragments[0].confidence == 1.0),
    _ma("MA06", "confidence ujemne", "confidence=−0.5", "fragments=[]",
        [frag(confidence=-0.5)], lambda r: r.fragments == []),
    _ma("MA07", "duplikat: zostaje wyższa pewność", "ten sam cytat i kategoria, confidence 0.6 i 0.9", "1 fragment, confidence=0.9",
        [frag(confidence=0.6), frag(confidence=0.9)], lambda r: [f.confidence for f in r.fragments] == [0.9]),
    _ma("MA08", "ten sam cytat, dwie kategorie", "A + F na „skandaliczna zdrada rządu”", "2 wpisy z tym samym zakresem; counts A=1, F=1",
        [frag(), frag(category="EXAGGERATION")],
        lambda r: len(r.fragments) == 2 and r.fragments[0].start == r.fragments[1].start
        and r.counts["EMOTIONAL_LANGUAGE"] == 1 and r.counts["EXAGGERATION"] == 1),
    _ma("MA09", "podtyp wielkimi literami", "LACK_OF_SOURCE, subtype=„UNRELIABLE”", "subtype=unreliable",
        [frag(quote="Eksperci twierdzą", category="LACK_OF_SOURCE", subtype="UNRELIABLE")], lambda r: r.fragments[0].subtype == "unreliable"),
    _ma("MA10", "podtyp ze spacjami", "subtype=„ none ”", "subtype=none",
        [frag(quote="Eksperci twierdzą", category="LACK_OF_SOURCE", subtype=" none ")], lambda r: r.fragments[0].subtype == "none"),
    *[
        _ma(f"MA{11 + i}", f"podtyp {st}", f"LACK_OF_SOURCE, subtype={st}", f"subtype={st}",
            [frag(quote="Eksperci twierdzą", category="LACK_OF_SOURCE", subtype=st)], lambda r, st=st: r.fragments[0].subtype == st)
        for i, st in enumerate(["unverifiable", "inadequate"])
    ],
    _ma("MA13", "nieznany podtyp", "subtype=„foo”", "subtype=None",
        [frag(quote="Eksperci twierdzą", category="LACK_OF_SOURCE", subtype="foo")], lambda r: r.fragments[0].subtype is None),
    _ma("MA14", "podtyp poza kategorią E", "EMOTIONAL_LANGUAGE, subtype=none", "subtype=None",
        [frag(subtype="none")], lambda r: r.fragments[0].subtype is None),
    _ma("MA15", "wskaźniki oczyszczone", "indicators=[„  a ”, „”, „   ”]", "indicators=[„a”]",
        [frag(indicators=["  a ", "", "   "])], lambda r: r.fragments[0].indicators == ["a"]),
    _ma("MA16", "dowód z nieznanego źródła", "source_id=„nie-ma”", "source_evidence=None",
        [frag(category="CHERRY_PICKING", source_id="nie-ma", source_evidence=EVIDENCE)], lambda r: r.fragments[0].source_evidence is None),
    _ma("MA17", "pusty dowód", "source_id=kgp, source_evidence=„”", "source_evidence=None",
        [frag(category="CHERRY_PICKING", source_id="kgp", source_evidence="  ")], lambda r: r.fragments[0].source_evidence is None),
    _ma("MA18", "poprawny dowód", "source_id=kgp, cytat ze źródła", "source_evidence={kgp, cytat}",
        [frag(category="CHERRY_PICKING", source_id="kgp", source_evidence=EVIDENCE)],
        lambda r: r.fragments[0].source_evidence is not None and r.fragments[0].source_evidence.quote == EVIDENCE),
    _ma("MA19", "id źródła ze spacjami", "source_id=„ kgp ”", "source_evidence.source_id=kgp",
        [frag(category="CHERRY_PICKING", source_id=" kgp ", source_evidence=EVIDENCE)],
        lambda r: r.fragments[0].source_evidence is not None and r.fragments[0].source_evidence.source_id == "kgp"),
    _ma("MA20", "dowód innymi literami → oryginał ze źródła", "source_evidence małymi literami", "quote w oryginalnej pisowni źródła",
        [frag(category="CHERRY_PICKING", source_id="kgp", source_evidence=EVIDENCE.lower())],
        lambda r: r.fragments[0].source_evidence is not None and r.fragments[0].source_evidence.quote == EVIDENCE),
    _ma("MA21", "zmyślony dowód", "source_evidence spoza źródła", "fragment zostaje, source_evidence=None",
        [frag(category="CHERRY_PICKING", source_id="kgp", source_evidence="Zmyślony cytat, którego w źródle nie ma wcale.")],
        lambda r: len(r.fragments) == 1 and r.fragments[0].source_evidence is None),
    _ma("MA22", "sortowanie po pozycji", "fragmenty podane od końca tekstu", "rosnąco po start",
        [frag(quote="będzie tylko gorzej", category="FEAR_APPEAL"), frag(quote="Eksperci twierdzą", category="LACK_OF_SOURCE"), frag()],
        lambda r: [f.start for f in r.fragments] == sorted(f.start for f in r.fragments) and r.fragments[0].category == "EMOTIONAL_LANGUAGE"),
    _ma("MA23", "zmyślony cytat odrzucony", "quote spoza tekstu", "fragments=[], dropped_fragments=1",
        [frag(quote="tego nie ma w tekście ani trochę")], lambda r: r.fragments == [] and r.dropped_fragments == 1),
    _ma("MA24", "zmyślony cytat z niską pewnością", "quote spoza tekstu, confidence=0.1", "dropped_fragments=0 (odrzucony wcześniej jako szum)",
        [frag(quote="tego nie ma w tekście ani trochę", confidence=0.1)], lambda r: r.dropped_fragments == 0),
    _ma("MA25", "liczniki dla wszystkich kategorii", "1 fragment A", "counts ma 7 kluczy A–G, suma = 1",
        [frag()], lambda r: set(r.counts) == set(CATEGORY_CODES) and sum(r.counts.values()) == 1),
    *[
        _ma(f"MA{26 + i}", f"nazwa kategorii {code}", f"category={code}", f"category_name zaczyna się od „{name}”",
            [frag(category=code)], lambda r, name=name: r.fragments[0].category_name.startswith(name))
        for i, (code, name) in enumerate(_NAMES.items())
    ],
    _ma("MA33", "atrybucja quoted zachowana", "attribution=quoted", "attribution=quoted",
        [frag(attribution="quoted")], lambda r: r.fragments[0].attribution == "quoted"),
    _ma("MA34", "cytat innymi literami → tekst oryginału", "quote=„SKANDALICZNA ZDRADA RZĄDU”", "quote=„skandaliczna zdrada rządu”, start=3",
        [frag(quote="SKANDALICZNA ZDRADA RZĄDU")], lambda r: r.fragments[0].quote == "skandaliczna zdrada rządu" and r.fragments[0].start == 3),
    _ma("MA35", "pola tekstowe oczyszczone", "explanation/test_answer ze spacjami", "bez spacji na brzegach",
        [frag(explanation="  zdanie. ", test_answer="\tnie.\n")], lambda r: (r.fragments[0].explanation, r.fragments[0].test_answer) == ("zdanie.", "nie.")),
    _ma("MA36", "tekst neutralny", "fragments=[]", "detected=False, score=0, wszystkie liczniki 0",
        [], lambda r: not r.manipulation_detected and r.score == 0 and set(r.counts.values()) == {0}),
    _ma("MA37", "cytat cudzy z wysoką pewnością nadal wykryty", "attribution=quoted, confidence=0.9", "detected=True",
        [frag(attribution="quoted")], lambda r: r.manipulation_detected),
    _ma("MA38", "offsety zgodne z tekstem", "4 różne fragmenty", "text[start:end] == quote dla każdego",
        [frag(), frag(quote="Przestępczość rośnie", category="CHERRY_PICKING"), frag(quote="Eksperci twierdzą", category="LACK_OF_SOURCE"),
         frag(quote="będzie tylko gorzej", category="FEAR_APPEAL")],
        lambda r: len(r.fragments) == 4 and all(MA_TEXT[f.start : f.end] == f.quote for f in r.fragments)),
    Case("MA39", "MA", "pusty tekst nie wywołuje LLM", "analyze_manipulation(„  \\n ”) z atrapą, która rzuca wyjątek",
         "fragments=[], score=0, bez wywołania LLM", _ma_empty_text),
]


# --- SC: score_fragments ----------------------------------------------------------------------


def _mf(conf: float = 1.0, attribution: str = "author") -> ManipulationFragment:
    return ManipulationFragment(
        quote="x", start=0, end=1, category="EMOTIONAL_LANGUAGE", category_name="A",
        confidence=conf, attribution=attribution,
    )  # fmt: skip


def _sc(cid: str, title: str, words: int, frags: list[ManipulationFragment], exp: int) -> Case:
    text = " ".join(["słowo"] * words)

    def check() -> None:
        assert score_fragments(text, frags) == exp

    desc = ", ".join(f"{f.confidence}/{f.attribution}" for f in frags) or "brak"
    return Case(cid, "SC", title, f"{words} słów; fragmenty: {desc}", str(exp), check)


SC_CASES = [
    _sc("SC01", "brak fragmentów", 10, [], 0),
    _sc("SC02", "1 fragment autora", 10, [_mf()], 28),
    _sc("SC03", "1 cytat cudzy (waga 0.5)", 10, [_mf(attribution="quoted")], 15),
    _sc("SC04", "1 fragment z pewnością 0.5", 10, [_mf(0.5)], 15),
    _sc("SC05", "3 fragmenty", 10, [_mf()] * 3, 63),
    _sc("SC06", "1 fragment w 100 słowach", 100, [_mf()], 28),
    _sc("SC07", "1 fragment w 200 słowach", 200, [_mf()], 15),
    _sc("SC08", "1 fragment w 300 słowach", 300, [_mf()], 11),
    _sc("SC09", "10 fragmentów", 10, [_mf()] * 10, 96),
    _sc("SC10", "2 autora + 2 cudze", 10, [_mf(), _mf(), _mf(attribution="quoted"), _mf(attribution="quoted")], 63),
    _sc("SC11", "nasycenie przy 30 fragmentach", 10, [_mf()] * 30, 100),
    _sc("SC12", "pusty tekst z fragmentem", 0, [_mf()], 28),
]


# --- PR: prompty ------------------------------------------------------------------------------


def _pr(cid: str, title: str, wejscie: str, oczekiwane: str, fn: Callable[[], None]) -> Case:
    return Case(cid, "PR", title, wejscie, oczekiwane, fn)


def _pr_no_sources() -> None:
    assert render_sources([]) == "(brak źródeł prawdy)"


def _pr_attrs() -> None:
    s = TruthSource(id="s1", title="PAP", url="https://example.org", content="treść", published_at=date(2024, 3, 12))
    out = render_sources([s])
    assert out.startswith('<zrodlo id="s1" tytul="PAP" data_publikacji="2024-03-12" url="https://example.org">')
    assert "treść" in out and out.endswith("</zrodlo>")


def _pr_truncate() -> None:
    s = TruthSource(id="s", content="a" * (MAX_SOURCE_CHARS + 500) + "KONIEC")
    out = render_sources([s])
    assert "KONIEC" not in out and "a" * MAX_SOURCE_CHARS in out



def _pr_total_budget() -> None:
    sources = [TruthSource(id=f"s{i}", content="b" * 10_000 + "KONIEC") for i in range(15)]
    out = render_sources(sources)
    assert out.count("<zrodlo") == 15 and "KONIEC" not in out
    assert out.count("b") <= MAX_TOTAL_SOURCE_CHARS

def _pr_date() -> None:
    out = manipulation_user("Tekst.", [], date(2024, 4, 1))
    assert "Data publikacji tekstu: 2024-04-01" in out and "<tekst>\nTekst.\n</tekst>" in out


def _pr_no_date() -> None:
    assert "Data publikacji tekstu: nieznana" in manipulation_user("Tekst.", [], None)


PR_CASES = [
    _pr("PR01", "brak źródeł", "render_sources([])", "„(brak źródeł prawdy)”", _pr_no_sources),
    _pr("PR02", "atrybuty źródła", "źródło z id, tytułem, datą i url", '<zrodlo id="s1" tytul="PAP" data_publikacji="2024-03-12" url=…>', _pr_attrs),
    _pr("PR03", "przycinanie długich źródeł", f"treść {MAX_SOURCE_CHARS + 506} znaków", f"pierwsze {MAX_SOURCE_CHARS} znaków, bez końcówki", _pr_truncate),
    _pr("PR06", "łączny budżet źródeł", "15 źródeł po 10 000 znaków", f"razem najwyżej {MAX_TOTAL_SOURCE_CHARS} znaków treści, każde źródło obecne", _pr_total_budget),
    _pr("PR04", "data tekstu w nagłówku", "article_date=2024-04-01", "„Data publikacji tekstu: 2024-04-01” + <tekst>…</tekst>", _pr_date),
    _pr("PR05", "nieznana data tekstu", "article_date=None", "„Data publikacji tekstu: nieznana …”", _pr_no_date),
]


# --- PI: pipeline -----------------------------------------------------------------------------

PI_TEXT = "To skandaliczna zdrada rządu! Eksperci twierdzą, że będzie gorzej."
_EMPTY_DATES = LLMDatesResponse(article_date_in_text="", text_category="other", recency_framing=0.0, dates=[])


def _fake(seen: list[tuple[str, type]] | None = None) -> Callable[..., Any]:
    async def call(system: str, user: str, schema: type) -> Any:
        if seen is not None:
            seen.append((user, schema))
        if schema is LLMManipulationResponse:
            return LLMManipulationResponse.model_validate({"fragments": [frag()]})
        return _EMPTY_DATES

    return call


def _pi_sync() -> None:
    r = analyze(PI_TEXT, [], date(2024, 4, 1), call=_fake())
    assert r.manipulation.counts["EMOTIONAL_LANGUAGE"] == 1 and r.dates.article_date == date(2024, 4, 1)


def _pi_in_loop() -> None:
    async def inner() -> None:
        with pytest.raises(RuntimeError, match="analyze_async"):
            analyze(PI_TEXT, [], call=_fake())

    asyncio.run(inner())


def _pi_none_sources() -> None:
    r = analyze(PI_TEXT, None, call=_fake())
    assert any(s.reason == "brak źródeł prawdy" for s in r.dates.skipped_checks)


def _pi_dict_sources() -> None:
    seen: list[tuple[str, type]] = []
    analyze(PI_TEXT, [{"source_id": "kgp", "body": "Dane KGP.", "date": "2024-03-01"}], call=_fake(seen))
    assert all('<zrodlo id="kgp" data_publikacji="2024-03-01">' in user for user, _ in seen)


def _pi_both_calls() -> None:
    seen: list[tuple[str, type]] = []
    analyze(PI_TEXT, [], call=_fake(seen))
    assert {schema for _, schema in seen} == {LLMManipulationResponse, LLMDatesResponse}


def _pi_error() -> None:
    async def failing(*_: Any) -> Any:
        raise LLMError("awaria")

    with pytest.raises(LLMError):
        analyze(PI_TEXT, [], call=failing)


def _pi_empty() -> None:
    seen: list[tuple[str, type]] = []
    r = asyncio.run(analyze_async("", [], call=_fake(seen)))
    assert seen == [] and not r.manipulation.manipulation_detected and r.dates.dates_consistent


def _pi_serializable() -> None:
    r = analyze(PI_TEXT, [], date(2024, 4, 1), call=_fake())
    dumped = r.model_dump(mode="json")
    assert set(dumped) == {"manipulation", "dates"} and dumped["dates"]["article_date"] == "2024-04-01"


PI_CASES = [
    Case("PI01", "PI", "synchroniczne analyze()", "analyze(tekst, [], 2024-04-01, atrapa)", "counts[A]=1, article_date=2024-04-01", _pi_sync),
    Case("PI02", "PI", "analyze() w pętli zdarzeń", "analyze() wywołane wewnątrz asyncio.run", "RuntimeError „…użyj await analyze_async()”", _pi_in_loop),
    Case("PI03", "PI", "sources=None", "analyze(tekst, None)", "działa; skipped: brak źródeł prawdy", _pi_none_sources),
    Case("PI04", "PI", "źródła jako słowniki z aliasami", "{source_id, body, date}", "oba prompty zawierają <zrodlo id=\"kgp\" data_publikacji=\"2024-03-01\">", _pi_dict_sources),
    Case("PI05", "PI", "dwa wywołania LLM", "analyze(tekst)", "wywołano schematy LLMManipulationResponse i LLMDatesResponse", _pi_both_calls),
    Case("PI06", "PI", "błąd LLM", "atrapa rzuca LLMError", "LLMError propagowany do wywołującego", _pi_error),
    Case("PI07", "PI", "pusty tekst", "analyze_async(„”)", "0 wywołań LLM, wynik neutralny", _pi_empty),
    Case("PI08", "PI", "wynik serializowalny do JSON", "model_dump(mode=json)", "klucze manipulation, dates; daty jako ISO", _pi_serializable),
]
