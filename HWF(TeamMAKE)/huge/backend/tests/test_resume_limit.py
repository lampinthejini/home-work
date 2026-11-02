"""장애 이어가기 상한 (CONFLICTS D1, 사용자 결정 2026-10-30: 3회). 지원자 쪽 끊김만 센다."""

from test_evaluation import makeApplication

from app.domain import status as st
from app.interview import lifecycle
from app.models import Application


def interruptAndResume(db, app, reason) -> bool:
    paused = lifecycle.markInterrupted(db, app, reason)
    if paused:
        app.attempt_status = st.transition(app.attempt_status, st.INTERVIEWING)  # 이어가기
        db.commit()
    return paused


def test_fourthApplicantSideInterruptionEndsAttempt(sessionFactory):
    appId = makeApplication(sessionFactory, status=st.INTERVIEWING)
    with sessionFactory() as db:
        app = db.get(Application, appId)
        assert [interruptAndResume(db, app, "ws_abnormal_close") for _ in range(3)] == [True, True, True]
        assert lifecycle.markInterrupted(db, app, "heartbeat_timeout") is False
        assert (app.attempt_status, app.end_detail) == (st.ENDED, "resume_limit")
        assert app.completed_at is not None


def test_serverSideInterruptionsDoNotCount(sessionFactory):
    appId = makeApplication(sessionFactory, status=st.INTERVIEWING)
    with sessionFactory() as db:
        app = db.get(Application, appId)
        for reason in ("server_error", "unknown", "server_error", "unknown"):
            assert interruptAndResume(db, app, reason)
        for _ in range(3):
            assert interruptAndResume(db, app, "device_error")
        assert app.attempt_status == st.INTERVIEWING
        assert lifecycle.resumesLeft(db, app) == 0
