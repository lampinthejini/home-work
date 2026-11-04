"""Celery worker · beat (TRD 3장 Celery 5 + Redis, AI 아키텍처 v1.4 7장).

큐: evaluate (채점, 동시 1개 — GPU·CPU 모델을 넘치게 쓰지 않음) · default (메일·삭제) ·
    sandbox (코드 실행 상자. docker.sock 은 이 worker 만 가진다 — ADR-09, R-06).
실행: celery -A app.worker worker -Q evaluate -c 1 / -Q default / -Q sandbox -c 2 · celery -A app.worker beat
정해진 시각 작업은 모두 한국 시간.
  5분마다: 끝났는데 채점이 없거나 멈춘 건 다시 넣기(AC-17) · 공개 시각이 지난 결과 공개
           평가 지연 건 6시간마다 재채점, 3일 뒤 재채점까지 실패하면(늦어도 7일) 평가 미완료 불합격
  매시 정각: 마감 3일·1일 전 미응시 안내 · 결과 보기 끝나기 2일 전 안내 · 마감 1일 전 관리자 안내
  매시 30분: 응시 끝 + 3일이 지난 녹화 삭제
  매일 03:00: 보관 기간이 지난 면접 데이터 삭제 · 매일 09:00: 이틀 뒤 삭제될 건 관리자 안내 (공고별 한 통)
"""

import asyncio
import logging
import uuid
from datetime import datetime, timedelta

import redis
from celery import Celery
from celery.schedules import crontab
from celery.signals import after_setup_logger

from . import db as dbModule
from .config import ENV
from .domain import status as st
from .models import Application, JobPosting, Result
from .services import coding, evaluation, llm, login_block, notify, retention, sandbox_runner
from .timeutil import asKst, now

log = logging.getLogger("huge.worker")

EVAL_TASK = "huge.evaluate"
MAIL_TASK = "huge.sendMail"
RESET_MAIL_TASK = "huge.sendResetMail"
SANDBOX_RUN_TASK = "huge.sandboxRun"
GRADE_TASK = "huge.gradeCoding"
GRADE_QUEUED_SEC = 300
RETRY_DELAYS_SEC = (60, 120, 240)  # 1·2·4분 (TRD 8-3)
EVAL_DEADLINE_MIN = 30
AI_DOWN_DELAY_SEC = 60
CODING_WAIT_SEC = 30
LOCK_TTL_SEC = 40 * 60
QUEUED_GRACE_SEC = 120
SWEEP_LAST_KEY = "sweep:last"
SWEEP_GRACE_KEY = "sweep:grace"  # 서비스가 멈췄다 돌아온 뒤 관리자에게 주는 시간
SWEEP_GAP_SEC = 3600  # 5분 점검이 이만큼 안 돌았으면 서비스가 멈춰 있던 것으로 본다
DOWN_GRACE_SEC = 24 * 3600

celery = Celery("huge", broker=ENV.redisUrl)
celery.conf.update(
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    broker_transport_options={"visibility_timeout": 3600},  # 가장 긴 작업(30분)보다 길게
    broker_connection_retry_on_startup=True,
    # [실행] 결과만 api 가 기다려 받는다. 나머지 작업은 결과를 저장하지 않는다
    result_backend=ENV.redisUrl,
    task_ignore_result=True,
    result_expires=600,
    timezone="Asia/Seoul",
    enable_utc=False,
    task_default_queue="default",
    task_routes={EVAL_TASK: {"queue": "evaluate"}, MAIL_TASK: {"queue": "default"}, RESET_MAIL_TASK: {"queue": "default"},
                 SANDBOX_RUN_TASK: {"queue": "sandbox"}, GRADE_TASK: {"queue": "sandbox"}},
    beat_schedule={
        "sweep": {"task": "huge.sweep", "schedule": 300.0},
        "hourly-reminders": {"task": "huge.reminders", "schedule": crontab(minute=0)},
        "purge": {"task": "huge.purge", "schedule": crontab(hour=3, minute=0)},
        "purge-notice": {"task": "huge.purgeNotice", "schedule": crontab(hour=9, minute=0)},
        "purge-recordings": {"task": "huge.purgeRecordings", "schedule": crontab(minute=30)},
    },
)
_redis = redis.Redis.from_url(ENV.redisUrl)


