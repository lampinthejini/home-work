"""관리자 예비 질문 (2026-11-16 사용자 결정, CONFLICTS C-20. 예전 '질문 관리'를 바꿈).

예비 질문은 AI 가 질문을 만들 때 보는 예시이고, 못 만들었을 때 대신 내는 질문이다.
AI 가 만든 질문은 승인 없이 들어오므로 여기서는 보고, 글을 고치고, '해당 직무만'을 정하고, 지운다.
칸: 질문분야 · 질문 · 직무 · 해당 직무만 · 삭제. 만든 지 하루가 안 된 질문은 NEW.
"""

from datetime import timedelta

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy import text as sql
from sqlalchemy.orm import Session

from ..db import getDb
from ..deps import requireAdmin
from ..errors import ApiError, notFound
from ..models import AuditLog, JobCode, Question, User
from ..services import question_bank, rag
from ..timeutil import asKst, now

router = APIRouter(prefix="/admin/questions")

NEW_FOR = timedelta(days=1)
TEXT_MIN, TEXT_MAX = 5, 200
DELETE_MAX = question_bank.RESERVE_LIMIT_PER_KIND * len(question_bank.RESERVE_KINDS)


def jobName(db: Session, code: str | None) -> str:
    if not code:
        return ""
    job = db.get(JobCode, code)
    return job.name if job else code


def isNew(q: Question) -> bool:
    created = asKst(q.created_at)
    return created is not None and now() - created < NEW_FOR


def view(db: Session, q: Question) -> dict:
    code = q.job_code or question_bank.DEFAULT_JOB_CODE
    return {"id": q.id, "kind": q.kind, "text": q.text, "category": q.category, "job_code": code, "job_name": jobName(db, code),
            "job_only": q.job_code is not None, "is_new": isNew(q), "created_at": q.created_at.isoformat() if q.created_at else None}


def reserveQuery(db: Session):
    return db.query(Question).filter(Question.source == "reserve")


@router.get("")
def listQuestions(kind: str | None = Query(None, pattern="^(personality|company|resume|job)$"),
                  db: Session = Depends(getDb), _admin: User = Depends(requireAdmin)):
    counts = dict(reserveQuery(db).with_entities(Question.kind, func.count()).group_by(Question.kind).all())
    rows = reserveQuery(db)
    if kind:
        rows = rows.filter(Question.kind == kind)
    return {"items": [view(db, q) for q in rows.order_by(Question.created_at.desc(), Question.id.desc())],
            "counts": {k: counts.get(k, 0) for k in question_bank.RESERVE_KINDS},
            "limit": question_bank.RESERVE_LIMIT_PER_KIND}


class QuestionPatch(BaseModel):
    text: str | None = Field(default=None, max_length=TEXT_MAX)
    job_only: bool | None = None


def reserveOr404(db: Session, questionId: int) -> Question:
    q = db.get(Question, questionId)
    if q is None or q.source != "reserve":
        raise notFound()
    return q


@router.patch("/{questionId}")
def updateQuestion(questionId: int, body: QuestionPatch, db: Session = Depends(getDb), admin: User = Depends(requireAdmin)):
    """글 고치기(관리자가 직접 고친 글은 유사도로 막지 않는다)와 '해당 직무만' 켜고 끄기."""
    q = reserveOr404(db, questionId)
    detail: dict = {}
    if body.text is not None:
        text = " ".join(body.text.split())
        if len(text) < TEXT_MIN:
            raise ApiError(400, "QUESTION_TEXT_INVALID", f"질문은 {TEXT_MIN}자 이상 써 주세요.")
        group = question_bank.normalizeText(text)[:128]
        if text != q.text and db.query(Question.id).filter(Question.duplicate_group == group, Question.id != q.id).first():
            raise ApiError(409, "QUESTION_DUPLICATE", "같은 질문이 이미 있습니다.")
        if text != q.text:
            detail["text"] = {"from": q.text, "to": text}
            q.text, q.duplicate_group = text, group
            reembed(db, q)
    if body.job_only is not None and body.job_only != (q.job_code is not None):
        q.job_code = question_bank.DEFAULT_JOB_CODE if body.job_only else None
        detail["job_only"] = body.job_only
    if detail:
        db.add(AuditLog(actor_id=admin.id, action="question.edit", target=str(q.id), detail=detail))
    db.commit()
    return view(db, q)


def reembed(db: Session, q: Question) -> None:
    """고친 글로 임베딩을 다시 만든다. 임베딩 서버가 없으면 비워 두고 다음 시작 때 채운다 (main.indexMissing)."""
    if not rag.supported(db):
        return
    db.flush()
    try:
        rag.storeVector(db, q.id, rag.embedSync([q.text], timeoutSec=rag.EMBED_TIMEOUT_SEC)[0])
    except rag.EmbedUnavailable:
        db.execute(sql("UPDATE questions SET embedding = NULL WHERE id = :id"), {"id": q.id})


class DeleteIn(BaseModel):
    ids: list[int] = Field(min_length=1, max_length=DELETE_MAX)


@router.post("/delete")
def deleteQuestions(body: DeleteIn, db: Session = Depends(getDb), admin: User = Depends(requireAdmin)):
    """고른 예비 질문을 지운다 (한 줄 [삭제]도 이것을 쓴다)."""
    ids = [i for (i,) in reserveQuery(db).filter(Question.id.in_(body.ids)).with_entities(Question.id)]
    deleted = question_bank.deleteQuestions(db, ids)
    db.add(AuditLog(actor_id=admin.id, action="question.delete", target="questions", detail={"ids": ids}))
    db.commit()
    return {"deleted": deleted}
