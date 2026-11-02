"""상자 밖 채점 비교 (채점 위조 방지)."""

from app.services.sandbox_runner import judge

CASES = [("1, 2", "3"), ("'a', 'b'", "'ab'")]


def testCorrectResultsPass():
    raw = {"status": "ran", "results": [{"no": 1, "actual": "3", "stderr": ""}, {"no": 2, "actual": "'ab'", "stderr": ""}]}
    result = judge(raw, CASES)
    assert result["status"] == "ok"
    assert [r["passed"] for r in result["results"]] == [True, True]


def testForgedPassedFlagIsIgnored():
    # 지원자 코드가 passed=True 를 찍어도 실제 값이 다르면 통과가 아니다
    raw = {"status": "ok", "results": [{"no": 1, "passed": True, "actual": "4"}, {"no": 2, "passed": True, "actual": "'x'"}]}
    assert [r["passed"] for r in judge(raw, CASES)["results"]] == [False, False]


def testMissingResultsAreRuntimeError():
    result = judge({"status": "ran", "results": [{"no": 1, "actual": "3", "stderr": ""}]}, CASES)
    assert result["status"] == "runtime_error"
    assert [r["passed"] for r in result["results"]] == [True, False]


def testMalformedOutputIsRejected():
    assert judge({"status": "ran", "results": "all passed"}, CASES)["status"] == "runtime_error"
    assert judge({"status": "ran", "results": [{}] * 5}, CASES)["status"] == "runtime_error"


def testSyntaxErrorPassesThrough():
    result = judge({"status": "syntax_error", "error": "invalid syntax (line 1)"}, CASES)
    assert result["status"] == "syntax_error" and result["error"]
