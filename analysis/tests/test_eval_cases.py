import json
import typing

from prawdowid_analysis.schemas import ModelVerdictValue
from scripts.eval_verdict import CASES_FILE, accepted, fact_check_sources, user_sources

ALLOWED = set(typing.get_args(ModelVerdictValue))


def load_cases():
    return json.loads(CASES_FILE.read_text(encoding="utf-8"))


def test_eval_cases_are_well_formed():
    cases = load_cases()
    ids = [c["id"] for c in cases]
    assert len(ids) == len(set(ids))
    assert {c["expected"] for c in cases} == ALLOWED, "każdy werdykt ma przypadek testowy"
    for case in cases:
        assert case["claim"].strip(), case["id"]
        assert accepted(case) <= ALLOWED, case["id"]
        assert not accepted(case) & set(case.get("forbidden", [])), case["id"]


def test_eval_case_sources_build():
    for case in load_cases():
        for source in user_sources(case):
            assert source.kind == "uzytkownik"
        for source in fact_check_sources(case):
            assert source.kind == "fact_check" and source.rating
