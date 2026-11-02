"""동의 철회 (APP-03)·회원 탈퇴 (화면정의서 S-A13 계정 탭, API 명세서 3장·5장, 테이블 정의서 1-6·1-7)."""

import pytest
from conftest import APPLICANT_PASSWORD, login, signup
from test_api_apply import applyReady, asApplicant

from app.domain import status as st
from app.interview import registry
from app.models import Application, AuditLog, Consent, DeletionLog, Notification, SavedResume, StatsArchive, User
from app.services import admission, storage


@pytest.fixture()
def deleted(monkeypatch):
    prefixes = []
    monkeypatch.setattr(storage, "deletePrefix", lambda prefix: prefixes.append(prefix) or 0)
    return prefixes


@pytest.fixture()
def terminated(monkeypatch):
    calls = []

    async def fake(ids, reason, detail=None):
        calls.append((list(ids), reason))
    monkeypatch.setattr(registry, "terminateMany", fake)
    return calls


def interviewing(sessionFactory, appId):
    """시작 API 를 거친 것처럼 진행 중 + 자리 잡음으로 만든다."""
    with sessionFactory() as db:
        app = db.get(Application, appId)
        app.attempt_status = st.INTERVIEWING
        admission.forceAcquire(db, app)
    assert int(admission.redisClient().get(admission.ACTIVE_KEY)) == 1


def test_consentWithdrawCancelsAndDeletesApplication(adminClient, sessionFactory, deleted, terminated):
    client, postingId = asApplicant(adminClient)
    appId = applyReady(client, postingId)
    interviewing(sessionFactory, appId)
    assert client.get("/me/applications").json()["items"][0]["consented"] is True

    res = client.post(f"/applications/{appId}/consent/withdraw")
    assert res.status_code == 204, res.text
    assert terminated == [([appId], "withdrawn")]
    assert int(admission.redisClient().get(admission.ACTIVE_KEY)) == 0  # 자리를 돌려준다
    assert f"answers/{appId}/" in deleted and f"recordings/{appId}/" in deleted
    with sessionFactory() as db:
        assert db.get(Application, appId) is None
        consent = db.query(Consent).one()
        assert consent.application_id is None and consent.withdrawn_at is not None  # 철회 기록은 증거로 남는다
        log = db.query(DeletionLog).one()
        assert (log.application_id, log.cause, log.scope) == (appId, "consent", "interview_data")
        assert db.query(StatsArchive).count() == 0  # 끝나지 않은 응시는 통계에 넣지 않는다
        assert db.query(User).filter_by(email="kim@example.com").count() == 1  # 계정은 그대로
    assert client.get("/me/applications").json()["items"] == []
    assert client.post(f"/applications/{appId}/consent/withdraw").status_code == 404


def test_consentWithdrawNeedsConsentAndOwner(adminClient, sessionFactory, deleted, terminated):
    client, postingId = asApplicant(adminClient)
    appId = client.post("/applications", json={"posting_id": postingId}).json()["application_id"]
    res = client.post(f"/applications/{appId}/consent/withdraw")
    assert res.status_code == 409 and res.json()["code"] == "NO_CONSENT"
    client.post("/auth/logout")
    signup(client, "lee@example.com")
    login(client, "lee@example.com", APPLICANT_PASSWORD)
    assert client.post(f"/applications/{appId}/consent/withdraw").status_code == 404


def test_accountWithdrawDeletesEverything(adminClient, sessionFactory, deleted, terminated):
    client, postingId = asApplicant(adminClient)
    appId = applyReady(client, postingId)
    interviewing(sessionFactory, appId)
    with sessionFactory() as db:
        user = db.query(User).filter_by(email="kim@example.com").one()
        userId = user.id
        db.add(SavedResume(user_id=userId, resume={"name": "김지원"}, name="김지원"))
        db.add(Notification(user_id=userId, kind="info", title="안내"))
        db.commit()

    wrong = client.post("/me/withdraw", json={"password": "Wrong#Pass2026", "confirm_text": "탈퇴"})
    assert wrong.status_code == 400 and wrong.json()["code"] == "WRONG_PASSWORD"
    noText = client.post("/me/withdraw", json={"password": APPLICANT_PASSWORD, "confirm_text": "탈퇴할게요"})
    assert noText.status_code == 400 and noText.json()["code"] == "CONFIRM_TEXT"

    res = client.post("/me/withdraw", json={"password": APPLICANT_PASSWORD, "confirm_text": "탈퇴"})
    assert res.status_code == 204, res.text
    assert terminated == [([appId], "withdrawn")]
    assert int(admission.redisClient().get(admission.ACTIVE_KEY)) == 0
    assert f"resumes/{userId}/" in deleted
    with sessionFactory() as db:
        assert db.get(User, userId) is None and db.get(Application, appId) is None
        assert db.query(SavedResume).count() == 0 and db.query(Notification).count() == 0
        assert db.query(Consent).one().withdrawn_at is not None
        logs = {(row.cause, row.scope) for row in db.query(DeletionLog)}
        assert logs == {("withdraw", "interview_data"), ("withdraw", "account")}
        assert db.query(AuditLog).filter_by(action="account.withdraw").count() == 1
    assert client.get("/auth/me").status_code == 401
    signup(client)  # 같은 이메일로 다시 가입할 수 있다 (테이블 정의서 1-7)


def test_adminCannotWithdraw(adminClient):
    from conftest import ADMIN_PASSWORD
    res = adminClient.post("/me/withdraw", json={"password": ADMIN_PASSWORD, "confirm_text": "탈퇴"})
    assert res.status_code == 403


def test_withdrawnFinishedAttemptKeepsAnonymousStats(adminClient, sessionFactory, deleted, terminated):
    client, postingId = asApplicant(adminClient)
    appId = applyReady(client, postingId)
    with sessionFactory() as db:
        app = db.get(Application, appId)
        app.attempt_status = st.COMPLETED
        from app.timeutil import now
        app.completed_at = now()
        db.commit()
    assert client.post(f"/applications/{appId}/consent/withdraw").status_code == 204
    assert terminated == []
    with sessionFactory() as db:
        row = db.query(StatsArchive).one()  # 끝난 응시는 숫자만 익명으로 남긴다
        assert (row.posting_id, row.applications, row.taken) == (postingId, 1, 1)
