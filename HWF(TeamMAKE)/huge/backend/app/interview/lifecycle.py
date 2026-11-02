"""응시 상태를 바꾸는 공통 동작. 면접 세션(WebSocket)·HTTP API·주기 작업이 같은 함수를 쓴다.

상태 원장은 applications.attempt_status (TRD 7-5). 자리 반환은 admission 이 holds_seat 와 함께 처리한다.
"""

import io
import wave
from datetime import timedelta

from sqlalchemy.orm import Session

from ..domain import status as st
from ..models import Application, CodingSubmission, SessionEvent
from ..services import admission, coding_bank
from ..settings_store import getSetting
from ..timeutil import asKst, now


def logEvent(db: Session, app: Application, type_: str, detail: str | None = None, judged: str | None = None,
             sessionId: str | None = None, seq: int | None = None) -> None:
    db.add(SessionEvent(application_id=app.id, session_id=sessionId, type=type_, detail=(detail or "")[:2000] or None,
                        judged=judged, seq=seq))


def recentEventTypes(db: Session, app: Application, lookbackSec: int) -> set[str]:
    since = now() - timedelta(seconds=lookbackSec)
    rows = db.query(SessionEvent.type, SessionEvent.at).filter(SessionEvent.application_id == app.id).all()
    return {t for t, at in rows if asKst(at) >= since}


def pauseCodingTimer(app: Application) -> None:
    if app.phase == "coding" and app.coding_started_at is not None and app.coding_remaining_sec is not None:
        elapsed = (now() - asKst(app.coding_started_at)).total_seconds()
        app.coding_remaining_sec = max(0, int(app.coding_remaining_sec - elapsed))
        app.coding_started_at = None


def codingRemaining(app: Application) -> int | None:
    if app.coding_remaining_sec is None:
        return None
    if app.coding_started_at is None:
        return app.coding_remaining_sec
    return max(0, int(app.coding_remaining_sec - (now() - asKst(app.coding_started_at)).total_seconds()))


# 서버 쪽 원인(서버 오류·재시작 등 원인 미상)은 이어가기 횟수에 넣지 않는다
SERVER_SIDE_REASONS = ("server_error", "unknown")


def applicantInterruptions(db: Session, app: Application) -> int:
    return (db.query(SessionEvent).filter(SessionEvent.application_id == app.id, SessionEvent.type == "interrupted",
                                          SessionEvent.detail.notin_(SERVER_SIDE_REASONS)).count())


def resumesLeft(db: Session, app: Application) -> int:
    return max(getSetting(db, "resume_limit") - applicantInterruptions(db, app), 0)


def markInterrupted(db: Session, app: Application, reason: str) -> bool:
    """장애 중단: 시간을 멈추고 자리는 disconnect_seat_hold_min 동안 맡아 둔다 (TRD 7-2).
    지원자 쪽 끊김으로 이어가기를 resume_limit 번 다 썼으면 응시를 종료한다 (CONFLICTS D1). 중단이면 True, 종료면 False."""
    if reason not in SERVER_SIDE_REASONS and resumesLeft(db, app) == 0:
        logEvent(db, app, "resume_limit", reason, judged="not_fault")
        finish(db, app, st.ENDED, "resume_limit")
        return False
    pauseCodingTimer(app)
    app.attempt_status = st.transition(app.attempt_status, st.INTERRUPTED)
    app.interrupted_at = now()
    app.interruption_reason = reason
    app.interruption_judged = "fault"
    logEvent(db, app, "interrupted", reason, judged="fault")
    db.commit()
    return True


def finish(db: Session, app: Application, target: str, detail: str | None = None) -> None:
    """응시 완료·종료·취소·마감 종료. 자리 반환까지 한다."""
    pauseCodingTimer(app)
    app.attempt_status = st.transition(app.attempt_status, target)
    app.completed_at = now()
    app.end_detail = detail
    if target == st.ENDED:
        app.interruption_judged = "not_fault"
    db.commit()
    admission.release(db, app)
    queueEvaluation(app.id)


def queueEvaluation(applicationId: str) -> None:
    """채점 작업을 커밋 뒤에 넣는다 (2단계 Celery). 빠지면 worker 의 5분 점검이 다시 넣는다."""
    from .. import worker

    worker.enqueueEvaluation(applicationId)


def enterCoding(db: Session, app: Application) -> None:
    """AI 면접이 끝나 코딩테스트로: 자리를 돌려주고(코딩은 GPU 를 안 씀) 문제를 배정한다 (TRD 5-3)."""
    app.attempt_status = st.transition(app.attempt_status, st.CODING)
    app.phase = "coding"
    if app.coding_remaining_sec is None:
        app.coding_remaining_sec = getSetting(db, "coding_limit_sec")
        app.coding_started_at = None  # 안내 화면에서 [시작]하거나 60초 뒤 자동 시작할 때 잰다 (G-03)
    for problemNo, key in enumerate(coding_bank.SELECTED, start=1):
        if db.query(CodingSubmission).filter_by(application_id=app.id, problem_no=problemNo).first() is None:
            db.add(CodingSubmission(application_id=app.id, problem_no=problemNo, problem_key=key,
                                    code=coding_bank.PROBLEMS[key]["starter"]))
    db.commit()
    admission.release(db, app)


def pcmToWav(pcm: bytes, sampleRate: int = 16000) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sampleRate)
        w.writeframes(pcm)
    return buffer.getvalue()
