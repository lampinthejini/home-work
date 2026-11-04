"""보관 기간이 끝난 면접 데이터 삭제 (PRD 10-2, TRD 4-2·10장, 테이블 정의서 1-6·4-13).

purge_at(결과 공개 + 7일)이 지난 지원 건을 통째로 지운다: 파일(이력서·답변 음성·질문 음성·녹화) → Redis 키 → DB 행.
동의 기록은 증거로 남기고 지원 건과의 연결만 끊는다. 지운 일은 deletion_logs 에 숫자로만 남긴다 (내용은 남기지 않음).
녹화는 따로 응시 끝 + 3일에 지운다 (purgeRecordings).
"""

import logging
from collections import defaultdict
from datetime import timedelta
from decimal import Decimal

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..domain import status as st
from ..interview import checkpoint
from ..models import (
    Answer,
    Application,
    CodingSubmission,
    Consent,
    DeletionLog,
    Highlight,
    InterviewQuestion,
    InterviewSession,
    ItemScore,
    JobPosting,
    Memo,
    Notification,
    Recording,
    Result,
    ResumeUpload,
    SessionEvent,
    StatsArchive,
)
from ..timeutil import asKst, now
from . import recording, storage

log = logging.getLogger("huge.retention")

# 지원 건 아래에서 함께 지워지는 행 (ON DELETE CASCADE). 지운 행 수를 세는 데만 쓴다
CHILD_TABLES = (InterviewQuestion, Answer, InterviewSession, SessionEvent, CodingSubmission, Result, ItemScore, Highlight,
                Notification, ResumeUpload, Memo, Recording)
RETENTION_DAYS = 7
REDIS_KEYS = ("eval:lock:{id}", "eval:since:{id}", "eval:queued:{id}", "grade:queued:{id}", "grade:lock:{id}")
NOTICE_DAYS = 2


def filePrefixes(db: Session, app: Application) -> list[str]:
    prefixes = [f"answers/{app.id}/", f"questions/{app.id}/", f"recordings/{app.id}/"]
    prefixes += [row.file_key for row in db.query(ResumeUpload).filter_by(application_id=app.id)]
    return prefixes


