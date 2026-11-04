"""'평가 지연' 건: 6시간마다 자동 재채점, 3일 안에 관리자 결정, 없으면 마지막 재채점까지 실패한 뒤 평가 미완료 불합격,
7일이면 무조건 닫는다 (CONFLICTS U8).

점수가 없는 건에 근거를 지어내지 않는다: 사유는 고정 문구 또는 관리자가 쓴 글이고 LLM 을 부르지 않는다.
"""

import uuid
from datetime import timedelta

import fakeredis
import pytest
from conftest import APPLICANT_PASSWORD, login, signup
from test_evaluation import makeApplication

from app import worker
from app.models import Application, AuditLog, Notification, Result, User
from app.services import llm
from app.timeutil import now

REASON = "답변을 직접 읽고 직무 경험이 충분하다고 판단했습니다"


@pytest.fixture()
def ai(monkeypatch):
    state = {"up": True}

    async def health(timeoutSec=3, lane="rt"):
        return state["up"]
    monkeypatch.setattr(llm, "health", health)
    return state


@pytest.fixture()
def queued(monkeypatch, ai):
    monkeypatch.setattr(worker, "_redis", fakeredis.FakeRedis())
    worker._redis.set(worker.SWEEP_LAST_KEY, now().isoformat())  # 방금까지 점검이 돌던 상태
    monkeypatch.setattr(worker, "queueMail", lambda notificationId, countdown=0: None)
    sent = []
    monkeypatch.setattr(worker, "enqueueEvaluation", lambda appId, attempt=1, countdown=0: sent.append(appId))

    async def forbidden(*args, **kwargs):
        raise AssertionError("LLM 을 부르면 안 된다")
    monkeypatch.setattr(llm, "structured", forbidden)
    return sent


def needsReview(sessionFactory, hoursAgo=0, reason="analysis_timeout") -> str:
    appId = makeApplication(sessionFactory, email=f"{uuid.uuid4().hex}@example.com")
    worker.toNeedsReview(appId, reason)
    with sessionFactory() as db:
        db.get(Application, appId).needs_review_since = now() - timedelta(hours=hoursAgo)
        db.commit()
    return appId


def sinceOf(sessionFactory, appId):
    with sessionFactory() as db:
        return db.get(Application, appId).needs_review_since.replace(tzinfo=None)


def test_retriesEverySixHoursOnly(sessionFactory, queued):
    appId = needsReview(sessionFactory, hoursAgo=5)
    worker.sweepTask.run()
    assert queued == []
    with sessionFactory() as db:
        db.get(Application, appId).needs_review_since = now() - timedelta(hours=7)
        db.commit()
    worker.sweepTask.run()
    assert queued == [appId]
    with sessionFactory() as db:
        assert db.get(Application, appId).analysis_status == "pending"
        db.get(Application, appId).analysis_status = "needs_review"  # 다시 확인 필요가 돼도 6시간 안에는 또 넣지 않는다
        db.commit()
    worker.sweepTask.run()
    assert queued == [appId]


def test_instructionSuspectedIsNotRetriedAutomatically(sessionFactory, queued):
    needsReview(sessionFactory, hoursAgo=7, reason="instruction_suspected")
    worker.sweepTask.run()
    assert queued == []


def test_retryFailureKeepsDeadlineAndDoesNotNotifyAgain(sessionFactory, queued):
    appId = needsReview(sessionFactory, hoursAgo=7)
    since = sinceOf(sessionFactory, appId)
    worker.sweepTask.run()
    worker.toNeedsReview(appId, "quote_not_found")
    assert sinceOf(sessionFactory, appId) == since
    with sessionFactory() as db:
        app = db.get(Application, appId)
        assert app.analysis_status == "needs_review" and app.review_reason == "quote_not_found"
        assert db.query(Notification).filter_by(kind="needs_review").count() == 1


def overdueAndRetried(sessionFactory, queued, hoursAgo=73):
    """기한이 지난 건이 마지막 재채점까지 실패한 상태."""
    appId = needsReview(sessionFactory, hoursAgo=hoursAgo)
    worker.sweepTask.run()
    assert queued[-1] == appId
    worker.toNeedsReview(appId, "analysis_timeout")
    return appId