@after_setup_logger.connect
def quietTaskResults(**_kwargs) -> None:
    """'작업 성공: <결과>' 줄에 지원자 코드 실행 결과가 찍히지 않게 한다 (TRD 11장: 로그에 답변 원문 금지)."""
    logging.getLogger("celery.app.trace").setLevel(logging.WARNING)


def enqueueEvaluation(applicationId: str, attempt: int = 1, countdown: int = 0) -> None:
    """DB 커밋 뒤에 부른다. 브로커가 안 되면 기록만 남기고 5분 점검이 다시 넣는다."""
    try:
        celery.send_task(EVAL_TASK, args=[applicationId], kwargs={"attempt": attempt}, countdown=countdown or None,
                         queue="evaluate", retry=False)
    except Exception as exc:  # noqa: BLE001
        log.warning("evaluation enqueue failed for %s: %s", applicationId, type(exc).__name__)


def queueMail(notificationId: str, countdown: int = 0) -> None:
    try:
        celery.send_task(MAIL_TASK, args=[notificationId], countdown=countdown or None, queue="default", retry=False)
    except Exception as exc:  # noqa: BLE001
        log.warning("mail enqueue failed for %s: %s", notificationId, type(exc).__name__)


def queueResetMail(email: str, link: str, attempt: int = 0) -> None:
    """비밀번호 재설정 메일. 링크(토큰)는 로그에 남기지 않는다."""
    countdown = notify.RETRY_DELAYS_SEC[attempt - 1] if attempt else None
    try:
        celery.send_task(RESET_MAIL_TASK, args=[email, link], kwargs={"attempt": attempt}, countdown=countdown,
                         queue="default", retry=False)
    except Exception as exc:  # noqa: BLE001
        log.warning("reset mail enqueue failed: %s", type(exc).__name__)


def notifyMany(rows: list[tuple]) -> None:
    """[(user_id, kind, title, link, application_id)] 알림을 만들고 커밋 뒤 메일을 넣는다."""
    if not rows:
        return
    db = dbModule.SessionLocal()
    try:
        created = [notify.create(db, *row).id for row in rows]
        db.commit()
    finally:
        db.close()
    for notificationId in created:
        queueMail(notificationId)


def lockKey(applicationId: str) -> str:
    return f"eval:lock:{applicationId}"


def sinceKey(applicationId: str) -> str:
    return f"eval:since:{applicationId}"


def queuedKey(applicationId: str) -> str:
    """다시 넣어 둔 작업이 기다리는 중 — 5분 점검이 같은 건을 또 넣지 않게."""
    return f"eval:queued:{applicationId}"


def releaseLock(applicationId: str, token: str) -> None:
    """내가 건 잠금만 푼다 (다른 작업의 잠금을 지우지 않게)."""
    held = _redis.get(lockKey(applicationId))
    if held is not None and held.decode() == token:
        _redis.delete(lockKey(applicationId))


def evaluationStartedAt(applicationId: str, completedAt) -> object:
    """30분 한도를 재는 기준 시각: 다시 돌리기를 눌렀으면 그때, 아니면 응시 끝난 때."""
    raw = _redis.get(sinceKey(applicationId))
    if raw:
        return datetime.fromisoformat(raw.decode())
    return asKst(completedAt) or now()


def toNeedsReview(applicationId: str, reason: str) -> None:
    if evaluation.markNeedsReview(applicationId, reason):
        log.warning("application %s needs review: %s", applicationId, reason)
        db = dbModule.SessionLocal()
        try:
            # 자동 재채점이 또 실패해도 같은 건을 다시 알리지 않는다
            rows = [(adminId, "needs_review", "평가가 지연된 지원 건이 있습니다", f"/admin/applicants/{applicationId}", applicationId)
                    for adminId in notify.adminIds(db) if not notify.exists(db, adminId, "needs_review", applicationId)]
        finally:
            db.close()
        notifyMany(rows)


