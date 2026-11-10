"""면접 진행 그래프 (ADR-07, TRD 7-5, AI 아키텍처 6.1·6.2).

  prepare → locate ─┬─ ask → wait(interrupt) → transcribe ─┬─ (본질문) followup ─┬─ queue_followup → ask
                    │                                        │                    └─ advance
                    │                                        └─ (꼬리질문) advance → locate
                    ├─ advance → locate
                    └─ finish (10개 끝 → 코딩테스트 또는 완료)

꼬리질문 판단은 하위 그래프다: preflight(한도·시간·무응답 규칙, LLM 안 부름) → decide(T4, RT 레인)
→ validate(형식·금지 표현) → create(저장 + TTS). 어느 단계든 안 되면 면접을 멈추지 않고 SKIP 한다.

그래프는 순서와 갈림길만 정한다. 질문 보내기·답변 받기·STT·저장 같은 실제 일은 LiveSession 이 한다.
'답변 기다리기'는 interrupt 로 그래프를 멈추고, LiveSession 이 답변이 끝나면 Command(resume=끝난 이유)로 잇는다.
상태 원장은 applications 이므로 새 연결(이어가기)마다 locate 가 DB 를 읽어 끊긴 질문부터 다시 낸다.
"""

import logging
import re
from typing import Protocol, TypedDict

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from ..domain import question_text
from ..services.posting_draft import BIAS_RULES

log = logging.getLogger("huge.interview.graph")

# 질문 하나에 6~9 단계 × (본질문 10 + 꼬리질문 4) + 여유. 기본값 25 로는 끝까지 못 간다
RECURSION_LIMIT = 400
FOLLOWUP_MAX_CHARS = 120  # 지시문은 80자 이내로 쓰게 하고, 조금 넘는 것은 받는다
FOREIGN_SCRIPT = re.compile(r"[぀-ヿ一-鿿]")
PERSONAL_TOPIC = re.compile(r"종교|정치|가족\s*관계|부모님|연애|임신|출산|건강\s*상태|병력")


class Runner(Protocol):
    """LiveSession 이 그래프에 내주는 일."""

    async def prepareQuestions(self) -> None: ...
    def locate(self) -> dict: ...
    def advance(self, seq: int) -> None: ...
    async def beginQuestion(self, rowId: str) -> None: ...
    async def finishAnswer(self, rowId: str, endReason: str) -> dict: ...
    def followupPreflight(self, rowId: str, answeredAt: float) -> str | None: ...
    async def followupDecide(self, rowId: str, answeredAt: float) -> dict: ...
    async def createFollowup(self, rowId: str, reasonCode: str, question: str, answeredAt: float) -> str: ...
    async def finishInterview(self) -> None: ...


class InterviewState(TypedDict, total=False):
    seq: int
    rowId: str | None       # 지금 낼 질문(interview_questions.id)
    kind: str | None        # base · follow_up
    endReason: str          # done · timeout
    answeredAt: float       # 답변이 끝난 시각 (time.monotonic, 같은 프로세스 안에서만 씀)
    followupId: str | None
    skipCause: str | None


class FollowupState(TypedDict, total=False):
    seq: int
    rowId: str
    answeredAt: float
    followupId: str | None
    skipCause: str | None
    reasonCode: str
    question: str


def validateFollowup(reasonCode: str, question: str) -> str | None:
    """꼬리질문 검증 (AI 아키텍처 T4: INVALID 면 SKIP). 문제 코드, 맞으면 None."""
    if reasonCode == "none":
        return "not_needed"
    text = question_text.cleanQuestion(question)
    if not 8 <= len(text) <= FOLLOWUP_MAX_CHARS or "\n" in text:
        return "invalid_length"
    if not re.search(r"[가-힣]", text) or FOREIGN_SCRIPT.search(text):
        return "invalid_language"
    if any(pattern.search(text) for pattern, _ in BIAS_RULES) or PERSONAL_TOPIC.search(text):
        return "forbidden_topic"  # 차별·사적 질문 금지 (AI 아키텍처 fq-1)
    # 본질문과 같은 글 검사: 찌꺼기·답변 방식 지시·여러 개 묻기 (2026-11-10). 길이는 위 FOLLOWUP_MAX_CHARS 로 따로 본다
    problem = question_text.textProblem(text)
    return problem if problem != "too_long" else None


