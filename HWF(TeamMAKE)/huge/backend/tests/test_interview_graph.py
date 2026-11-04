"""면접 진행 그래프의 순서·갈림길 (ADR-07). 실제 일은 가짜 러너가 기록만 한다."""

import asyncio
import sys

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from app.interview import graph

# LangGraph 의 interrupt 는 Python 3.11 이상에서만 비동기 노드 안의 실행 문맥을 찾는다 (서버 이미지는 3.11).
# 3.10 에서 돌리면 건너뛴다: 백엔드 이미지에서 `python -m pytest tests/test_interview_graph.py` 로 확인
needsPy311 = pytest.mark.skipif(sys.version_info < (3, 11), reason="LangGraph interrupt 는 Python 3.11 이상 필요")


class FakeRunner:
    def __init__(self, followupSeqs=(), totalLimit=4, decide=None):
        self.seq = 1
        self.answered: set[str] = set()
        self.followups: dict[int, str] = {}
        self.followupSeqs = set(followupSeqs)
        self.totalLimit = totalLimit
        self.decideOut = decide or (lambda seq: {"reasonCode": "vague", "question": f"{seq}번 답변을 더 구체적으로 말씀해 주시겠어요?"})
        self.log: list[str] = []
        self.finished = False

    async def prepareQuestions(self):
        self.log.append("prepare")

    def locate(self):
        if self.seq > 10:
            return {"seq": self.seq, "rowId": None, "kind": None}
        base = f"b{self.seq}"
        if base not in self.answered:
            return {"seq": self.seq, "rowId": base, "kind": "base"}
        fid = self.followups.get(self.seq)
        if fid and fid not in self.answered:
            return {"seq": self.seq, "rowId": fid, "kind": "follow_up"}
        return {"seq": self.seq, "rowId": None, "kind": None}

    def advance(self, seq):
        self.seq = seq + 1

    async def beginQuestion(self, rowId):
        self.log.append(f"ask:{rowId}")

    async def finishAnswer(self, rowId, endReason):
        self.answered.add(rowId)
        self.log.append(f"answer:{rowId}:{endReason}")
        return {"answeredAt": 0.0, "sttSec": 1.0}

    def followupPreflight(self, rowId, answeredAt):
        seq = int(rowId[1:])
        if len(self.followups) >= self.totalLimit:
            return "total_limit"
        return None if seq in self.followupSeqs else "empty_answer"

    async def followupDecide(self, rowId, answeredAt):
        return self.decideOut(int(rowId[1:]))

    async def createFollowup(self, rowId, reasonCode, question, answeredAt):
        seq = int(rowId[1:])
        self.followups[seq] = f"f{seq}"
        return f"f{seq}"

    async def finishInterview(self):
        self.finished = True


async def runAll(runner: FakeRunner, saver=None, stopAfter: int | None = None):
    compiled = graph.buildInterviewGraph(runner, saver or InMemorySaver())
    config = graph.graphConfig("app-1")
    result = await compiled.ainvoke({"seq": 0}, config)
    waits = 0
    while result.get("__interrupt__"):
        waits += 1
        if stopAfter is not None and waits > stopAfter:
            return waits
        result = await compiled.ainvoke(Command(resume="done"), config)
    return waits


@needsPy311
def test_tenQuestionsWithFollowupsThenFinish():
    runner = FakeRunner(followupSeqs={2, 5})
    waits = asyncio.run(runAll(runner))
    assert waits == 12 and runner.finished
    asks = [entry for entry in runner.log if entry.startswith("ask:")]
    assert asks[:4] == ["ask:b1", "ask:b2", "ask:f2", "ask:b3"]
    assert "ask:f5" in asks and asks[-1] == "ask:b10"


@needsPy311
def test_followupLimitIsCountedAcrossInterview():
    runner = FakeRunner(followupSeqs=set(range(1, 11)), totalLimit=4)
    waits = asyncio.run(runAll(runner))
    assert waits == 14 and len(runner.followups) == 4  # 본질문 10 + 꼬리질문 4 (RECURSION_LIMIT 안에서 끝까지)


@needsPy311
def test_invalidFollowupIsSkippedWithoutStopping():
    runner = FakeRunner(followupSeqs={1, 2, 3}, decide=lambda seq: (
        {"reasonCode": "none", "question": ""} if seq == 1 else
        {"reasonCode": "vague", "question": "결혼은 하셨나요?"} if seq == 2 else
        {"skipCause": "llm:timeout"}))
    waits = asyncio.run(runAll(runner))
    assert waits == 10 and runner.followups == {} and runner.finished


@needsPy311
def test_newConnectionResumesFromLedger():
    # 첫 연결은 3번 질문을 기다리다 끊김 → 새 연결은 원장을 읽어 3번부터 다시 (같은 thread_id)
    runner = FakeRunner()
    saver = InMemorySaver()
    asyncio.run(runAll(runner, saver, stopAfter=2))
    assert runner.answered == {"b1", "b2"}
    runner.log.clear()
    asyncio.run(runAll(runner, saver))
    assert runner.log[1] == "ask:b3" and runner.finished


def test_validateFollowup():
    assert graph.validateFollowup("none", "어떤 방법을 쓰셨나요?") == "not_needed"
    assert graph.validateFollowup("vague", "짧다?") == "invalid_length"
    assert graph.validateFollowup("vague", "どの方法を使いましたか?") == "invalid_language"
    assert graph.validateFollowup("vague", "부모님은 어떤 일을 하시나요?") == "forbidden_topic"
    assert graph.validateFollowup("vague", "그때 데이터 전처리는 구체적으로 어떻게 하셨나요?") is None