@celery.task(name=EVAL_TASK, bind=True)
def evaluateTask(self, applicationId: str, attempt: int = 1) -> str:
    token = uuid.uuid4().hex
    if not _redis.set(lockKey(applicationId), token, nx=True, ex=LOCK_TTL_SEC):
        return "locked"
    _redis.delete(queuedKey(applicationId))
    try:
        db = dbModule.SessionLocal()
        try:
            app = db.get(Application, applicationId)
            completedAt = app.completed_at if app else None
        finally:
            db.close()
        overdue = now() - evaluationStartedAt(applicationId, completedAt) > timedelta(minutes=EVAL_DEADLINE_MIN)
        try:
            outcome = asyncio.run(evaluation.evaluate(applicationId))
        except evaluation.NeedsReview as exc:
            toNeedsReview(applicationId, exc.reason)
            return "needs_review"
        except evaluation.AiUnavailable as exc:
            if overdue:
                toNeedsReview(applicationId, "analysis_timeout")
                return "needs_review"
            log.info("ai unavailable (%s), evaluation of %s postponed", exc, applicationId)
            reschedule(applicationId, attempt, AI_DOWN_DELAY_SEC)
            return "postponed"
        except Exception as exc:  # noqa: BLE001 — EvalFailed·DB 오류 모두 시도 1회로 센다
            log.warning("evaluation attempt %d failed for %s: %s", attempt, applicationId, exc)
            if attempt > len(RETRY_DELAYS_SEC) or overdue:
                toNeedsReview(applicationId, "analysis_timeout")
                return "needs_review"
            reschedule(applicationId, attempt + 1, RETRY_DELAYS_SEC[attempt - 1])
            return "retry"
        if outcome == "waiting_coding":
            if overdue:
                toNeedsReview(applicationId, "sandbox_error")
                return "needs_review"
            reschedule(applicationId, attempt, CODING_WAIT_SEC)
        return outcome
    finally:
        releaseLock(applicationId, token)


def reschedule(applicationId: str, attempt: int, delaySec: int) -> None:
    _redis.set(queuedKey(applicationId), "1", ex=delaySec + QUEUED_GRACE_SEC)
    enqueueEvaluation(applicationId, attempt, delaySec)


@celery.task(name=MAIL_TASK)
def sendMailTask(notificationId: str) -> str:
    try:
        return notify.sendNow(notificationId)
    except notify.MailRetry as retry:
        queueMail(notificationId, int(retry.args[0]))
        return "retry"


@celery.task(name=RESET_MAIL_TASK)
def sendResetMailTask(email: str, link: str, attempt: int = 0) -> str:
    body = (f"비밀번호 재설정을 요청하셨습니다. 아래 주소에서 30분 안에 새 비밀번호를 정해 주세요.\n{link}\n\n"
            "요청하지 않으셨다면 이 메일을 무시해 주세요. 비밀번호는 바뀌지 않습니다.\n\n— Huge 채용 (Team AIIT)")
    try:
        return notify.sendPlain(email, "비밀번호 재설정 안내", body)
    except notify.MailRetry:
        if attempt >= len(notify.RETRY_DELAYS_SEC):
            log.warning("reset mail failed after retries")
            return "failed"
        queueResetMail(email, link, attempt + 1)
        return "retry"


def findUnscored(db) -> list[str]:
    """응시는 끝났는데 결과가 없고 작업도 돌고 있지 않은 건 (AC-17)."""
    rows = (db.query(Application.id).outerjoin(Result, Result.application_id == Application.id)
            .filter(Application.attempt_status.in_(st.FINAL_STATUSES - {st.NOT_TAKEN_CLOSED}),
                    Application.analysis_status.in_(("pending", "running")), Result.id.is_(None)).all())
    return [appId for (appId,) in rows if not _redis.exists(lockKey(appId)) and not _redis.exists(queuedKey(appId))]


def releaseDue(db) -> list[str]:
    """공개 시각이 지난 확정 결과를 공개로 바꾸고, 같은 트랜잭션에서 지원자 알림을 만든다 (RPT-02).
    돌려주는 값은 메일을 보낼 알림 id."""
    created = []
    for app in (db.query(Application).filter(Application.analysis_status == "decided",
                                              Application.release_status.in_(("scheduled", "delayed")),
                                              Application.release_at <= now()).all()):
        app.release_status = "released"
        created.append(notify.create(db, app.user_id, "result_released", f"[{app.posting.title}] 1차 결과가 공개되었습니다",
                                     f"/mypage/results/{app.id}", app.id))
    db.commit()
    return [n.id for n in created]


