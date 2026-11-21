"""Przypadki na żywo z prawdziwym LLM (uruchamiane tylko przy RUN_LLM_TESTS=1 i uzupełnionym .env)."""

from __future__ import annotations

from collections.abc import Callable

from inputDataAnalysis import AnalysisResult, analyze
from inputDataAnalysis.__main__ import EXAMPLES

from .case_base import Case


def _run(name: str) -> AnalysisResult:
    ex = EXAMPLES[name]
    return analyze(ex["text"], ex["sources"], ex.get("article_date"))


def _cat(name: str, code: str) -> Callable[[], None]:
    def check() -> None:
        r = _run(name)
        assert r.manipulation.counts[code] >= 1, r.manipulation.counts
        assert r.manipulation.manipulation_detected

    return check


def _neutral() -> None:
    r = _run("neutralny")
    assert r.manipulation.fragments == [] and r.manipulation.score == 0
    assert r.dates.dates_consistent and r.dates.issues == []


def _cherry() -> None:
    r = _run("G_cherry_picking")
    cherry = [f for f in r.manipulation.fragments if f.category == "CHERRY_PICKING"]
    assert cherry and any(f.source_evidence for f in cherry)


def _old_news() -> None:
    r = _run("stary_news_jako_nowy")
    codes = {i.code for i in r.dates.issues}
    assert "OUTDATED_AS_CURRENT" in codes and "INTERNAL_INCONSISTENCY" in codes
    assert r.dates.dates_consistent is False


def _live(cid: str, name: str, ocz: str, fn: Callable[[], None]) -> Case:
    return Case(cid, "LV", f"przykład „{name}”", f"EXAMPLES[{name!r}] → prawdziwy LLM", ocz, fn)


LV_CASES = [
    _live("LV01", "A_emocje", "counts[EMOTIONAL_LANGUAGE] ≥ 1, detected=True", _cat("A_emocje", "EMOTIONAL_LANGUAGE")),
    _live("LV02", "B_straszenie", "counts[FEAR_APPEAL] ≥ 1", _cat("B_straszenie", "FEAR_APPEAL")),
    _live("LV03", "C_spisek", "counts[CONSPIRACY_FRAMING] ≥ 1", _cat("C_spisek", "CONSPIRACY_FRAMING")),
    _live("LV04", "D_pilnosc", "counts[FALSE_URGENCY] ≥ 1", _cat("D_pilnosc", "FALSE_URGENCY")),
    _live("LV05", "E_brak_zrodla", "counts[LACK_OF_SOURCE] ≥ 1", _cat("E_brak_zrodla", "LACK_OF_SOURCE")),
    _live("LV06", "F_wyolbrzymienie", "counts[EXAGGERATION] ≥ 1", _cat("F_wyolbrzymienie", "EXAGGERATION")),
    _live("LV07", "G_cherry_picking", "CHERRY_PICKING z source_evidence", _cherry),
    _live("LV08", "neutralny", "0 fragmentów, score=0, dates_consistent=True, 0 problemów", _neutral),
    _live("LV09", "stary_news_jako_nowy", "OUTDATED_AS_CURRENT + INTERNAL_INCONSISTENCY, dates_consistent=False", _old_news),
]