def archiveStats(db: Session, app: Application) -> None:
    """지우기 전에 통계 숫자만 StatsArchive 에 더한다 (CONFLICTS F1). 관리자 통계(/admin/stats)와 같은 기준으로 센다."""
    if app.attempt_status == st.DRAFTING:
        return  # 통계 대상이 아님
    taken = app.attempt_status in st.FINAL_STATUSES - {st.NOT_TAKEN_CLOSED}
    month = asKst(app.completed_at).strftime("%Y-%m") if taken and app.completed_at else ""
    row = db.query(StatsArchive).filter_by(posting_id=app.posting_id, month=month).with_for_update().first()
    if row is None:
        row = StatsArchive(posting_id=app.posting_id, month=month, applications=0, taken=0, decided=0, passed=0,
                           total_sum=Decimal(0), score_bins=[0] * 10, item_sums={}, resumed=0, cheating_cancelled=0)
        db.add(row)
    row.posting_title = app.posting.title
    row.applications += 1
    if not taken:
        return
    row.taken += 1
    sessions = db.query(func.count()).select_from(InterviewSession).filter(InterviewSession.application_id == app.id).scalar() or 0
    row.resumed += max(sessions - 1, 0)
    row.cheating_cancelled += int(app.attempt_status == st.CANCELLED and app.end_detail == "exit_twice")
    result = db.query(Result).filter_by(application_id=app.id).first()
    if result is None or not result.scored:
        return  # 점수가 없는 결과는 점수 통계에 넣지 않는다 (/admin/stats 와 같은 기준)
    total = Decimal(result.total_score)
    row.decided += 1
    row.passed += int(result.ai_decision == "pass")
    row.total_sum = Decimal(row.total_sum) + total
    bins = list(row.score_bins)
    bins[min(int(total) // 10, 9)] += 1
    row.score_bins = bins  # JSON 칸은 새 값을 넣어야 바뀐 것으로 저장된다
    sums = dict(row.item_sums)
    for item, value in (result.item_points or {}).items():
        if value is not None:
            prev, count = sums.get(item, ["0", 0])
            sums[item] = [str(Decimal(prev) + Decimal(str(value))), count + 1]
    row.item_sums = sums


def purgeApplication(db: Session, app: Application, redisClient=None, cause: str = "retention") -> dict:
    """한 지원 건의 면접 데이터를 지우고 삭제 기록을 남긴다. 파일을 먼저 지워 DB 만 지워지고 파일이 남는 일이 없게 한다."""
    files = sum(storage.deletePrefix(prefix) for prefix in filePrefixes(db, app))
    redisKeys = 0
    if redisClient is not None:
        redisKeys = int(redisClient.delete(*[key.format(id=app.id) for key in REDIS_KEYS]) or 0)
    rows = 1 + sum(db.query(func.count()).select_from(table).filter(table.application_id == app.id).scalar() or 0
                   for table in CHILD_TABLES)
    db.query(Consent).filter_by(application_id=app.id).update({Consent.application_id: None})  # 동의는 증거로 남김
    checkpoints = checkpoint.deleteThread(db, app.id)  # LangGraph 체크포인트 (thread_id = 지원 번호, AI 아키텍처 7장)
    items = {"db_rows": rows, "files": files, "redis_keys": redisKeys, "checkpoints": checkpoints}
    db.add(DeletionLog(application_id=app.id, cause=cause, scope="interview_data", deleted_items=items))
    # 동의 철회·탈퇴는 응시가 끝난 건만 익명 숫자로 남긴다 (끝나지 않은 응시는 통계에 넣지 않음)
    if cause == "retention" or app.attempt_status in st.FINAL_STATUSES:
        archiveStats(db, app)
    db.delete(app)
    db.commit()
    return items


def purgeRecordings(db: Session, at=None) -> int:
    """보관 기한(응시 끝 + 3일)이 지난 녹화 파일·행을 지운다. 지원 건은 남긴다. 실패한 건은 다음 날 다시."""
    at = at or now()
    candidates = (db.query(Recording, Application).join(Application, Application.id == Recording.application_id)
                  .filter((Recording.expires_at <= at) | (Application.completed_at <= at - timedelta(days=recording.RETENTION_DAYS))).all())
    done = 0
    for rec, app in candidates:
        if recording.expiresAt(rec, app) > at:
            continue
        try:
            files = storage.deletePrefix(rec.file_key)
            db.add(DeletionLog(application_id=app.id, cause="retention", scope="recording",
                               deleted_items={"files": files, "segment_no": rec.segment_no}))
            db.delete(rec)
            db.commit()
            done += 1
        except Exception as exc:  # noqa: BLE001
            db.rollback()
            log.warning("recording purge failed for %s: %s", app.id, type(exc).__name__)
    return done


# 채점을 거치지 않아 purge_at 이 없는 상태: 작성 중 · 준비 중 · 미응시 마감. 공고의 1차 결과 공개일 + 7일에 함께 지운다 (PRD 10-2)
UNSCORED_STATUSES = (st.DRAFTING, st.READY, st.NOT_TAKEN_CLOSED)


def purgeDue(db: Session, redisClient=None, at=None) -> list[str]:
    """purge_at 이 지난 지원 건을 지운다. 한 건이 실패해도 다음 건은 계속 지운다 (다음 날 다시 시도).
    '확인 필요' 건은 purge_at 이 없어 지우지 않는다 — 결과가 정해질 때(최대 7일, CONFLICTS U8) 삭제일도 정해진다."""
    at = at or now()
    ids = [appId for (appId,) in db.query(Application.id).filter(Application.purge_at.is_not(None), Application.purge_at <= at)]
    ids += [appId for (appId,) in db.query(Application.id).join(JobPosting, JobPosting.id == Application.posting_id)
            .filter(Application.purge_at.is_(None), Application.attempt_status.in_(UNSCORED_STATUSES),
                    JobPosting.release_at.is_not(None), JobPosting.release_at <= at - timedelta(days=RETENTION_DAYS))]
    done = []
    for appId in ids:
        app = db.get(Application, appId)
        if app is None:
            continue
        try:
            purgeApplication(db, app, redisClient)
            done.append(appId)
        except Exception as exc:  # noqa: BLE001 — 실패한 건은 다음 날 다시 지운다
            db.rollback()
            log.warning("purge failed for %s: %s", appId, type(exc).__name__)
    return done


def adminNoticeRows(db: Session, adminIds: list[str], at=None) -> list[tuple]:
    """삭제 2일 전 관리자 안내: 그날 삭제될 건을 공고별로 묶어 한 통씩 (TRD 10장, 매일 09:00)."""
    at = asKst(at or now())
    start = at.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=NOTICE_DAYS)
    counts: dict[str, int] = defaultdict(int)
    for app in db.query(Application).filter(Application.purge_at >= start, Application.purge_at < start + timedelta(days=1)):
        counts[app.posting_id] += 1
    rows = []
    for postingId, count in counts.items():
        posting = db.get(JobPosting, postingId)
        title = f"[{posting.title}] 지원 {count}건의 면접 데이터가 {start.month}월 {start.day}일에 삭제됩니다"
        rows += [(adminId, "purge_notice", title, f"/admin/applicants?posting={postingId}", None) for adminId in adminIds]
    return rows