def noteSweep() -> bool:
    """이번 점검 시각을 남긴다. 서비스가 멈췄다 돌아온 지 24시간 안이면 True."""
    current = now()
    last = _redis.get(SWEEP_LAST_KEY)
    if last is None or (current - datetime.fromisoformat(last.decode())).total_seconds() > SWEEP_GAP_SEC:
        _redis.set(SWEEP_GRACE_KEY, "1", ex=DOWN_GRACE_SEC)
    _redis.set(SWEEP_LAST_KEY, current.isoformat())
    return bool(_redis.exists(SWEEP_GRACE_KEY))


def aiReady() -> bool:
    return all(asyncio.run(llm.health(lane=lane)) for lane in ("rt", "eval"))


def settleReviews(db) -> tuple[list[str], list[str]]:
    """평가 지연 건을 재채점하거나 닫는다. (닫은 건, 다시 넣을 건). 재채점 건의 사유·시각은 남겨 기한이 늘어나지 않게 한다.

    AI 가 멈췄거나 PC 가 꺼져 있었던 일로 재채점 기회 없이 불합격되지 않게, 기한이 지나도 AI 가 정상일 때
    재채점까지 실패해야 닫는다. 채점 지시 의심 건은 재채점하지 않고, 멈췄다 돌아온 뒤 관리자에게 24시간을 더 준다.
    """
    recovering = noteSweep()
    rows = db.query(Application).filter(Application.analysis_status == "needs_review", Application.needs_review_since.is_not(None)).with_for_update().all()
    current = now()
    ready = aiReady() if any(a.review_reason != evaluation.INSTRUCTION_REASON for a in rows) else False
    closed, retried = [], []
    for app in rows:
        age = current - asKst(app.needs_review_since)
        overdue = age >= timedelta(days=evaluation.REVIEW_DEADLINE_DAYS)
        if age >= timedelta(days=evaluation.REVIEW_LIMIT_DAYS):
            close = True
        elif app.review_reason == evaluation.INSTRUCTION_REASON:
            close = overdue and not recovering
        else:
            key = f"eval:review-retry:{app.id}"
            if not ready or age < timedelta(hours=evaluation.REVIEW_RETRY_HOURS):
                continue
            close = overdue and bool(_redis.exists(key))
            if not close and _redis.set(key, "1", nx=True, ex=evaluation.REVIEW_RETRY_HOURS * 3600):
                app.analysis_status = "pending"
                retried.append(app.id)
        if close and evaluation.closeIncomplete(db, app):
            closed.append(app.id)
    db.commit()
    return closed, retried


@celery.task(name="huge.sweep")
def sweepTask() -> dict:
    db = dbModule.SessionLocal()
    try:
        closed, retried = settleReviews(db)
        missing = [appId for appId in findUnscored(db) if appId not in retried]
        released = releaseDue(db)
        closedRows = [(adminId, "needs_review", "평가를 끝내지 못한 지원 건이 불합격 처리되었습니다", f"/admin/applicants/{appId}", appId)
                      for appId in closed for adminId in notify.adminIds(db)]
    finally:
        db.close()
    notifyMany(closedRows)
    for appId in retried:
        requestReprocess(appId)
    for appId in missing:
        enqueueEvaluation(appId)
    for notificationId in released:
        queueMail(notificationId)
    return {"requeued": len(missing), "released": len(released), "retried": len(retried), "auto_failed": len(closed)}


