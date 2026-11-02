"""보관 기간 삭제·코딩 실행 worker 이전 (2단계-C)."""

from datetime import timedelta

import fakeredis
from test_evaluation import makeApplication

from app import worker
from app.models import Answer, Application, Consent, DeletionLog, InterviewQuestion, ResumeUpload, User
from app.services import coding, retention, sandbox_runner, storage
from app.timeutil import now


def withConsentAndUpload(sessionFactory, appId):
    with sessionFactory() as db:
        app = db.get(Application, appId)
        db.add(Consent(application_id=appId, subject_hash="h" * 64, consent_version="v1.3", items={"retention": True}))
        db.add(ResumeUpload(user_id=app.user_id, application_id=appId, file_key=f"resumes/{app.user_id}/up1", file_name="cv.pdf",
                                content_type="application/pdf"))
        db.commit()


def test_purgeDeletesInterviewDataKeepsConsentAndLogs(sessionFactory, monkeypatch):
    deleted = []
    monkeypatch.setattr(storage, "deletePrefix", lambda prefix: deleted.append(prefix) or 1)
    appId = makeApplication(sessionFactory)
    keep = makeApplication(sessionFactory, email="lee@example.com")
    withConsentAndUpload(sessionFactory, appId)
    fake = fakeredis.FakeRedis()
    fake.set(f"eval:since:{appId}", "x")
    with sessionFactory() as db:
        db.get(Application, appId).purge_at = now() - timedelta(minutes=1)
        db.get(Application, keep).purge_at = now() + timedelta(days=1)
        db.commit()
        assert retention.purgeDue(db, fake) == [appId]
    with sessionFactory() as db:
        assert db.get(Application, appId) is None and db.get(Application, keep) is not None
        assert db.query(Answer).filter_by(application_id=appId).count() == 0
        assert db.query(InterviewQuestion).filter_by(application_id=appId).count() == 0
        consent = db.query(Consent).one()
        assert consent.application_id is None and consent.subject_hash == "h" * 64  # 동의는 증거로 남는다
        assert db.query(User).count() == 3  # 회원 계정은 지우지 않는다 (탈퇴 때 지움)
        logRow = db.query(DeletionLog).one()
        assert (logRow.application_id, logRow.cause, logRow.scope) == (appId, "retention", "interview_data")
        assert logRow.deleted_items["files"] == 4 and logRow.deleted_items["redis_keys"] == 1
        assert logRow.deleted_items["db_rows"] == 7  # 지원 1 + 질문 3 + 답변 2 + 업로드 1
    assert f"answers/{appId}/" in deleted and any(p.startswith("resumes/") for p in deleted)
    assert not fake.exists(f"eval:since:{appId}")


def test_purgeKeepsDbRowsWhenFileDeleteFails(sessionFactory, monkeypatch):
    def broken(prefix):
        raise RuntimeError("s3 down")
    monkeypatch.setattr(storage, "deletePrefix", broken)
    appId = makeApplication(sessionFactory)
    with sessionFactory() as db:
        db.get(Application, appId).purge_at = now() - timedelta(minutes=1)
        db.commit()
        assert retention.purgeDue(db) == []
    with sessionFactory() as db:  # 파일을 못 지웠으면 DB 도 남겨 다음 날 다시 지운다
        assert db.get(Application, appId) is not None and db.query(DeletionLog).count() == 0


def test_adminNoticeGroupsByPostingTwoDaysAhead(sessionFactory):
    appId = makeApplication(sessionFactory)
    with sessionFactory() as db:
        base = now().replace(hour=9, minute=0, second=0, microsecond=0)
        db.get(Application, appId).purge_at = base + timedelta(days=2, hours=-6)  # 이틀 뒤 03:00
        db.commit()
        rows = retention.adminNoticeRows(db, ["admin-1", "admin-2"], at=base)
    assert len(rows) == 2 and "1건" in rows[0][2] and rows[0][1] == "purge_notice"


def test_runExamplesGoesThroughSandboxQueue(monkeypatch):
    sent = {}

    class FakeResult:
        def get(self, timeout):
            return {"status": "ok", "results": []}

        def forget(self):
            sent["forgot"] = True

    def sendTask(name, args, queue, expires, retry):
        sent.update(name=name, queue=queue)
        return FakeResult()
    monkeypatch.setattr(worker.celery, "send_task", sendTask)
    assert coding.runExamples("def solution(): pass", [("1", "1")])["status"] == "ok"
    assert sent == {"name": worker.SANDBOX_RUN_TASK, "queue": "sandbox", "forgot": True}


def test_runExamplesTimeoutIsInfraError(monkeypatch):
    class Slow:
        def get(self, timeout):
            raise TimeoutError()

        def forget(self):
            pass
    monkeypatch.setattr(worker.celery, "send_task", lambda *a, **k: Slow())
    try:
        coding.runExamples("x", [("1", "1")])
    except sandbox_runner.SandboxInfraError:
        pass
    else:
        raise AssertionError("expected SandboxInfraError")


def test_enqueueGradeOncePerWindow(monkeypatch):
    monkeypatch.setattr(worker, "_redis", fakeredis.FakeRedis())
    calls = []
    monkeypatch.setattr(worker.celery, "send_task", lambda name, args, queue, retry: calls.append((name, queue)))
    worker.enqueueGrade("app-1")
    worker.enqueueGrade("app-1")
    assert calls == [(worker.GRADE_TASK, "sandbox")]


def test_purgeUnscoredAfterPostingReleasePlusSeven(sessionFactory, monkeypatch):
    monkeypatch.setattr(storage, "deletePrefix", lambda prefix: 0)
    from app.domain import status as st
    from app.models import JobPosting
    drafting = makeApplication(sessionFactory, status=st.DRAFTING)
    review = makeApplication(sessionFactory, email="lee@example.com")
    with sessionFactory() as db:
        for appId in (drafting, review):
            app = db.get(Application, appId)
            db.get(JobPosting, app.posting_id).release_at = now() - timedelta(days=8)
        db.get(Application, review).analysis_status = "needs_review"  # 확인 필요 건은 관리자가 처리할 때까지 남긴다
        db.commit()
        assert retention.purgeDue(db) == [drafting]


def test_brokerDownIsInfraError(monkeypatch):
    def down(*args, **kwargs):
        raise ConnectionError("redis down")
    monkeypatch.setattr(worker.celery, "send_task", down)
    try:
        coding.runExamples("x", [("1", "1")])
    except sandbox_runner.SandboxInfraError:
        pass
    else:
        raise AssertionError("expected SandboxInfraError")


def test_regradeSkipsAlreadyGraded(sessionFactory, monkeypatch):
    calls = []
    monkeypatch.setattr(coding, "SessionLocal", sessionFactory)
    monkeypatch.setattr(sandbox_runner, "run", lambda code, cases: calls.append(code) or {"status": "ok", "results": []})
    appId = makeApplication(sessionFactory, codingEnabled=True, coding=[(3, 5, "ok"), (0, 0, "infra_error")])
    coding.gradeAll(appId)
    assert len(calls) == 1


def test_consentSubjectIsKeyedHash():
    import hashlib

    from app.crypto import subjectHash
    assert subjectHash("Kim@Example.com ") == subjectHash("kim@example.com")
    assert subjectHash("kim@example.com") != hashlib.sha256(b"kim@example.com").hexdigest()
