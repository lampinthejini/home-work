"""코딩테스트 문제 목록 (COD-02): 문제 자체가 맞는지, 지원 건마다 기초 1 · 응용 1 을 고르는지 확인한다."""

import ast
import json
import uuid
from collections import Counter
from pathlib import Path

import pytest
from test_evaluation import makeApplication

from app.domain import status as st
from app.interview import lifecycle
from app.models import Application, CodingSubmission
from app.services import coding, coding_bank

SOLUTIONS = json.loads((Path(__file__).parent / "coding_solutions.json").read_text(encoding="utf-8"))
ALL_KEYS = sorted(coding_bank.PROBLEMS)


def runCase(code: str, args: str) -> str:
    """실행 상자와 같은 방식으로 돌리고 비교한다 (sandbox_runner)."""
    namespace: dict = {}
    exec(code, namespace)  # noqa: S102 — 테스트에 넣어 둔 모범 답안과 시작 코드만 돌린다
    return repr(eval(f"solution({args})", {"solution": namespace["solution"]}))  # noqa: S307


def expectedRepr(expected: str) -> str:
    return repr(ast.literal_eval(expected))


def test_everyProblemHasReferenceSolution():
    assert sorted(SOLUTIONS) == ALL_KEYS


@pytest.mark.parametrize("key", ALL_KEYS)
def test_referenceSolutionPassesEveryCase(key):
    problem = coding_bank.PROBLEMS[key]
    for args, expected in problem["examples"] + problem["hidden"]:
        assert runCase(SOLUTIONS[key], args) == expectedRepr(expected), (key, args)


@pytest.mark.parametrize("key", ALL_KEYS)
def test_starterCodeDoesNotPassEveryHiddenCase(key):
    problem = coding_bank.PROBLEMS[key]
    results = [runCase(problem["starter"], args) == expectedRepr(expected) for args, expected in problem["hidden"]]
    assert not all(results), key


@pytest.mark.parametrize("key", ALL_KEYS)
def test_problemShape(key):
    problem = coding_bank.PROBLEMS[key]
    assert len(key) <= 32  # coding_submissions.problem_key
    assert problem["level"] in ("기초", "응용")
    assert problem["starter"].startswith(problem["signature"])
    assert len(problem["examples"]) >= 2
    assert len(problem["hidden"]) >= 5
    # 결과 repr 은 상자에서 10000자로 잘린다
    for args, expected in problem["examples"] + problem["hidden"]:
        assert len(runCase(SOLUTIONS[key], args)) < 10000, (key, args)
        assert len(expected) < 10000


def test_levelsAreBalanced():
    assert Counter(p["level"] for p in coding_bank.PROBLEMS.values()) == {"기초": 5, "응용": 5}


def test_pickGivesOneOfEachLevelInOrder():
    for _ in range(50):
        basic, applied = coding_bank.pickProblems(str(uuid.uuid4()))
        assert coding_bank.PROBLEMS[basic]["level"] == "기초"
        assert coding_bank.PROBLEMS[applied]["level"] == "응용"


def test_pickIsStableForSameApplication():
    applicationId = str(uuid.uuid4())
    assert coding_bank.pickProblems(applicationId) == coding_bank.pickProblems(applicationId)


def test_pickUsesEveryProblem():
    picked = Counter(key for _ in range(500) for key in coding_bank.pickProblems(str(uuid.uuid4())))
    assert sorted(picked) == ALL_KEYS


def test_enterCodingStoresPickedProblemsAndViewsFollowThem(sessionFactory):
    appId = makeApplication(sessionFactory, status=st.INTERVIEWING)
    with sessionFactory() as db:
        app = db.get(Application, appId)
        lifecycle.enterCoding(db, app)
        rows = db.query(CodingSubmission).filter_by(application_id=appId).order_by(CodingSubmission.problem_no).all()
        assert [r.problem_key for r in rows] == coding_bank.pickProblems(appId)
        assert rows[0].code == coding_bank.PROBLEMS[rows[0].problem_key]["starter"]
        views = coding.problemViews(db, app)
        assert [v["title"] for v in views] == [coding_bank.PROBLEMS[r.problem_key]["title"] for r in rows]


def test_alreadyAssignedProblemIsKept(sessionFactory):
    """목록이 바뀌어도 이미 배정한 문제는 그대로 쓴다. 지원 번호로 다시 고르지 않는다."""
    appId = makeApplication(sessionFactory, status=st.INTERVIEWING)
    with sessionFactory() as db:
        app = db.get(Application, appId)
        lifecycle.enterCoding(db, app)
        row = db.query(CodingSubmission).filter_by(application_id=appId, problem_no=1).one()
        other = next(k for k, p in coding_bank.PROBLEMS.items() if p["level"] == "기초" and k != row.problem_key)
        row.problem_key = other
        db.commit()
        views = coding.problemViews(db, app)
        assert views[0]["title"] == coding_bank.PROBLEMS[other]["title"]
