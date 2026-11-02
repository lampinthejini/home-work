"""코드 리뷰 반영 회귀 테스트: 비밀번호 변경 시 다른 로그인 끊기 · 붙은 세션 없는 진행 중 응시 정리."""

from datetime import timedelta

from conftest import APPLICANT_PASSWORD, login, publishedPosting, signup
from fastapi.testclient import TestClient

from app import jobs
from app.domain import status as st
from app.models import Application, InterviewSession, User
from app.timeutil import now

NEW_PASSWORD = "Fresh#Pass2027"


def test_passwordChangeRevokesOtherSessions(client):
    signup(client)
    login(client, "kim@example.com", APPLICANT_PASSWORD)
    other = TestClient(client.app, base_url="http://127.0.0.1:8000")
    login(other, "kim@example.com", APPLICANT_PASSWORD)
    res = client.post("/auth/password-change", json={"current_password": APPLICANT_PASSWORD, "new_password": NEW_PASSWORD})
    assert res.status_code == 204
    assert client.get("/auth/me").status_code == 200
    assert other.get("/auth/me").status_code == 401


def makeInProgress(sessionFactory, adminClient, sessionAgeSec: int) -> str:
    postingId = publishedPosting(adminClient)
    with sessionFactory() as db:
        user = User(email="lee@example.com", password_hash="x", name="이", role="applicant")
        db.add(user)
        db.flush()
        app = Application(user_id=user.id, posting_id=postingId, attempt_status=st.INTERVIEWING, holds_seat=True)
        db.add(app)
        db.flush()
        db.add(InterviewSession(application_id=app.id, user_id=user.id, created_at=now() - timedelta(seconds=sessionAgeSec)))
        db.commit()
        return app.id


def test_orphanedAttemptBecomesInterrupted(sessionFactory, adminClient):
    appId = makeInProgress(sessionFactory, adminClient, sessionAgeSec=600)
    with sessionFactory() as db:
        jobs.sweepOrphans(db)
    with sessionFactory() as db:
        app = db.get(Application, appId)
        assert app.attempt_status == st.INTERRUPTED
        assert app.interruption_judged == "fault"


def test_freshSessionIsLeftAlone(sessionFactory, adminClient):
    # 시작 직후 면접 화면이 아직 연결 중인 응시는 건드리지 않는다
    appId = makeInProgress(sessionFactory, adminClient, sessionAgeSec=10)
    with sessionFactory() as db:
        jobs.sweepOrphans(db)
    with sessionFactory() as db:
        assert db.get(Application, appId).attempt_status == st.INTERVIEWING