def test_afterThreeDaysFailsWithHonestReason(sessionFactory, queued, adminClient):
    appId = overdueAndRetried(sessionFactory, queued)
    worker.sweepTask.run()
    with sessionFactory() as db:
        app = db.get(Application, appId)
        result = db.query(Result).filter_by(application_id=appId).one()
        assert app.analysis_status == "decided" and app.review_reason is None
        assert app.purge_at is not None and app.release_at is not None
        assert result.ai_decision == "fail" and result.decision_check == "incomplete"
        assert "채점을 끝내지 못" in result.ai_reason and result.ai_reason_quotes == []
        assert result.strengths == [] and result.improvements == [] and result.summary is None
        assert result.public_view["status_reason"] == "evaluation_incomplete" and result.public_view["ai_generated"] is False
        assert db.query(AuditLog).filter_by(action="analysis.auto_fail", target=appId).count() == 1
    detail = adminClient.get(f"/admin/applicants/{appId}").json()["result"]
    assert detail["total_score"] is None and detail["interview_score"] is None and detail["decision_check"] == "incomplete"
    worker.sweepTask.run()  # 두 번 돌아도 하나
    with sessionFactory() as db:
        assert db.query(Result).filter_by(application_id=appId).count() == 1


def resultCount(sessionFactory, appId) -> int:
    with sessionFactory() as db:
        return db.query(Result).filter_by(application_id=appId).count()


def test_instructionSuspectedAlsoClosesAfterThreeDays(sessionFactory, queued):
    appId = needsReview(sessionFactory, hoursAgo=73, reason="instruction_suspected")
    worker.sweepTask.run()
    assert queued == []
    with sessionFactory() as db:
        assert db.query(Result).filter_by(application_id=appId).one().decision_check == "incomplete"


def test_overdueIsRetriedOnceBeforeFailing(sessionFactory, queued):
    """PC 를 3일 넘게 꺼 뒀다 켠 경우: 재채점 없이 불합격으로 닫지 않는다."""
    appId = needsReview(sessionFactory, hoursAgo=100)
    worker.sweepTask.run()
    assert queued == [appId] and resultCount(sessionFactory, appId) == 0
    worker.sweepTask.run()  # 재채점이 아직 돌고 있으면 닫지 않는다
    assert resultCount(sessionFactory, appId) == 0
    worker.toNeedsReview(appId, "analysis_timeout")
    worker.sweepTask.run()
    assert resultCount(sessionFactory, appId) == 1


def test_aiDownNeitherRetriesNorFails(sessionFactory, queued, ai):
    ai["up"] = False
    appId = needsReview(sessionFactory, hoursAgo=100)
    young = needsReview(sessionFactory, hoursAgo=7)
    worker.sweepTask.run()
    assert queued == [] and resultCount(sessionFactory, appId) == 0
    ai["up"] = True  # 복구되면 바로 닫지 않고 먼저 재채점한다
    worker.sweepTask.run()
    assert sorted(queued) == sorted([appId, young]) and resultCount(sessionFactory, appId) == 0


def test_hardLimitClosesEvenWhenAiDown(sessionFactory, queued, ai):
    ai["up"] = False
    appId = needsReview(sessionFactory, hoursAgo=7 * 24 + 1)
    instruction = needsReview(sessionFactory, hoursAgo=7 * 24 + 1, reason="instruction_suspected")
    worker.sweepTask.run()
    assert queued == []
    assert resultCount(sessionFactory, appId) == 1 and resultCount(sessionFactory, instruction) == 1


def test_instructionWaitsOneDayAfterServiceWasDown(sessionFactory, queued):
    appId = needsReview(sessionFactory, hoursAgo=100, reason="instruction_suspected")
    worker._redis.set(worker.SWEEP_LAST_KEY, (now() - timedelta(hours=2)).isoformat())
    worker.sweepTask.run()
    assert resultCount(sessionFactory, appId) == 0  # 꺼져 있던 동안 관리자가 볼 수 없었다
    assert 0 < worker._redis.ttl(worker.SWEEP_GRACE_KEY) <= 24 * 3600
    worker.sweepTask.run()
    assert resultCount(sessionFactory, appId) == 0
    worker._redis.delete(worker.SWEEP_GRACE_KEY)  # 24시간이 지남
    worker.sweepTask.run()
    assert resultCount(sessionFactory, appId) == 1


