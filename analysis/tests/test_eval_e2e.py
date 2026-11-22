import json

from scripts.eval_e2e import compute, judge, read_log


def reply(status, body):
    return {"status": status, "seconds": 1.0, "request_id": "r1", "body": body}


RESULT = {
    "status": "result",
    "claims": [
        {"verdict": "false", "sources": [{"quote": "cytat", "url": "https://gov.pl/x"}]},
        {"verdict": "confirmed", "sources": [{"quote": "inny", "url": None}]},
        {"verdict": "insufficient"},
    ],
}


def test_judge_result_counts_sources_and_expectations():
    case = {"expected": ["false", "confirmed", "insufficient"], "forbidden": ["misleading"]}
    j = judge(case, reply(200, RESULT))
    assert j["outcome"] == "wynik"
    assert j["ok"] is True and not j["forbidden_hit"]
    assert j["decisive_claims"] == 2 and j["decisive_with_source"] == 1
    assert j["sources_without_url"] == 1


def test_judge_technical_error_is_not_a_verdict():
    body = {"error": {"code": "analysis_failed", "message": "x"}, "claims": [{"verdict": "false"}]}
    j = judge({"expected": ["false"]}, reply(502, body))
    assert j["outcome"] == "techniczny"
    assert j["verdicts"] == [] and j["ok"] is False
    assert j["error_code"] == "analysis_failed"


def test_read_log_joins_summary_and_injection_by_request_id(tmp_path):
    log = tmp_path / "app.jsonl"
    lines = [
        {"event": "prompt_injection", "request_id": "r1"},
        {
            "event": "request_summary",
            "request_id": "r1",
            "llm_calls": 4,
            "prompt_tokens": 10,
            "completion_tokens": 5,
            "abstained": False,
        },
        {"event": "request_summary", "request_id": "other", "llm_calls": 9},
    ]
    log.write_text("\n".join(json.dumps(x) for x in lines), encoding="utf-8")
    found = read_log(log, {"r1"})
    assert found["r1"]["llm_calls"] == 4 and found["r1"]["injection_events"] == 1


def test_compute_flags_results_in_expect_technical_mode():
    row = {
        "id": "T01",
        "scenario": "J",
        "kind": "text",
        "seconds": 2.0,
        **judge({}, reply(200, RESULT)),
    }
    row["log"] = {"prompt_tokens": 100, "completion_tokens": 20, "llm_calls": 3}
    m = compute([row], expect_technical=True)
    assert m["technical_violations"] == ["T01"]
    assert m["tokens_per_1000_requests"] == 120_000
    assert m["citation_coverage_live"] == {"hits": 1, "total": 2}
