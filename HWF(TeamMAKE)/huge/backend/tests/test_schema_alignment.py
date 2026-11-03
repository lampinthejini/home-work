"""테이블 정의서에 맞춘 덧붙이기 (CONFLICTS.md T 절, 2026-11-02 사용자 결정): CHECK 제약 · 빠진 시각 칸 · 수정 요약."""

from datetime import timedelta

import pytest
from conftest import postingBody
from sqlalchemy.exc import IntegrityError
from test_evaluation import makeApplication

from app.domain import status as st
from app.models import Application, EvaluationCriteria, PostingRevision, User
from app.services import evaluation
from app.timeutil import now


def test_attemptStatusOutsideListIsRejectedByDb(sessionFactory):
    appId = makeApplication(sessionFactory)
    with sessionFactory() as db:
        db.get(Application, appId).attempt_status = "finished"
        with pytest.raises(IntegrityError):
            db.commit()


def test_everyKnownAttemptStatusIsAllowed(sessionFactory):
    appId = makeApplication(sessionFactory)
    for value in (st.DRAFTING, st.READY, st.INTERVIEWING, st.CODING, st.INTERRUPTED, st.COMPLETED,
                  st.ENDED, st.ENDED_CLOSED, st.CANCELLED, st.NOT_TAKEN_CLOSED):
        with sessionFactory() as db:
            db.get(Application, appId).attempt_status = value
            db.commit()


def test_roleOutsideListIsRejected(sessionFactory):
    with sessionFactory() as db:
        db.add(User(email="x@example.com", password_hash="x", name="x", role="superuser"))
        with pytest.raises(IntegrityError):
            db.commit()


def test_updatedAtMovesOnChange(sessionFactory):
    appId = makeApplication(sessionFactory)
    with sessionFactory() as db:
        app = db.get(Application, appId)
        assert app.updated_at is not None and app.user.updated_at is not None and app.user.email_verified_at is None
        app.updated_at = now() - timedelta(days=365 * 20)
        db.commit()
        app.away_count = 1
        db.commit()
        assert db.get(Application, appId).updated_at.year >= now().year  # 바뀌면 지금 시각으로 다시 찍힌다


def test_needsReviewSinceSetAndCleared(sessionFactory):
    appId = makeApplication(sessionFactory)
    assert evaluation.markNeedsReview(appId, "analysis_timeout")
    with sessionFactory() as db:
        app = db.get(Application, appId)
        assert app.needs_review_since is not None
        app.analysis_status = "pending"
        app.review_reason = None
        db.commit()
        assert db.get(Application, appId).needs_review_since is None  # 사유가 지워지면 같이 지운다


def test_lockingCriteriaRecordsLockedAt():
    c = EvaluationCriteria(weights={}, locked=False)
    assert c.locked_at is None
    c.locked = True
    first = c.locked_at
    assert first is not None
    c.locked = True  # 이미 잠겼으면 시각을 바꾸지 않는다
    assert c.locked_at == first


def test_revisionStoresSummary(adminClient, sessionFactory):
    body = postingBody(open_at=(now() - timedelta(hours=1)).isoformat())
    postingId = adminClient.post("/admin/postings", json=body).json()["posting_id"]
    assert adminClient.post(f"/admin/postings/{postingId}/publish").status_code == 200
    assert adminClient.patch(f"/admin/postings/{postingId}", json={"location": "서울 서초구"}).status_code == 200
    with sessionFactory() as db:
        row = db.query(PostingRevision).filter_by(posting_id=postingId, field="location").one()
        assert row.summary.startswith("근무지:") and row.summary.endswith("→ 서울 서초구")


def test_settingRecordsWhoChangedIt(adminClient, sessionFactory):
    from app.models import AppSetting

    res = adminClient.put("/admin/settings/max_concurrent_interviews", json={"value": 2})
    assert res.status_code == 200, res.text
    with sessionFactory() as db:
        admin = db.query(User).filter_by(role="admin").first()
        assert db.get(AppSetting, "max_concurrent_interviews").updated_by == admin.id