def test_adminDecidesManually(sessionFactory, queued, adminClient):
    appId = needsReview(sessionFactory, hoursAgo=1)
    with sessionFactory() as db:
        postingId = db.get(Application, appId).posting_id
    assert adminClient.get(f"/admin/applicants/{appId}").json()["review_deadline"] is not None
    url = f"/admin/analysis/{appId}/decision"
    assert adminClient.post(url, json={"decision": "pass", "reason": "짧음"}).status_code == 400
    assert adminClient.post(url, json={"decision": "maybe", "reason": REASON}).status_code == 422
    assert adminClient.post(url, json={"decision": "pass", "reason": REASON}).status_code == 200
    with sessionFactory() as db:
        result = db.query(Result).filter_by(application_id=appId).one()
        assert (result.ai_decision, result.decision_check, result.ai_reason) == ("pass", "manual", REASON)
        assert result.public_view["status_reason"] == "manual_decision" and result.public_view["ai_generated"] is False
        log = db.query(AuditLog).filter_by(action="analysis.manual_decision", target=appId).one()
        assert log.actor_id and log.detail["decision"] == "pass" and REASON not in str(log.detail)  # 사유 글은 감사 로그에 넣지 않는다
    passed = adminClient.get(f"/admin/postings/{postingId}/passed").json()["items"]
    assert [(p["application_id"], p["total_score"]) for p in passed] == [(appId, None)]
    assert adminClient.post(url, json={"decision": "fail", "reason": REASON}).status_code == 409  # 확정 뒤에는 못 바꾼다


def test_applicantCannotDecide(sessionFactory, queued, client):
    appId = needsReview(sessionFactory, hoursAgo=1)
    assert client.post(f"/admin/analysis/{appId}/decision", json={"decision": "pass", "reason": REASON}).status_code in (401, 403)


def test_decisionOnlyForNeedsReview(sessionFactory, queued, adminClient):
    appId = makeApplication(sessionFactory)
    assert adminClient.post(f"/admin/analysis/{appId}/decision", json={"decision": "pass", "reason": REASON}).status_code == 409


def test_manualReprocessDoesNotExtendDeadline(sessionFactory, queued, adminClient, monkeypatch):
    monkeypatch.setattr(worker, "requestReprocess", lambda appId: None)
    appId = needsReview(sessionFactory, hoursAgo=10)
    since = sinceOf(sessionFactory, appId)
    assert adminClient.post(f"/admin/analysis/{appId}/reprocess").status_code == 202
    worker.toNeedsReview(appId, "analysis_timeout")
    assert sinceOf(sessionFactory, appId) == since


def test_unscoredResultsStayOutOfScoreStats(sessionFactory, queued, adminClient):
    overdueAndRetried(sessionFactory, queued)
    worker.sweepTask.run()
    stats = adminClient.get("/admin/stats").json()
    assert stats["taken"] == 1 and stats["pass_rate"] is None and stats["average_total"] is None


def test_applicantSeesWhyAfterRelease(sessionFactory, queued, client):
    signup(client, "real@example.com")
    login(client, "real@example.com", APPLICANT_PASSWORD)
    appId = overdueAndRetried(sessionFactory, queued)
    worker.sweepTask.run()
    with sessionFactory() as db:
        app = db.get(Application, appId)
        app.user_id = db.query(User).filter_by(email="real@example.com").one().id
        app.release_status, app.release_at = "released", now() - timedelta(minutes=1)
        db.commit()
    body = client.get(f"/me/results/{appId}").json()
    assert body["result"] == "fail" and body["status_reason"] == "evaluation_incomplete"
    assert body["ai_generated"] is False and body["strengths"] == []


def test_adminWarnedOneDayBeforeDeadline(sessionFactory, queued):
    appId = needsReview(sessionFactory, hoursAgo=50)
    with sessionFactory() as db:
        rows = worker.reminderRows(db)
    assert any(r[1] == "needs_review" and r[4] == appId and "24시간" in r[2] for r in rows)
