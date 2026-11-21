import json
import typing

from prawdowid_analysis.schemas import ModelVerdictValue
from scripts.eval_verdict import CASES_FILE


def test_eval_cases_are_well_formed():
    cases = json.loads(CASES_FILE.read_text(encoding="utf-8"))
    allowed = set(typing.get_args(ModelVerdictValue))
    ids = [c["id"] for c in cases]
    assert len(ids) == len(set(ids))
    assert {c["expected"] for c in cases} == allowed, "każdy werdykt ma przypadek testowy"
    assert all(c["claim"].strip() for c in cases)
