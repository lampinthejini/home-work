"""장치가 꺼졌을 때 판정 (E18, TC-064). 창을 닫으면 카메라·마이크가 먼저 꺼지고 unload·연결 끊김이 뒤따른다.
그 순서로 와도 장애 중단(이어가기)이 아니라 응시 종료여야 한다."""

import asyncio

from test_evaluation import makeApplication

from app.domain import status as st
from app.interview import engine as en
from app.interview import lifecycle
from app.models import Application


class FakeSession(en.LiveSession):
    def __init__(self, appId: str):  # 웹소켓·Redis 없이 판정만 본다
        self.appId = appId
        self.sid = "s-1"
        self.state = "answering"
        self.tasks = []
        self.sent = []
        self.endedEvent = asyncio.Event()
        self.settings = {"unload_lookback_sec": 30}

    async def send(self, message: dict) -> None:
        self.sent.append(message)

    async def closeWs(self) -> None:
        pass


def setUp(sessionFactory, monkeypatch):
    monkeypatch.setattr(en, "SessionLocal", sessionFactory)
    monkeypatch.setattr(en, "DEVICE_END_GRACE_SEC", 0.05)
    monkeypatch.setattr(lifecycle, "queueEvaluation", lambda applicationId: None)
    appId = makeApplication(sessionFactory, status=st.INTERVIEWING)
    return appId, FakeSession(appId)


def statusOf(sessionFactory, appId):
    with sessionFactory() as db:
        app = db.get(Application, appId)
        return app.attempt_status, app.end_detail


def logUnload(sessionFactory, appId):
    with sessionFactory() as db:
        lifecycle.logEvent(db, db.get(Application, appId), "unload", "pagehide", sessionId="s-1")
        db.commit()


async def deviceEnded(session):
    await session.onDeviceError({"type": "device_error", "device": "camera", "kind": "ended"})


def test_windowCloseAfterDeviceEndIsNotFault(sessionFactory, monkeypatch):
    """장치 꺼짐 → unload 순서로 와도 응시 종료"""
    appId, session = setUp(sessionFactory, monkeypatch)

    async def scenario():
        await deviceEnded(session)
        logUnload(sessionFactory, appId)
        await asyncio.wait(session.tasks)  # 끝낼 때 세션이 자기 작업까지 취소하므로 gather 대신 wait

    asyncio.run(scenario())
    assert statusOf(sessionFactory, appId) == (st.ENDED, "unload")


def test_disconnectDuringGraceLeavesJudgementToDisconnect(sessionFactory, monkeypatch):
    """기다리는 동안 연결이 끊기면 15초 끊김 판정에 맡긴다"""
    appId, session = setUp(sessionFactory, monkeypatch)

    async def scenario():
        await deviceEnded(session)
        session.state = "disconnected"
        await asyncio.wait(session.tasks)  # 끝낼 때 세션이 자기 작업까지 취소하므로 gather 대신 wait

    asyncio.run(scenario())
    assert statusOf(sessionFactory, appId) == (st.INTERVIEWING, None)


def test_deviceEndAloneIsFault(sessionFactory, monkeypatch):
    """창을 닫지 않았는데 장치가 꺼지면 지금처럼 장애 중단"""
    appId, session = setUp(sessionFactory, monkeypatch)

    async def scenario():
        await deviceEnded(session)
        assert statusOf(sessionFactory, appId)[0] == st.INTERVIEWING  # 바로 정하지 않는다
        await asyncio.wait(session.tasks)  # 끝낼 때 세션이 자기 작업까지 취소하므로 gather 대신 wait

    asyncio.run(scenario())
    assert statusOf(sessionFactory, appId)[0] == st.INTERRUPTED
    assert session.sent[-1]["type"] == "paused"
    assert session.sent[-1]["resumes_left"] == 2  # 장애 화면(OV-01)에 남은 이어가기 횟수를 보인다


def test_openFailedIsJudgedAtOnce(sessionFactory, monkeypatch):
    """연결 때 장치를 못 연 경우는 창 닫기와 상관없으니 바로 장애 중단"""
    appId, session = setUp(sessionFactory, monkeypatch)
    asyncio.run(session.runSafely(session.onDeviceError({"type": "device_error", "device": "mic", "kind": "open_failed"})))
    assert statusOf(sessionFactory, appId)[0] == st.INTERRUPTED
    assert session.tasks == []


def test_autosaveFailureIsRecordedWithoutPausing(sessionFactory, monkeypatch):
    """코딩 자동 저장을 3번 다시 해도 못 하면 서버에 기록만 남긴다. 끊김 판정은 heartbeat 가 한다"""
    from app.models import SessionEvent

    appId, session = setUp(sessionFactory, monkeypatch)
    asyncio.run(session.onText('{"type": "autosave_failed", "problem_no": 2}'))
    assert statusOf(sessionFactory, appId)[0] == st.INTERVIEWING
    with sessionFactory() as db:
        events = db.query(SessionEvent).filter_by(application_id=appId, type="autosave_failed").all()
        assert [e.detail for e in events] == ["problem 2"]
    assert session.sent == []
