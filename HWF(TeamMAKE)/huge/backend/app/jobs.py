"""1분마다 도는 정리 작업 (1단계: api 안 asyncio 작업, 2단계에서 Celery beat 로 옮긴다).

- 장애 중단 뒤 disconnect_seat_hold_min 이 지나면 자리 반환 (TRD 5-3)
- 마감 시각이 지난 게시 공고 자동 마감 (INT-10)
- Redis 동시 면접 수를 holds_seat 기준으로 다시 맞춤
"""

import asyncio
import logging
from datetime import timedelta

from .db import SessionLocal
from .domain import status as st
from .interview import lifecycle, registry
from .models import Application, CodingSubmission, InterviewSession, JobPosting
from .services import admission, coding
from .services.postings import closePosting
from .settings_store import getSetting
from .timeutil import asKst, now

log = logging.getLogger("huge.jobs")
INTERVAL_SEC = 60
ORPHAN_GRACE_SEC = 90  # 시작 API 뒤 면접 화면이 연결되기까지 기다리는 시간


def releaseHeldSeats(db) -> None:
    holdMin = getSetting(db, "disconnect_seat_hold_min")
    for app in db.query(Application).filter(Application.attempt_status == st.INTERRUPTED, Application.holds_seat.is_(True)).all():
        if app.interrupted_at and asKst(app.interrupted_at) + timedelta(minutes=holdMin) <= now():
            admission.release(db, app)


def sweepOrphans(db) -> None:
    """진행 중인데 붙어 있는 면접 세션이 없는 지원 (재시작·연결 한 번도 안 됨) → 장애 중단으로 돌린다.

    원인을 알 수 없으므로 지원자에게 유리하게 장애로 본다 (TRD 7-2 '원인 미상'). 자리는 releaseHeldSeats 가 돌려준다.
    """
    graceStart = now() - timedelta(seconds=ORPHAN_GRACE_SEC)
    for app in db.query(Application).filter(Application.attempt_status.in_(st.IN_PROGRESS)).all():
        if registry.get(app.id) is not None:
            continue
        last = db.query(InterviewSession).filter_by(application_id=app.id).order_by(InterviewSession.created_at.desc()).first()
        if last is not None and asKst(last.created_at) > graceStart and last.ended_at is None:
            continue
        lifecycle.markInterrupted(db, app, "unknown")
        log.info("orphaned attempt %s marked interrupted", app.id)


def regradePending() -> None:
    """끝난 응시인데 채점되지 않은(마감·종료로 끝났거나 인프라 오류) 코딩 답안을 다시 채점한다."""
    db = SessionLocal()
    try:
        rows = (db.query(CodingSubmission.application_id).join(Application, Application.id == CodingSubmission.application_id)
                .filter(Application.attempt_status.in_(coding.GRADED_STATUSES),
                        (CodingSubmission.grade_status.is_(None)) | (CodingSubmission.grade_status == "infra_error"))
                .distinct().all())
    finally:
        db.close()
    for (applicationId,) in rows:
        coding.scheduleGrade(applicationId)


async def closeExpiredPostings(db) -> None:
    for posting in db.query(JobPosting).filter(JobPosting.status == "published", JobPosting.close_at <= now()).all():
        result = closePosting(db, posting)
        await registry.terminateMany(result["live_application_ids"], "closed")
        log.info("auto-closed posting %s", posting.id)


async def runForever() -> None:
    while True:
        db = SessionLocal()
        try:
            sweepOrphans(db)
            releaseHeldSeats(db)
            await closeExpiredPostings(db)
            admission.reconcile(db)
            regradePending()
        except Exception:
            log.exception("periodic job failed")
            db.rollback()
        finally:
            db.close()
        await asyncio.sleep(INTERVAL_SEC)
