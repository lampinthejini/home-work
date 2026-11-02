"""관리자 2단계-B: 비교 · 다음 전형 · 통계 · 운영 현황 · 운영 설정."""

from datetime import timedelta
from decimal import Decimal

from conftest import login, signup
from test_evaluation import makeApplication

from app.domain import status as st
from app.models import Application, AuditLog, Notification, Result, User
from app.timeutil import now


def decide(sessionFactory, appId, total, decision, items=None):
    with sessionFactory() as db:
        app = db.get(Application, appId)
        db.add(Result(application_id=appId, criteria_id=1, item_points=items or {"expertise": total}, interview_score=Decimal(total),
                      total_score=Decimal(total), pass_score=Decimal(70), ai_decision=decision, ai_reason="이유",
                      strengths=["강점"], improvements=["개선"], model_version="m", prompt_version="p", rubric_version="r",
                      public_view={}))
        app.analysis_status = "decided"
        app.purge_at = now() + timedelta(days=9)
        db.commit()


def samePosting(sessionFactory, appId, otherId):
    with sessionFactory() as db:
        db.get(Application, otherId).posting_id = db.get(Application, appId).posting_id
        db.commit()


def test_compareTwoToThree(sessionFactory, adminClient):
    a = makeApplication(sessionFactory)
    b = makeApplication(sessionFactory, email="lee@example.com")
    samePosting(sessionFactory, a, b)
    decide(sessionFactory, a, 80, "pass")
    res = adminClient.get(f"/admin/applicants/compare?ids={a},{b}")
    assert res.status_code == 200
    body = res.json()
    assert body["same_posting"] and body["items"][0]["total_score"] == "80.00" and body["items"][1]["decision"] is None
    assert adminClient.get(f"/admin/applicants/compare?ids={a}").json()["code"] == "COMPARE_COUNT"
    assert adminClient.get(f"/admin/applicants/compare?ids={a},nope").status_code == 404
    with sessionFactory() as db:
        assert db.query(AuditLog).filter_by(action="applicant.compare").count() == 1


def test_passedListsOnlyPassWithContacts(sessionFactory, adminClient):
    a = makeApplication(sessionFactory)
    b = makeApplication(sessionFactory, email="lee@example.com")
    c = makeApplication(sessionFactory, email="park@example.com")
    samePosting(sessionFactory, a, b)
    samePosting(sessionFactory, a, c)
    decide(sessionFactory, a, 75, "pass")
    decide(sessionFactory, b, 60, "fail")
    with sessionFactory() as db:
        postingId = db.get(Application, a).posting_id
    body = adminClient.get(f"/admin/postings/{postingId}/passed").json()
    assert [i["application_id"] for i in body["items"]] == [a]
    assert body["items"][0]["phone"] == "010-1234-5678" and body["undecided"] == 1 and body["purge_at"]
    assert adminClient.get(f"/admin/postings/{postingId}/passed?q=없는이름").json()["items"] == []


def test_statsHaveNoPersonalData(sessionFactory, adminClient):
    a = makeApplication(sessionFactory)
    b = makeApplication(sessionFactory, email="lee@example.com", status=st.CANCELLED)
    makeApplication(sessionFactory, email="park@example.com", status=st.NOT_TAKEN_CLOSED)
    decide(sessionFactory, a, 75, "pass")
    with sessionFactory() as db:
        db.get(Application, b).end_detail = "exit_twice"
        db.commit()
    body = adminClient.get("/admin/stats").json()
    assert body["applications"] == 3 and body["taken"] == 2 and body["pass_rate"] == 100
    assert body["average_total"] == "75.00" and body["cheating_cancelled"] == 1
    assert body["score_bins"][7]["count"] == 1 and len(body["monthly"]) == 12 and body["monthly"][-1]["taken"] == 2
    text = str(body)
    assert "김지원" not in text and "example.com" not in text


