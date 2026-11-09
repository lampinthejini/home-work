"""마이페이지 지원 내역·결과 (API 명세서 9장). 점수·근거는 어느 응답에도 넣지 않는다 (RPT-03, AC-16)."""

from datetime import timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..db import getDb
from ..deps import activeUser, ownedApplication, requireApplicant
from ..domain import status as st
from ..errors import notFound
from ..interview import registry
from ..models import Application, Consent, InterviewSession, Notification, Result, User
from ..timeutil import asKst, iso, now

router = APIRouter()
RESULT_VIEW_DAYS = 7


def releaseAt(app: Application):
    """이 건의 공개 시각. 결과가 늦게 나온 건은 따로 정해진다(EVL-08). 확정 전에는 공고의 공개 시각."""
    return asKst(app.release_at or app.posting.release_at)


def isReleased(app: Application) -> bool:
    at = releaseAt(app)
    if app.release_status != "released" or at is None or now() < at:
        return False
    return app.purge_at is None or now() < asKst(app.purge_at)


@router.get("/me/applications")
def myApplications(page: int = Query(1, ge=1), size: int = Query(20, ge=1, le=50),
                   db: Session = Depends(getDb), user: User = Depends(requireApplicant)):
    rows = db.query(Application).filter(Application.user_id == user.id).all()
    rows.sort(key=lambda a: (st.MY_APPLICATIONS_ORDER.get(a.attempt_status, 9), -asKst(a.created_at).timestamp()))
    total = len(rows)
    items = []
    for a in rows[(page - 1) * size: page * size]:
        released = isReleased(a)
        session = db.query(InterviewSession).filter_by(application_id=a.id).order_by(InterviewSession.created_at.desc()).first()
        items.append({
            "application_id": a.id,
            "posting": {"posting_id": a.posting.id, "title": a.posting.title, "close_at": iso(a.posting.close_at)},
            "attempt_status": a.attempt_status,
            "next_action": st.nextAction(a.attempt_status, released),
            "phase": a.phase,
            "session_id": session.id if session and a.attempt_status in st.IN_PROGRESS else None,
            # 면접 화면이 지금 붙어 있는가. 시작 뒤 한 번도 연결되지 않은 응시를 '다른 창에서 응시 중'으로 보이지 않게 한다 (E7)
            "connected": a.attempt_status in st.IN_PROGRESS and registry.get(a.id) is not None,
            "resume_until": iso(a.posting.close_at) if a.attempt_status == st.INTERRUPTED else None,
            "release_status": a.release_status,
            "release_at": iso(releaseAt(a)),
            "result_until": iso(a.purge_at or releaseAt(a) + timedelta(days=RESULT_VIEW_DAYS)) if released else None,
            "applied_at": iso(a.submitted_at or a.created_at),
            "consented": db.query(Consent).filter_by(application_id=a.id, withdrawn_at=None).count() > 0,  # 계정 탭 [동의 철회]
        })
    return {"items": items, "total": total, "page": page, "size": size}


@router.get("/me/results/{applicationId}")
def myResult(applicationId: str, db: Session = Depends(getDb), user: User = Depends(requireApplicant)):
    """공개된 결과(public_view)만 준다. 점수·근거·이유는 넣지 않는다 (RPT-03·04). 공개 전·보관 만료는 404."""
    app = ownedApplication(db, user, applicationId)
    result = db.query(Result).filter_by(application_id=app.id).first()
    if not isReleased(app) or result is None:
        raise notFound()
    view = result.public_view or {}
    return {
        "application_id": app.id,
        "posting": {"posting_id": app.posting.id, "title": app.posting.title},
        "result": view.get("result"),
        "attempt_status": app.attempt_status,
        "status_reason": view.get("status_reason"),
        "strengths": view.get("strengths", []),
        "improvements": view.get("improvements", []),
        "ai_generated": view.get("ai_generated", True),
        "contact_email": app.posting.contact_email,
        "result_until": iso(app.purge_at),
        "status": "released",
    }


@router.get("/notifications")
def notifications(db: Session = Depends(getDb), user: User = Depends(activeUser)):
    """머리글 🔔: 최근 20건과 안 읽은 수 (API 명세서 9장)."""
    shown = db.query(Notification).filter_by(user_id=user.id, hidden_at=None)
    rows = shown.order_by(Notification.created_at.desc()).limit(20).all()
    unread = shown.filter_by(read_at=None).count()
    return {"unread": unread, "items": [{"notification_id": n.id, "kind": n.kind, "title": n.title, "link": n.link,
                                         "read": n.read_at is not None, "created_at": iso(n.created_at)} for n in rows]}


@router.post("/notifications/{notificationId}/read", status_code=204)
def readNotification(notificationId: str, db: Session = Depends(getDb), user: User = Depends(activeUser)):
    row = db.get(Notification, notificationId)
    if row is None or row.user_id != user.id:
        raise notFound()
    if row.read_at is None:
        row.read_at = now()
        db.commit()


@router.post("/notifications/{notificationId}/hide", status_code=204)
def hideNotification(notificationId: str, db: Session = Depends(getDb), user: User = Depends(activeUser)):
    """🔔 목록에서 지운다(숨김). 안 읽은 알림이면 읽음으로도 표시한다."""
    row = db.get(Notification, notificationId)
    if row is None or row.user_id != user.id:
        raise notFound()
    current = now()
    row.read_at = row.read_at or current
    row.hidden_at = row.hidden_at or current
    db.commit()


@router.post("/notifications/hide-read")
def hideReadNotifications(db: Session = Depends(getDb), user: User = Depends(activeUser)):
    """읽은 알림을 모두 🔔 목록에서 지운다(숨김)."""
    hidden = (db.query(Notification).filter(Notification.user_id == user.id, Notification.read_at.is_not(None),
                                            Notification.hidden_at.is_(None)).update({"hidden_at": now()}))
    db.commit()
    return {"hidden": hidden}
