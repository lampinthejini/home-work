"""관리자 질문 관리: AI 가 만든 질문(검토 대기)을 승인하면 질문은행에서 쓴다.

질문마다 적용 범위(C-17)를 보여 준다: 그 공고 전용(회사 질문) · 그 직무(직무 질문) · 공통(인성 질문)."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..db import getDb
from ..deps import requireAdmin
from ..errors import notFound
from ..models import AuditLog, JobCode, JobPosting, Question, User

router = APIRouter(prefix="/admin/questions")

STATUSES = ("pending", "active", "rejected")
LIST_LIMIT = 200


def scopeView(db: Session, q: Question) -> dict:
    if q.posting_id:
        posting = db.get(JobPosting, q.posting_id)
        return {"type": "posting", "posting_id": q.posting_id, "label": posting.title if posting else ""}
    if q.job_code:
        job = db.get(JobCode, q.job_code)
        return {"type": "job", "job_code": q.job_code, "label": job.name if job else q.job_code}
    return {"type": "common", "label": "공통"}


def view(db: Session, q: Question) -> dict:
    return {"id": q.id, "kind": q.kind, "text": q.text, "status": q.status, "category": q.category, "scope": scopeView(db, q)}


@router.get("")
def listQuestions(status: str = Query("pending", pattern="^(pending|active|rejected)$"),
                  kind: str | None = Query(None, pattern="^(personality|company|job)$"),
                  db: Session = Depends(getDb), _admin: User = Depends(requireAdmin)):
    base = db.query(Question).filter(Question.source == "generated")
    counts = dict(base.with_entities(Question.status, func.count()).group_by(Question.status).all())
    rows = base.filter(Question.status == status)
    if kind:
        rows = rows.filter(Question.kind == kind)
    return {"items": [view(db, q) for q in rows.order_by(Question.id.desc()).limit(LIST_LIMIT)],
            "counts": {s: counts.get(s, 0) for s in STATUSES}}


def setStatus(db: Session, admin: User, questionId: int, status: str) -> dict:
    q = db.get(Question, questionId)
    if q is None or q.source != "generated":
        raise notFound()  # 엑셀·예비 질문은 여기서 바꾸지 않는다
    before = q.status
    q.status = status
    db.add(AuditLog(actor_id=admin.id, action="question.approve" if status == "active" else "question.reject",
                    target=str(q.id), detail={"from": before, "to": status}))
    db.commit()
    return view(db, q)


@router.post("/{questionId}/approve")
def approve(questionId: int, db: Session = Depends(getDb), admin: User = Depends(requireAdmin)):
    return setStatus(db, admin, questionId, "active")


@router.post("/{questionId}/reject")
def reject(questionId: int, db: Session = Depends(getDb), admin: User = Depends(requireAdmin)):
    return setStatus(db, admin, questionId, "rejected")