def test_statsKeepPurgedApplicationsAsAnonymousTotals(sessionFactory, adminClient, monkeypatch):
    """보관 기간이 지나 지운 건도 익명 집계로 남아 통계 숫자가 그대로다 (PRD 10-2 '통계 숫자 기한 없음', CONFLICTS F1)."""
    from app.models import StatsArchive
    from app.services import retention, storage
    monkeypatch.setattr(storage, "deletePrefix", lambda prefix: 0)
    a = makeApplication(sessionFactory)
    b = makeApplication(sessionFactory, email="lee@example.com", status=st.CANCELLED)
    c = makeApplication(sessionFactory, email="park@example.com", status=st.NOT_TAKEN_CLOSED)
    d = makeApplication(sessionFactory, email="choi@example.com")
    for other in (b, c, d):
        samePosting(sessionFactory, a, other)
    decide(sessionFactory, a, 75, "pass", {"expertise": 4, "logic": 3})
    decide(sessionFactory, d, 55, "fail", {"expertise": 2})
    with sessionFactory() as db:
        db.get(Application, b).end_detail = "exit_twice"
        postingId = db.get(Application, a).posting_id
        db.commit()
    before = adminClient.get("/admin/stats").json()
    beforePosting = adminClient.get(f"/admin/stats?posting_id={postingId}").json()
    with sessionFactory() as db:
        for appId in (a, b, c):  # d 는 남겨 두어 남은 건과 지운 건이 함께 세어지는지 본다
            db.get(Application, appId).purge_at = now() - timedelta(minutes=1)
        db.commit()
        assert sorted(retention.purgeDue(db)) == sorted([a, b, c])
        assert db.query(Application).count() == 1
        archived = db.query(StatsArchive).all()
        assert archived and all(not hasattr(row, "application_id") and not hasattr(row, "user_id") for row in archived)
    assert adminClient.get("/admin/stats").json() == before
    assert adminClient.get(f"/admin/stats?posting_id={postingId}").json() == beforePosting
    assert before["applications"] == 4 and before["taken"] == 3 and before["pass_rate"] == 50
    assert before["item_averages"] == {"expertise": "3.00", "logic": "3.00"} and before["cheating_cancelled"] == 1


def test_opsStatusMasksEmailAndCountsReserve(sessionFactory, adminClient):
    a = makeApplication(sessionFactory)
    with sessionFactory() as db:
        db.get(Application, a).analysis_status = "needs_review"
        db.get(Application, a).review_reason = "analysis_timeout"
        user = db.query(User).filter_by(email="kim@example.com").one()
        db.add(Notification(user_id=user.id, kind="result_released", title="결과", email_status="failed", email_fail_reason="550 no user"))
        db.commit()
    body = adminClient.get("/admin/ops-status").json()
    assert body["needs_review"][0]["reason"] == "analysis_timeout"
    assert body["mail_failed"]["count"] == 1 and body["mail_failed"]["items"][0]["to"] == "ki***@example.com"
    assert {r["category"] for r in body["reserve_questions"]} == {"personality", "company", "resume", "job"}
    assert body["coding_problems"]


def test_reserveQuestionsMeetMinimum():
    from app.routers.admin_ops import RESERVE_MINIMUM
    from app.services.question_bank import RESERVE_QUESTIONS, normalizeText
    for kind in ("personality", "company", "resume", "job"):
        texts = RESERVE_QUESTIONS[kind]
        assert len(texts) >= RESERVE_MINIMUM, kind
        assert len({normalizeText(t) for t in texts}) == len(texts), kind


def test_settingsRangeAndHistory(adminClient):
    assert adminClient.put("/admin/settings/max_concurrent_interviews", json={"value": 0}).json()["code"] == "INVALID_SETTING"
    assert adminClient.put("/admin/settings/no_such_key", json={"value": 1}).status_code == 404
    assert adminClient.put("/admin/settings/max_concurrent_interviews", json={"value": 3}).status_code == 200
    body = adminClient.get("/admin/settings").json()
    assert body["max_concurrent_interviews"] == 3 and body["active_interviews"] == 0
    assert body["history"][0]["to"] == 3 and body["history"][0]["from"] is not None


def test_applicantCannotUseAdminOps(client, sessionFactory):
    signup(client)
    login(client, "kim@example.com", "Apply#Pass2026")
    for path in ("/admin/stats", "/admin/ops-status", "/admin/applicants/compare?ids=a,b"):
        assert client.get(path).status_code in (401, 403)


def test_settingsOnlyScreenKeysEditable(adminClient):
    assert adminClient.put("/admin/settings/upload_max_mb", json={"value": -1}).json()["code"] == "INVALID_SETTING"


def test_mailFailReasonAddressMasked(sessionFactory, adminClient):
    makeApplication(sessionFactory)
    with sessionFactory() as db:
        user = db.query(User).filter_by(email="kim@example.com").one()
        db.add(Notification(user_id=user.id, kind="result_released", title="결과", email_status="failed",
                            email_fail_reason="550 <kim@example.com> no such user"))
        db.commit()
    reason = adminClient.get("/admin/ops-status").json()["mail_failed"]["items"][0]["reason"]
    assert "kim@example.com" not in reason and "ki***@example.com" in reason
