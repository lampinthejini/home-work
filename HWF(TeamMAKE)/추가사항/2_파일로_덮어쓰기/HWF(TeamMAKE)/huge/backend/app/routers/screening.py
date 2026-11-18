"""서류 평가: 포트폴리오 올리기 · 결과 보기 · 이의 신청 · 관리자 판정 변경 (CONFLICTS C-24)."""

import asyncio
import uuid
from typing import Literal

from fastapi import APIRouter, Depends, File, UploadFile
from pydantic import Field
from sqlalchemy.orm import Session

from .. import worker
from ..db import getDb
from ..deps import ownedApplication, requireAdmin, requireApplicant
from ..domain import status as st
from ..errors import ApiError, notFound
from ..models import Application, AuditLog, ResumeScreening, User
from ..schemas import Strict
from ..services import notify, question_compose, resume_extract, storage
from ..services.postings import currentCriteria
from ..services.resume_screening import criteriaFor, screeningView
from ..timeutil import now
from .applications import UPLOAD_SLOTS, requireDrafting

router = APIRouter()

PORTFOLIO_MAX_MB = 10
PORTFOLIO_TEXT_CHARS = 20000  # 저장하는 글자 수. 평가에는 앞 2,000자만 넣는다 (resume_screening.PORTFOLIO_CHARS)
PORTFOLIO_OCR_PAGES = 3  # 글자가 없는(스캔) PDF 는 앞 3쪽만 OCR


async def portfolioText(data: bytes) -> str:
    """PDF 글자 뽑기. 리더는 격리된 상자(pdf_box)에서 돈다. 글자가 없으면 앞 몇 쪽만 OCR."""
    try:
        pages = await resume_extract.readPages(data)
    except resume_extract.BoxError as exc:
        raise ApiError(400, exc.code, "포트폴리오 PDF 를 읽지 못했습니다.") from exc
    text = "\n\n".join(p.text for p in pages if p.source != "none").strip()
    if not text and pages:
        try:
            done = await resume_extract.ocrPages(data, "application/pdf", [p.no for p in pages[:PORTFOLIO_OCR_PAGES]])
            text = "\n\n".join(page.text for page, _lines in done).strip()
        except resume_extract.OcrError:
            text = ""
    if not text:
        raise ApiError(400, "PORTFOLIO_NO_TEXT", "포트폴리오에서 글자를 읽지 못했습니다. 글자가 들어 있는 PDF 를 올려 주세요.")
    return text[:PORTFOLIO_TEXT_CHARS]


def portfolioView(app: Application) -> dict | None:
    if not app.portfolio_key:
        return None
    return {"file_name": app.portfolio_name, "chars": len(app.portfolio_text or "")}


@router.post("/applications/{applicationId}/portfolio")
async def uploadPortfolio(applicationId: str, file: UploadFile = File(...), db: Session = Depends(getDb),
                          user: User = Depends(requireApplicant)):
    """포트폴리오 PDF (선택). 서류 평가를 켠 공고에서만 받는다 (쓰지 않는 개인정보는 모으지 않음). 다시 올리면 바꾼다."""
    app = ownedApplication(db, user, applicationId)
    requireDrafting(app)
    criteria = currentCriteria(app.posting)
    if not (criteria and criteria.screening_enabled):
        raise ApiError(409, "PORTFOLIO_NOT_USED", "이 공고는 포트폴리오를 받지 않습니다.")
    async with UPLOAD_SLOTS:
        data = await file.read(PORTFOLIO_MAX_MB * 1024 * 1024 + 1)
        if len(data) > PORTFOLIO_MAX_MB * 1024 * 1024:
            raise ApiError(413, "FILE_TOO_LARGE", f"포트폴리오는 {PORTFOLIO_MAX_MB}MB 까지 올릴 수 있습니다.")
        if resume_extract.detectType(file.filename or "", data[:16]) != "application/pdf":
            raise ApiError(400, "UNSUPPORTED_FILE", "포트폴리오는 PDF 만 올릴 수 있습니다.")
        text = await portfolioText(data)
        key = f"portfolios/{app.id}/{uuid.uuid4()}.pdf"
        await asyncio.to_thread(storage.putObject, key, data, "application/pdf")
    old = app.portfolio_key
    app.portfolio_key, app.portfolio_name, app.portfolio_text = key, (file.filename or "portfolio.pdf")[:255], text
    db.commit()
    if old:
        await asyncio.to_thread(storage.deletePrefix, old)
    return {"portfolio": portfolioView(app)}


@router.delete("/applications/{applicationId}/portfolio", status_code=204)
async def deletePortfolio(applicationId: str, db: Session = Depends(getDb), user: User = Depends(requireApplicant)):
    app = ownedApplication(db, user, applicationId)
    requireDrafting(app)
    old = app.portfolio_key
    app.portfolio_key = app.portfolio_name = app.portfolio_text = None
    db.commit()
    if old:
        await asyncio.to_thread(storage.deletePrefix, old)


