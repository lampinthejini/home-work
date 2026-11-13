"""화면 이탈 1회째 (CHT-02·05, CONFLICTS C-18).
코딩테스트는 첫 이탈에도 시계를 멈추지 않는다: 멈추면 경고 한 번이 '시간이 줄지 않는 검색 시간'이 된다.
이탈했다 돌아온 시각과 이탈 시간은 기록해 관리자가 볼 수 있게 한다."""

import asyncio
import re
from datetime import timedelta

from test_evaluation import makeApplication

from app.domain import status as st
from app.interview import engine as en
from app.interview import lifecycle
from app.models import Application, SessionEvent
from app.settings_store import getSetting
from app.timeutil import asKst, now


class FakeSession(en.LiveSession):
    def __init__(self, appId: str, state: str):  # 웹소켓·Redis 없이 이탈 처리만 본다
        self.appId = appId
        self.sid = "s-1"
        self.state = state
        self.tasks = []
        self.sent = []
        self.current = None
        self.warned = False
        self.warnedAt = 0.0
        self.awayStartedAt = 0.0
        self.warnRemaining = None
        self.ackEvent = asyncio.Event()
        self.endedEvent = asyncio.Event()
        self.settings = {}

    async def send(self, message: dict) -> None:
        self.sent.append(message)


def startCoding(sessionFactory, monkeypatch, elapsedSec: int = 100) -> str:
    """코딩테스트를 시작한 지 elapsedSec 초 지난 지원 건."""
    monkeypatch.setattr(en, "SessionLocal", sessionFactory)
    appId = makeApplication(sessionFactory, status=st.INTERVIEWING)
    with sessionFactory() as db:
        app = db.get(Application, appId)
        lifecycle.enterCoding(db, app)
        app.coding_started_at = now() - timedelta(seconds=elapsedSec)
        db.commit()
    return appId


def codingClock(sessionFactory, appId):
    with sessionFactory() as db:
        app = db.get(Application, appId)
        return app.coding_started_at, app.coding_remaining_sec, lifecycle.codingRemaining(app)


def test_firstAwayDuringCodingKeepsTimerRunning(sessionFactory, monkeypatch):
    """첫 이탈: 경고는 띄우되 코딩 시계는 계속 간다"""
    appId = startCoding(sessionFactory, monkeypatch)
    before = codingClock(sessionFactory, appId)
    session = FakeSession(appId, "coding")

    asyncio.run(session.onAway("visibility", {"state": "hidden"}))

    startedAt, remainingSec, _ = codingClock(sessionFactory, appId)
    assert startedAt is not None, "시계가 멈추면 안 된다"
    assert asKst(startedAt) == asKst(before[0]) and remainingSec == before[1]
    assert session.sent[-1]["type"] == "warn" and session.sent[-1]["phase"] == "coding"


def test_warnAckDuringCodingDoesNotGiveTimeBack(sessionFactory, monkeypatch):
    """확인을 눌러도 이탈한 동안의 시간을 돌려주지 않는다"""
    appId = startCoding(sessionFactory, monkeypatch, elapsedSec=100)
    session = FakeSession(appId, "coding")
    limit = None
    with sessionFactory() as db:
        limit = getSetting(db, "coding_limit_sec")

    async def scenario():
        await session.onAway("visibility", {"state": "hidden"})
        await session.onWarnAck()

    asyncio.run(scenario())
    _, _, remaining = codingClock(sessionFactory, appId)
    assert remaining <= limit - 100, "이탈 전후로 흐른 시간이 남은 시간에서 빠져야 한다"
    assert session.sent[-1]["type"] == "resume" and session.sent[-1]["remaining_sec"] <= limit - 100


def test_awayReturnIsRecordedWithDuration(sessionFactory, monkeypatch):
    """돌아오면 이탈 시간을 기록한다 (CHT-05 '얼마나 벗어났는지'). 화면 이탈 횟수에는 넣지 않는다"""
    appId = startCoding(sessionFactory, monkeypatch)
    session = FakeSession(appId, "coding")

    async def scenario():
        await session.onAway("blur", {"duration_ms": 5000})
        session.awayStartedAt -= 30  # 30초 더 머물다 돌아온 것처럼
        await session.onWarnAck()

    asyncio.run(scenario())
    with sessionFactory() as db:
        events = db.query(SessionEvent).filter_by(application_id=appId).order_by(SessionEvent.id).all()
    assert [e.type for e in events] == ["blur", "away_return"]
    back = events[-1]
    assert back.judged == "info"
    seconds = int(re.search(r"(\d+)초", back.detail).group(1))
    assert 35 <= seconds <= 37, "blur 는 감지 전 머문 시간(5초)까지 더한다"
    assert sum(e.judged == "cheating" for e in events) == 1


def test_awayReturnIsRecordedInInterviewToo(sessionFactory, monkeypatch):
    """면접 중 이탈도 돌아온 기록을 남긴다 (면접은 기존처럼 답변 시간을 멈춘다)"""
    monkeypatch.setattr(en, "SessionLocal", sessionFactory)
    appId = makeApplication(sessionFactory, status=st.INTERVIEWING)
    session = FakeSession(appId, "processing")

    async def scenario():
        await session.onAway("visibility", {"state": "hidden"})
        await session.onWarnAck()

    asyncio.run(scenario())
    with sessionFactory() as db:
        types = [e.type for e in db.query(SessionEvent).filter_by(application_id=appId).order_by(SessionEvent.id)]
    assert types == ["visibility", "away_return"]