def reminderRows(db) -> list[tuple]:
    rows = []
    current = now()
    for posting in db.query(JobPosting).filter(JobPosting.status == "published", JobPosting.close_at.is_not(None)).all():
        left = asKst(posting.close_at) - current
        for days in (3, 1):
            if timedelta(days=days) - timedelta(hours=1) < left <= timedelta(days=days):
                title = f"[{posting.title}] 접수 마감 {days}일 전입니다. 응시를 마쳐 주세요"
                for app in db.query(Application).filter(Application.posting_id == posting.id,
                                                        Application.attempt_status.in_((st.DRAFTING, st.READY, st.INTERRUPTED))):
                    if not notify.exists(db, app.user_id, "deadline_reminder", app.id, title):
                        rows.append((app.user_id, "deadline_reminder", title, "/mypage", app.id))
                if days == 1:
                    adminTitle = f"[{posting.title}] 내일 접수가 마감됩니다"
                    for adminId in notify.adminIds(db):
                        if not notify.exists(db, adminId, "posting_closing", None, adminTitle):
                            rows.append((adminId, "posting_closing", adminTitle, f"/admin/applicants?posting={posting.id}", None))
    for app in db.query(Application).filter(Application.analysis_status == "needs_review", Application.needs_review_since.is_not(None)).all():
        left = evaluation.reviewDeadline(app) - current
        title = f"[{app.posting.title}] 평가 지연 건을 24시간 안에 결정하지 않으면 불합격 처리될 수 있습니다"
        if timedelta(0) < left <= timedelta(days=1):
            rows += [(adminId, "needs_review", title, f"/admin/applicants/{app.id}", app.id)
                     for adminId in notify.adminIds(db) if not notify.exists(db, adminId, "needs_review", app.id, title)]
    for app in db.query(Application).filter(Application.release_status == "released", Application.purge_at.is_not(None)).all():
        left = asKst(app.purge_at) - current
        if timedelta(days=2) - timedelta(hours=1) < left <= timedelta(days=2) and not notify.exists(db, app.user_id, "result_expiring", app.id):
            rows.append((app.user_id, "result_expiring", f"[{app.posting.title}] 결과 보기가 2일 뒤 끝납니다",
                         f"/mypage/results/{app.id}", app.id))
    return rows


@celery.task(name="huge.reminders")
def remindersTask() -> int:
    db = dbModule.SessionLocal()
    try:
        rows = reminderRows(db)
    finally:
        db.close()
    notifyMany(rows)
    return len(rows)


def gradeQueuedKey(applicationId: str) -> str:
    return f"grade:queued:{applicationId}"


def enqueueGrade(applicationId: str) -> None:
    """코딩 숨겨진 테스트 채점. 5분 안에 같은 건을 또 넣지 않는다 (인프라 오류면 5분 뒤 점검이 다시 넣음)."""
    try:
        if not _redis.set(gradeQueuedKey(applicationId), "1", nx=True, ex=GRADE_QUEUED_SEC):
            return
        celery.send_task(GRADE_TASK, args=[applicationId], queue="sandbox", retry=False)
    except Exception as exc:  # noqa: BLE001 — 5분 점검(regradePending)이 다시 넣는다
        log.warning("grading enqueue failed for %s: %s", applicationId, type(exc).__name__)


@celery.task(name=SANDBOX_RUN_TASK, ignore_result=False)
def sandboxRunTask(code: str, cases: list[list[str]]) -> dict:
    try:
        return sandbox_runner.run(code, [tuple(c) for c in cases])
    except sandbox_runner.SandboxBusy:
        return {"infra": "busy"}
    except sandbox_runner.SandboxInfraError as exc:
        return {"infra": str(exc) or "down"}


@celery.task(name=GRADE_TASK)
def gradeCodingTask(applicationId: str) -> str:
    token = uuid.uuid4().hex
    key = f"grade:lock:{applicationId}"
    if not _redis.set(key, token, nx=True, ex=600):
        return "locked"
    try:
        coding.gradeAll(applicationId)
        return "graded"
    finally:
        held = _redis.get(key)
        if held is not None and held.decode() == token:
            _redis.delete(key)


@celery.task(name="huge.purge")
def purgeTask() -> int:
    db = dbModule.SessionLocal()
    try:
        done = retention.purgeDue(db, _redis)
        login_block.purgeExpired(db)
        db.commit()
    finally:
        db.close()
    log.info("purged %d applications", len(done))
    return len(done)


@celery.task(name="huge.purgeRecordings")
def purgeRecordingsTask() -> int:
    db = dbModule.SessionLocal()
    try:
        done = retention.purgeRecordings(db)
    finally:
        db.close()
    if done:
        log.info("purged %d recordings", done)
    return done


@celery.task(name="huge.purgeNotice")
def purgeNoticeTask() -> int:
    db = dbModule.SessionLocal()
    try:
        rows = [row for row in retention.adminNoticeRows(db, notify.adminIds(db))
                if not notify.exists(db, row[0], row[1], None, row[2])]
    finally:
        db.close()
    notifyMany(rows)
    return len(rows)


def requestReprocess(applicationId: str) -> None:
    """관리자 '다시 돌리기': 30분 한도를 지금부터 다시 잰다."""
    _redis.set(sinceKey(applicationId), now().isoformat(), ex=24 * 3600)
    _redis.delete(queuedKey(applicationId))
    enqueueEvaluation(applicationId)