@router.get("/applications/{applicationId}/portfolio")
def getPortfolio(applicationId: str, db: Session = Depends(getDb), user: User = Depends(requireApplicant)):
    return {"portfolio": portfolioView(ownedApplication(db, user, applicationId))}


class AppealIn(Strict):
    text: str = Field(min_length=1, max_length=1000)


class ScreeningDecisionIn(Strict):
    decision: Literal["pass", "fail"]
    note: str = Field(min_length=1, max_length=1000)


def screeningRow(db: Session, app: Application) -> ResumeScreening | None:
    return db.query(ResumeScreening).filter_by(application_id=app.id).first()


@router.get("/applications/{applicationId}/screening")
def myScreening(applicationId: str, db: Session = Depends(getDb), user: User = Depends(requireApplicant)):
    """지원자: 서류 평가 진행 상태와, 끝났으면 항목별 단계·근거 문장·점수."""
    app = ownedApplication(db, user, applicationId)
    row = screeningRow(db, app)
    if row is None:
        raise notFound()
    return {"attempt_status": app.attempt_status, "screening": screeningView(row, criteriaFor(app))}


@router.post("/applications/{applicationId}/screening/appeal")
def appeal(applicationId: str, body: AppealIn, db: Session = Depends(getDb), user: User = Depends(requireApplicant)):
    """서류 불합격 이의 신청. 한 번만. 관리자에게 알린다."""
    app = ownedApplication(db, user, applicationId, forUpdate=True)
    row = screeningRow(db, app)
    if row is None or app.attempt_status != st.SCREEN_REJECTED:
        raise ApiError(409, "NOT_SCREEN_REJECTED", "서류 불합격 건만 이의 신청할 수 있습니다.")
    if row.appeal_at is not None:
        raise ApiError(409, "APPEAL_DONE", "이미 이의 신청을 했습니다.")
    row.appeal_text, row.appeal_at = body.text.strip(), now()
    ids = [notify.create(db, adminId, "screening_appeal", f"[{app.posting.title}] 서류 평가 이의 신청이 들어왔습니다.",
                         f"/admin/applicants/{app.id}", app.id).id for adminId in notify.adminIds(db)]
    db.commit()
    for notificationId in ids:
        worker.queueMail(notificationId)
    return {"appeal_at": row.appeal_at.isoformat()}


@router.get("/admin/applications/{applicationId}/screening")
def adminScreening(applicationId: str, db: Session = Depends(getDb), _admin: User = Depends(requireAdmin)):
    """관리자: 1차·2차 항목별 결과, 이의 신청 내용."""
    app = db.get(Application, applicationId)
    if app is None:
        raise notFound()
    row = screeningRow(db, app)
    if row is None:
        raise notFound()
    return {"attempt_status": app.attempt_status, "screening": screeningView(row, criteriaFor(app), forAdmin=True)}


@router.post("/admin/applications/{applicationId}/screening/decision")
# async: 질문 만들기(scheduleCompose)는 이벤트 루프에 작업을 건다 (동기 함수면 스레드에서 돌아 루프가 없다)
async def changeDecision(applicationId: str, body: ScreeningDecisionIn, db: Session = Depends(getDb), admin: User = Depends(requireAdmin)):
    """관리자 판정 변경 (이의 신청 처리). 합격으로 바꾸면 응시 준비가 되고 질문 만들기를 시작한다."""
    app = db.get(Application, applicationId)
    row = screeningRow(db, app) if app else None
    if app is None or row is None:
        raise notFound()
    if row.decision is None or app.attempt_status not in (st.SCREEN_REJECTED, st.READY):
        raise ApiError(409, "SCREENING_NOT_DECIDED", "서류 평가가 끝난 건만 판정을 바꿀 수 있습니다.")
    if app.attempt_status == st.READY and body.decision == "fail":
        raise ApiError(409, "SCREENING_ALREADY_PASSED", "이미 서류 합격으로 응시 준비가 된 건은 불합격으로 바꿀 수 없습니다.")
    previous = row.decision
    row.decision, row.decided_by = body.decision, "admin"
    row.override_note, row.override_by, row.override_at = body.note.strip(), admin.id, now()
    notificationId = None
    if body.decision == "pass" and app.attempt_status == st.SCREEN_REJECTED:
        app.attempt_status = st.transition(app.attempt_status, st.READY)
        notificationId = notify.create(db, app.user_id, "screening", f"[{app.posting.title}] 서류 평가 결과가 합격으로 바뀌었습니다. "
                                       "면접 응시 준비를 해 주세요.", "/mypage", app.id).id
    db.add(AuditLog(actor_id=admin.id, action="screening.decision", target=app.id,
                    detail={"from": previous, "to": body.decision}))
    db.commit()
    if notificationId:
        worker.queueMail(notificationId)
        question_compose.scheduleCompose(app.id)
    return {"attempt_status": app.attempt_status, "screening": screeningView(row, criteriaFor(app), forAdmin=True)}
