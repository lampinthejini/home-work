"""동의 철회 (APP-03) · 회원 탈퇴 (S-A13). 진행 중 응시는 취소하고 자리를 돌려준 뒤 바로 지운다.

지우는 방식은 보관 기간 삭제(retention.purgeApplication)와 같다. 익명 통계에는 응시가 끝난 건만 더한다.
동의 기록은 철회 시각을 적어 증거로 남긴다 (테이블 정의서 4-9).
"""

from sqlalchemy.orm import Session

from ..domain import status as st
from ..interview import registry
from ..models import Application, AuditLog, Consent, DeletionLog, User
from ..timeutil import now
from . import admission, question_compose, retention, storage


async def withdrawApplication(db: Session, app: Application, cause: str) -> None:
    """cause: consent(동의 철회) · withdraw(탈퇴)."""
    live = app.attempt_status in st.IN_PROGRESS
    question_compose.cancelCompose(app.id)
    db.query(Consent).filter_by(application_id=app.id, withdrawn_at=None).update({Consent.withdrawn_at: now()})
    db.commit()
    admission.release(db, app)
    if live:
        await registry.terminateMany([app.id], "withdrawn")  # 화면에 알리고 면접 작업을 멈춘 뒤 지운다
    retention.purgeApplication(db, app, admission.redisClient(), cause=cause)


async def withdrawAccount(db: Session, user: User) -> None:
    userId = user.id
    for app in db.query(Application).filter_by(user_id=userId).all():
        await withdrawApplication(db, app, "withdraw")
    files = storage.deletePrefix(f"resumes/{userId}/")  # 등록 이력서용으로 올린 파일
    db.add(DeletionLog(user_id=userId, cause="withdraw", scope="account", deleted_items={"files": files}))
    db.add(AuditLog(actor_id=userId, action="account.withdraw", target=userId))
    db.delete(db.get(User, userId))  # 등록 이력서·알림·로그인 세션은 함께 지워진다 (ON DELETE CASCADE)
    db.commit()
