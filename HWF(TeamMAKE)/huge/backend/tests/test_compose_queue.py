"""질문 만들기는 한 번에 한 사람 (CONFLICTS C-28, 2026-11-19 사용자 결정).

실측(모의 지원 10명 동시): 질문 만들기 6건이 겹쳐 LLM 자리를 나눠 쓰다 각자의 예산(180초)을 다 써서 60자리 중 19개만 새로 만들었다.
줄을 세워 한 사람씩 만들고, 예산은 차례가 온 때부터 센다. 기다리는 지원자에게는 앞사람 수와 예상 시간을 알린다.
"""

import asyncio

from app.models import Application, User
from app.services import llm, question_compose
from app.settings_store import setSetting
from tests.test_question_rag import composed, makeApplication, world  # noqa: F401 — world 는 fixture


def secondApplication(sessionFactory, firstId: str, email: str = "lee@example.com") -> str:
    with sessionFactory() as db:
        first = db.get(Application, firstId)
        user = User(email=email, password_hash="x", name="이지원", role="applicant")
        db.add(user)
        db.flush()
        app = Application(user_id=user.id, posting_id=first.posting_id, attempt_status="ready", resume_snapshot=first.resume_snapshot)
        db.add(app)
        db.commit()
        return app.id


def slowLlm(fake, monkeypatch, delaySec: float, active: list, seen: list):
    """LLM 호출마다 delaySec 걸리고, 그 순간 질문을 만들고 있는 지원 건을 적는다."""
    original = fake.structured

    async def structured(schema, system, user, timeoutSec, maxTokens=400, temperature=0.4, lane="rt"):
        seen.append(question_compose.activeCompose())
        await asyncio.sleep(delaySec)
        return await original(schema, system, user, timeoutSec, maxTokens, temperature, lane)
    monkeypatch.setattr(llm, "structured", structured)


def test_composesRunOneAtATimeAndBudgetStartsAtTurn(sessionFactory, world, monkeypatch):  # noqa: F811
    """두 사람이 동시에 와도 한 사람씩 만든다. 뒷사람은 기다린 시간을 예산에서 빼지 않아 모두 새로 만든다."""
    fake = world()
    seen: list = []
    slowLlm(fake, monkeypatch, 0.01, [], seen)
    first = makeApplication(sessionFactory)
    second = secondApplication(sessionFactory, first)
    with sessionFactory() as db:
        setSetting(db, "question_compose_budget_sec", 3)  # 한 사람 혼자면 충분, 둘이 나눠 쓰면 모자라게

    async def run():
        await asyncio.gather(question_compose.compose(first), question_compose.compose(second))

    asyncio.run(run())
    firstAt = [i for i, appId in enumerate(seen) if appId == first]
    secondAt = [i for i, appId in enumerate(seen) if appId == second]
    assert firstAt and secondAt and max(firstAt) < min(secondAt)  # 앞사람이 다 끝난 뒤에 뒷사람 LLM 호출
    for appId in (first, second):
        rows = composed(sessionFactory, appId)
        assert len(rows) == 10 and {r.source for r in rows} == {"generated"}
    assert question_compose.queuePosition(first) is None and question_compose.activeCompose() is None


def test_queuePositionAndEstimate(sessionFactory, world, monkeypatch):  # noqa: F811
    """기다리는 사람은 앞에 몇 명이 있는지, 대략 몇 초 걸릴지 알 수 있다 (예상 = (앞사람 + 나) × 최근 평균)."""
    fake = world()
    gate = asyncio.Event()
    original = fake.structured

    async def blocked(schema, system, user, timeoutSec, maxTokens=400, temperature=0.4, lane="rt"):
        await gate.wait()
        return await original(schema, system, user, timeoutSec, maxTokens, temperature, lane)
    monkeypatch.setattr(llm, "structured", blocked)
    monkeypatch.setattr(question_compose, "recentComposeSec", [80.0, 100.0])
    first = makeApplication(sessionFactory)
    second = secondApplication(sessionFactory, first)
    third = secondApplication(sessionFactory, first, "park@example.com")

    async def run():
        tasks = [asyncio.create_task(question_compose.compose(a)) for a in (first, second, third)]
        await asyncio.sleep(0.2)
        state = {a: (question_compose.queuePosition(a), question_compose.estimateSec(a)) for a in (first, second, third)}
        gate.set()
        await asyncio.gather(*tasks)
        return state

    state = asyncio.run(run())
    assert state[first] == (0, 90)  # 지금 만드는 중
    assert state[second] == (1, 180)
    assert state[third] == (2, 270)


def test_waitingTooLongFillsFromReserveWithoutLlm(sessionFactory, world, monkeypatch):  # noqa: F811
    """차례를 기다리다 최대 기다림을 넘으면 줄에서 빠져 LLM 없이 예비 질문으로 채운다. 앞사람 질문 만들기는 그대로 간다."""
    fake = world()
    gate = asyncio.Event()
    original = fake.structured
    made: list = []

    async def blocked(schema, system, user, timeoutSec, maxTokens=400, temperature=0.4, lane="rt"):
        if user.startswith("[만들 질문]"):  # 질문 만들기만 막는다 (예비 직무 질문의 핵심 요소는 그대로 받는다)
            made.append(user)
            await gate.wait()
        return await original(schema, system, user, timeoutSec, maxTokens, temperature, lane)
    monkeypatch.setattr(llm, "structured", blocked)
    first = makeApplication(sessionFactory)
    second = secondApplication(sessionFactory, first)

    async def run():
        question_compose.runningTasks[first] = asyncio.create_task(question_compose.compose(first))
        question_compose.runningTasks[second] = asyncio.create_task(question_compose.compose(second))
        await asyncio.sleep(0.1)
        await asyncio.wait_for(question_compose.ensureComposed(second, waitSec=0.2), timeout=10)
        assert question_compose.queuePosition(second) is None
        gate.set()
        await question_compose.runningTasks[first]

    asyncio.run(run())
    rows = composed(sessionFactory, second)
    assert len(rows) == 10 and {r.source for r in rows} == {"reserve"}
    assert {r.substitute_reason for r in rows} == {"budget"}
    assert len(made) <= 10  # 뒷사람은 질문을 만들지 않았다 (앞사람 자리 시도만)
    assert {r.source for r in composed(sessionFactory, first)} == {"generated"}
    with sessionFactory() as db:
        assert db.get(Application, second).questions_status == "ready"


def test_screeningWaitsWhileQuestionsAreComposed():
    """서류 평가(1차, 4B)는 질문 만들기가 줄에 있는 동안 기다린다 — 질문 만들기가 LLM 을 먼저 쓴다."""
    async def run():
        assert await asyncio.wait_for(question_compose.waitComposeIdle(), timeout=1) is None  # 줄이 비면 바로
        question_compose.composeQueue.append("someone")
        waiter = asyncio.create_task(question_compose.waitComposeIdle())
        await asyncio.sleep(0.1)
        assert not waiter.done()
        question_compose.composeQueue.remove("someone")
        question_compose.notifyQueueChanged()
        await asyncio.wait_for(waiter, timeout=1)

    asyncio.run(run())
