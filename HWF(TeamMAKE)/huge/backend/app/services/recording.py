"""카메라 녹화 조각 저장·재생·보관 기한 (API 명세서 6장·2-6, 테이블 정의서 4-10). 녹화는 평가에 쓰지 않는다."""

import logging
from datetime import timedelta

from sqlalchemy.orm import Session

from ..domain import status as st
from ..errors import ApiError
from ..models import Application, InterviewSession, Recording, SessionEvent
from ..timeutil import asKst, now
from . import storage

RETENTION_DAYS = 3  # 응시 끝 + 3일
CHUNK_MAX_BYTES = 5 * 1024 * 1024  # 10초 조각 (화면은 약 300kbps 로 녹화)
SEGMENT_MAX_BYTES = 400 * 1024 * 1024
FINISH_GRACE_SEC = 60  # 응시가 끝난 직후 마지막 조각은 받는다
WEBM_MAGIC = b"\x1a\x45\xdf\xa3"  # EBML 머리글
SERVER_FAULT_LOOKBACK_SEC = 60  # 화면은 1·2·4초 간격으로 다시 올린 뒤 실패를 알린다

log = logging.getLogger("huge.recording")


def chunkKey(fileKey: str, chunkNo: int) -> str:
    return f"{fileKey}{chunkNo:05d}.webm"


def baseExpiry(app: Application):
    """응시가 끝났으면 끝난 시각, 아직이면 마감 시각(가장 늦게 끝날 수 있는 시각) + 3일."""
    end = app.completed_at or app.posting.close_at or now()
    return asKst(end) + timedelta(days=RETENTION_DAYS)


def expiresAt(rec: Recording, app: Application):
    """기록된 기한과 '끝난 시각 + 3일' 중 이른 쪽. 조각이 더 오지 않아 기록된 기한이 마감 기준으로 남아 있어도 3일에 지운다."""
    return min(asKst(rec.expires_at), baseExpiry(app)) if app.completed_at else asKst(rec.expires_at)


def acceptsUploads(app: Application) -> bool:
    if app.attempt_status in st.IN_PROGRESS:
        return True
    return (app.attempt_status in st.FINAL_STATUSES and app.completed_at is not None
            and now() - asKst(app.completed_at) <= timedelta(seconds=FINISH_GRACE_SEC))


def saveChunk(db: Session, session: InterviewSession, app: Application, segmentNo: int, chunkNo: int, data: bytes) -> None:
    if not acceptsUploads(app):
        raise ApiError(409, "NOT_IN_PROGRESS", "진행 중인 응시가 아닙니다.")
    if segmentNo != session.recording_segment:
        raise ApiError(409, "SEGMENT_MISMATCH", "녹화 구간 번호가 맞지 않습니다.")
    if len(data) > CHUNK_MAX_BYTES:
        raise ApiError(413, "FILE_TOO_LARGE", "녹화 조각이 너무 큽니다.")
    if chunkNo == 0 and not data.startswith(WEBM_MAGIC):
        raise ApiError(400, "INVALID_FILE", "WebM 녹화 조각이 아닙니다.")
    rec = db.query(Recording).filter_by(application_id=app.id, segment_no=segmentNo).with_for_update().first()
    if rec is None:
        rec = Recording(application_id=app.id, segment_no=segmentNo, file_key=f"recordings/{app.id}/{segmentNo}/",
                        last_chunk_no=-1, size_bytes=0, expires_at=baseExpiry(app))
        db.add(rec)
        db.flush()
    if chunkNo <= rec.last_chunk_no:
        db.commit()
        return  # 다시 올린 조각 (응답을 못 받아 재시도). 이미 저장했다
    if rec.size_bytes + len(data) > SEGMENT_MAX_BYTES:
        raise ApiError(413, "FILE_TOO_LARGE", "녹화 용량을 넘었습니다.")
    try:
        storage.putObject(chunkKey(rec.file_key, chunkNo), data, "video/webm")
    except Exception as exc:  # noqa: BLE001 — 저장소 장애는 서버 쪽 탓으로 기록해 둔다 (uploadFailureReason)
        db.rollback()
        log.warning("recording store failed for %s: %s", app.id, type(exc).__name__)
        db.add(SessionEvent(application_id=app.id, session_id=session.id, type="upload_error", detail="storage", judged="info"))
        db.commit()
        raise ApiError(503, "STORAGE_UNAVAILABLE", "녹화를 저장하지 못했습니다. 잠시 뒤 다시 올립니다.") from exc
    rec.last_chunk_no = chunkNo  # 중간 조각이 빠졌으면 재생 때 그 부분만 끊긴다
    rec.size_bytes += len(data)
    rec.last_chunk_at = now()
    rec.expires_at = baseExpiry(app)
    db.commit()


def uploadFailureReason(db: Session, app: Application) -> str:
    """화면이 '녹화 업로드 실패'를 알렸을 때의 장애 사유. 화면이 보낸 원인은 믿지 않고(이어가기 횟수 우회 방지)
    서버가 최근에 저장소 오류를 기록했을 때만 서버 쪽 장애(server_error, 이어가기 횟수에 안 셈)로 본다."""
    since = now() - timedelta(seconds=SERVER_FAULT_LOOKBACK_SEC)
    rows = db.query(SessionEvent.at).filter(SessionEvent.application_id == app.id, SessionEvent.type == "upload_error").all()
    return "server_error" if any(asKst(at) >= since for (at,) in rows) else "upload_failed"


def streamSegment(fileKey: str):
    for key in storage.listKeys(fileKey):
        yield storage.getObject(key)[0]