def buildFollowupGraph(runner: Runner):
    async def preflight(state: FollowupState) -> dict:
        return {"skipCause": runner.followupPreflight(state["rowId"], state["answeredAt"]), "followupId": None}

    async def decide(state: FollowupState) -> dict:
        out = await runner.followupDecide(state["rowId"], state["answeredAt"])
        return {"skipCause": out.get("skipCause"), "reasonCode": out.get("reasonCode", "none"),
                "question": question_text.cleanQuestion(out.get("question", ""))}

    async def validate(state: FollowupState) -> dict:
        return {"skipCause": validateFollowup(state.get("reasonCode", "none"), state.get("question", ""))}

    async def create(state: FollowupState) -> dict:
        followupId = await runner.createFollowup(state["rowId"], state["reasonCode"], state["question"].strip(),
                                                 state["answeredAt"])
        return {"followupId": followupId}

    async def skip(state: FollowupState) -> dict:
        # 사유만 남긴다 (답변·질문 글은 로그에 넣지 않음)
        log.info("followup skipped seq=%s: %s reason=%s", state.get("seq"), state.get("skipCause"), state.get("reasonCode"))
        return {"followupId": None}

    def nextOr(target: str):
        return lambda state: "skip" if state.get("skipCause") else target

    g = StateGraph(FollowupState)
    g.add_node("preflight", preflight)
    g.add_node("decide", decide)
    g.add_node("validate", validate)
    g.add_node("create", create)
    g.add_node("skip", skip)
    g.add_edge(START, "preflight")
    g.add_conditional_edges("preflight", nextOr("decide"), ["decide", "skip"])
    g.add_conditional_edges("decide", nextOr("validate"), ["validate", "skip"])
    g.add_conditional_edges("validate", nextOr("create"), ["create", "skip"])
    g.add_edge("create", END)
    g.add_edge("skip", END)
    return g.compile()


def buildInterviewGraph(runner: Runner, checkpointer: BaseCheckpointSaver | None):
    async def prepare(_state: InterviewState) -> dict:
        await runner.prepareQuestions()
        return {}

    async def locate(_state: InterviewState) -> dict:
        return runner.locate()

    async def ask(state: InterviewState) -> dict:
        await runner.beginQuestion(state["rowId"])
        return {}

    async def wait(state: InterviewState) -> dict:
        # 그래프를 멈추고 답변이 끝나기를 기다린다. 이어서 실행되면 이 노드가 처음부터 다시 돌고 interrupt 가 값을 돌려준다.
        # Python 3.11 이상이 필요하다: 3.10 에서는 interrupt 가 실행 문맥을 찾지 못한다 (LangGraph 제약, 이미지는 3.11)
        endReason = interrupt({"seq": state.get("seq"), "kind": state.get("kind")})
        return {"endReason": endReason}

    async def transcribe(state: InterviewState) -> dict:
        out = await runner.finishAnswer(state["rowId"], state.get("endReason", "done"))
        return {"answeredAt": out["answeredAt"]}

    async def queueFollowup(state: InterviewState) -> dict:
        return {"rowId": state["followupId"], "kind": "follow_up", "followupId": None}

    async def advance(state: InterviewState) -> dict:
        runner.advance(state["seq"])
        return {"rowId": None, "kind": None, "followupId": None}

    async def finish(_state: InterviewState) -> dict:
        await runner.finishInterview()
        return {}

    def afterLocate(state: InterviewState) -> str:
        if state.get("seq", 0) > 10:
            return "finish"
        return "ask" if state.get("rowId") else "advance"

    def afterTranscribe(state: InterviewState) -> str:
        return "followup" if state.get("kind") == "base" else "advance"

    def afterFollowup(state: InterviewState) -> str:
        return "queue_followup" if state.get("followupId") else "advance"

    g = StateGraph(InterviewState)
    g.add_node("prepare", prepare)
    g.add_node("locate", locate)
    g.add_node("ask", ask)
    g.add_node("wait", wait)
    g.add_node("transcribe", transcribe)
    g.add_node("followup", buildFollowupGraph(runner))
    g.add_node("queue_followup", queueFollowup)
    g.add_node("advance", advance)
    g.add_node("finish", finish)
    g.add_edge(START, "prepare")
    g.add_edge("prepare", "locate")
    g.add_conditional_edges("locate", afterLocate, ["ask", "advance", "finish"])
    g.add_edge("ask", "wait")
    g.add_edge("wait", "transcribe")
    g.add_conditional_edges("transcribe", afterTranscribe, ["followup", "advance"])
    g.add_conditional_edges("followup", afterFollowup, ["queue_followup", "advance"])
    g.add_edge("queue_followup", "ask")
    g.add_edge("advance", "locate")
    g.add_edge("finish", END)
    return g.compile(checkpointer=checkpointer)


def graphConfig(applicationId: str) -> dict:
    return {"configurable": {"thread_id": applicationId}, "recursion_limit": RECURSION_LIMIT}
