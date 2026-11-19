"""서류 평가: 추가 서류(자기소개서·포트폴리오·프로젝트 계획서 등, 모두 선택) · 지원서 제출 · 결과 보기 · 이의 신청 (CONFLICTS C-25).

관리자는 결과를 보기만 한다 (판정을 바꾸지 않음, PRD N2). 이의 신청은 AI(8B)가 다시 평가한다.
"""

import asyncio
import uuid

from fastapi import APIRouter, Depends, File, UploadFile
from pydantic import Field
from sqlalchemy.orm import Session

from ..db import getDb
from ..deps import ownedApplication, requireAdmin, requireApplicant
from ..domain import status as st
from ..domain.scoring import normalizeForQuote
from ..errors import ApiError, notFound
from ..models import Application, ResumeScreening, User
from ..schemas import Strict
from ..services import resume_extract, resume_screening, storage
from ..services.postings import isAcceptingApplications
from ..services.resume_screening import COVER_TEXT_MAX, DOC_KINDS, FILE_TEXT_CHARS, ITEM_BY_KEY, MAX_FILES, NOT_APPEALABLE, criteriaFor, screeningView
from ..timeutil import now
from .applications import UPLOAD_SLOTS, nextStep, requireDrafting, submitApplication

router = APIRouter()

FILE_MAX_MB = 10
FILE_OCR_PAGES = 10  # OCR 하는 쪽 수 상한 (글자가 없는 쪽 · 큰 그림이 있는 쪽). PDF 는 10쪽까지 읽는다 (pdf_box.MAX_PAGES)
APPEAL_TEXT_MAX = 500


# ---------- 추가 서류 ----------

async def pdfText(data: bytes) -> str:
    """PDF 글자 뽑기. 리더는 격리된 상자(pdf_box)에서 돈다. 글자가 없는 쪽과 큰 그림이 있는 쪽은 OCR 로 읽어
    그림 속 글자까지 얻는다(FILE_OCR_PAGES 쪽까지). 그림 자체는 평가하지 않는다 — 평가에 쓰는 것은 글자뿐 (회의 결정 2026-11-18)."""
    try:
        pages = await resume_extract.readPages(data)
    except resume_extract.BoxError as exc:
        raise ApiError(400, exc.code, "PDF 를 읽지 못했습니다.") from exc
    texts = {p.no: p.text for p in pages if p.source != "none"}
    toOcr = [p.no for p in pages if p.source == "none" or p.images > 0][:FILE_OCR_PAGES]
    if toOcr:
        try:
            for page, _lines in await resume_extract.ocrPages(data, "application/pdf", toOcr):
                texts[page.no] = withImageText(texts.get(page.no, ""), page.text)
        except resume_extract.OcrError:
            pass  # OCR 이 안 되면 글자층만 쓴다
    text = "\n\n".join(texts[no].strip() for no in sorted(texts) if texts[no].strip())
    if not text:
        raise ApiError(400, "DOCUMENT_NO_TEXT", "PDF 에서 글자를 읽지 못했습니다. 글자가 들어 있는 PDF 를 올려 주세요.")
    return text[:FILE_TEXT_CHARS]


def withImageText(layerText: str, ocrText: str) -> str:
    """글자층 글 뒤에, OCR 로 읽은 줄 가운데 글자층에 없는 줄(그림 속 글자)만 붙인다. 글자층이 없으면 OCR 글 그대로."""
    if not layerText.strip():
        return ocrText
    known = normalizeForQuote(layerText)
    extra = [line.strip() for line in ocrText.splitlines()
             if len(normalizeForQuote(line)) >= 2 and normalizeForQuote(line) not in known]
    return layerText + ("\n" + "\n".join(extra) if extra else "")


def coverText(app: Application) -> str:
    return next((d["text"] for d in app.extra_documents or [] if d.get("source") == "text"), "")


def fileDocs(app: Application) -> list[dict]:
    return [d for d in app.extra_documents or [] if d.get("source") == "pdf"]


CARRIED_HEADING = "[이력서에서 옮긴 내용 — 자기소개 · 교육 · 대회 · 수상 · 활동 등]"


def carriedCover(cover: str | None, others: str | None) -> str:
    """이력서에서 읽은 자기소개와 칸 없는 항목을 자기소개서 칸에 넣을 글로. 머리말을 달아 지원자가 어디서 왔는지 안다.
    머리말은 하나만 단다 — 4B 가 자기소개와 칸 없는 항목을 섞어 나누는 일이 있어(실측 2026-11-18) 따로 달면 이름이 틀린다.
    칸 없는 항목을 앞에 둔다 — 짧고 다른 곳에 둘 데가 없어서, 칸(3,000자)을 넘으면 자기소개 뒷부분이 잘리게."""
    # 자기소개에 이미 있는 줄은 칸 없는 항목에서 뺀다 (같은 글이 두 번 들어가지 않게)
    known = normalizeForQuote(cover or "")
    others = "\n".join(line for line in (others or "").splitlines()
                       if line.strip() and not (len(normalizeForQuote(line)) >= 10 and normalizeForQuote(line) in known))
    parts = [t.strip() for t in (others, cover or "") if t.strip()]
    return f"{CARRIED_HEADING}\n" + "\n\n".join(parts) if parts else ""  # 칸보다 길면 setCoverText 가 문단 끝에서 자르고 표시한다


def documentsView(app: Application) -> dict:
    return {"cover_text": coverText(app), "cover_max": COVER_TEXT_MAX, "max_files": MAX_FILES, "file_max_mb": FILE_MAX_MB,
            "cover_auto": any(d.get("auto") for d in app.extra_documents or [] if d.get("source") == "text"),
            "cover_cut": any(d.get("cut") for d in app.extra_documents or [] if d.get("source") == "text"),
            "kinds": DOC_KINDS,
            "files": [{"id": d["id"], "kind": d["kind"], "name": d["name"], "chars": len(d.get("text") or "")} for d in fileDocs(app)]}


def setCoverText(app: Application, text: str, auto: bool = False) -> None:
    """auto: 이력서에서 자동으로 옮긴 글 (지원자가 한 번이라도 고치면 지원자 글이 된다). 칸보다 길면 문단 끝에서 자르고 표시한다."""
    text = text.strip()
    cut = auto and len(text) > COVER_TEXT_MAX
    if cut:
        head = text[:COVER_TEXT_MAX]
        text = (head[:head.rfind("\n")] if head.rfind("\n") > COVER_TEXT_MAX // 2 else head).strip()
    docs = fileDocs(app)
    if text:
        doc = {"id": "cover", "kind": "cover_letter", "source": "text", "name": "자기소개서", "key": None, "text": text}
        if auto:
            doc["auto"] = True
        if cut:
            doc["cut"] = True
        docs = [doc, *docs]
    app.extra_documents = docs


def requireResumeSaved(db: Session, app: Application) -> None:
    requireDrafting(app)
    if nextStep(db, app) != "documents":
        raise ApiError(409, "RESUME_REQUIRED", "이력서를 먼저 저장해 주세요.")


class DocumentsIn(Strict):
    cover_text: str = Field(default="", max_length=COVER_TEXT_MAX + 100)


def checkCover(body: DocumentsIn) -> None:
    if len(body.cover_text.strip()) > COVER_TEXT_MAX:
        raise ApiError(400, "COVER_TOO_LONG", f"자기소개서는 {COVER_TEXT_MAX}자까지 쓸 수 있습니다.")


@router.get("/applications/{applicationId}/documents")
def getDocuments(applicationId: str, db: Session = Depends(getDb), user: User = Depends(requireApplicant)):
    return documentsView(ownedApplication(db, user, applicationId))


@router.put("/applications/{applicationId}/documents")
def saveDocuments(applicationId: str, body: DocumentsIn, db: Session = Depends(getDb), user: User = Depends(requireApplicant)):
    """자기소개서 글 임시 저장 (제출 전까지 몇 번이든)."""
    app = ownedApplication(db, user, applicationId, forUpdate=True)
    requireResumeSaved(db, app)
    checkCover(body)
    setCoverText(app, body.cover_text)
    db.commit()
    return documentsView(app)


@router.post("/applications/{applicationId}/documents/files")
async def uploadDocument(applicationId: str, file: UploadFile = File(...),
                         db: Session = Depends(getDb), user: User = Depends(requireApplicant)):
    """자기소개서 PDF 하나 더하기 (MAX_FILES 개까지). 포트폴리오·프로젝트 기술서 등도 자기소개서로 본다."""
    app = ownedApplication(db, user, applicationId)
    requireResumeSaved(db, app)
    if len(fileDocs(app)) >= MAX_FILES:
        raise ApiError(409, "DOCUMENT_LIMIT", f"PDF 는 {MAX_FILES}개까지 올릴 수 있습니다.")
    async with UPLOAD_SLOTS:
        data = await file.read(FILE_MAX_MB * 1024 * 1024 + 1)
        if len(data) > FILE_MAX_MB * 1024 * 1024:
            raise ApiError(413, "FILE_TOO_LARGE", f"PDF 는 {FILE_MAX_MB}MB 까지 올릴 수 있습니다.")
        if resume_extract.detectType(file.filename or "", data[:16]) != "application/pdf":
            raise ApiError(400, "UNSUPPORTED_FILE", "추가 서류는 PDF 만 올릴 수 있습니다.")
        text = await pdfText(data)
        docId = str(uuid.uuid4())
        key = f"documents/{app.id}/{docId}.pdf"
        await asyncio.to_thread(storage.putObject, key, data, "application/pdf")
    app = ownedApplication(db, user, applicationId, forUpdate=True)  # 글자 뽑는 동안 바뀌었을 수 있다 (동시에 올린 경우)
    if app.attempt_status != st.DRAFTING or len(fileDocs(app)) >= MAX_FILES:
        db.rollback()
        await asyncio.to_thread(storage.deletePrefix, key)
        raise ApiError(409, "DOCUMENT_LIMIT", f"PDF 는 {MAX_FILES}개까지 올릴 수 있습니다.")
    app.extra_documents = [*(app.extra_documents or []), {"id": docId, "kind": "cover_letter", "source": "pdf",
                                                          "name": (file.filename or "document.pdf")[:255], "key": key, "text": text}]
    db.commit()
    return documentsView(app)


@router.delete("/applications/{applicationId}/documents/files/{fileId}")
async def deleteDocument(applicationId: str, fileId: str, db: Session = Depends(getDb), user: User = Depends(requireApplicant)):
    app = ownedApplication(db, user, applicationId, forUpdate=True)
    requireDrafting(app)
    target = next((d for d in fileDocs(app) if d["id"] == fileId), None)
    if target is None:
        raise notFound()
    app.extra_documents = [d for d in app.extra_documents if d.get("id") != fileId]
    db.commit()
    await asyncio.to_thread(storage.deletePrefix, target["key"])
    return documentsView(app)


@router.post("/applications/{applicationId}/submit")
async def submit(applicationId: str, body: DocumentsIn, db: Session = Depends(getDb), user: User = Depends(requireApplicant)):
    """지원서 제출. 추가 서류는 없어도 된다. 제출하면 서류 평가가 시작되고 더는 고칠 수 없다."""
    app = ownedApplication(db, user, applicationId, forUpdate=True)
    requireResumeSaved(db, app)
    if not isAcceptingApplications(app.posting):
        raise ApiError(409, "POSTING_CLOSED", "접수 기간이 아닙니다.")
    checkCover(body)
    setCoverText(app, body.cover_text)
    # 면접 질문 만들기는 이력서 cover_letter 칸을 읽는다. 자기소개서 글과 PDF 글을 이어 그 칸에 둔다
    cover = "\n\n".join(d["text"] for d in app.extra_documents or [] if (d.get("text") or "").strip())
    if cover:
        app.resume_snapshot = {**(app.resume_snapshot or {}), "cover_letter": cover[:5000]}
    return submitApplication(db, app)


# ---------- 결과 · 이의 신청 ----------

class AppealClaim(Strict):
    item: str
    text: str = Field(min_length=1, max_length=APPEAL_TEXT_MAX)


class AppealIn(Strict):
    claims: list[AppealClaim] = Field(min_length=1, max_length=len(ITEM_BY_KEY))


def screeningRow(db: Session, app: Application) -> ResumeScreening | None:
    return db.query(ResumeScreening).filter_by(application_id=app.id).first()


@router.get("/applications/{applicationId}/screening")
def myScreening(applicationId: str, db: Session = Depends(getDb), user: User = Depends(requireApplicant)):
    """지원자: 서류 평가 진행 상태와, 끝났으면 항목별 단계·근거 문장 (점수는 보이지 않음)."""
    app = ownedApplication(db, user, applicationId)
    row = screeningRow(db, app)
    if row is None:
        raise notFound()
    return {"attempt_status": app.attempt_status, "posting_title": app.posting.title,
            "can_appeal": canAppeal(app, row), "appeal_text_max": APPEAL_TEXT_MAX,
            "screening": screeningView(row, criteriaFor(app))}


def canAppeal(app: Application, row: ResumeScreening) -> bool:
    return app.attempt_status == st.SCREEN_REJECTED and row.appeal_at is None and isAcceptingApplications(app.posting)


@router.post("/applications/{applicationId}/screening/appeal")
async def appeal(applicationId: str, body: AppealIn, db: Session = Depends(getDb), user: User = Depends(requireApplicant)):
    """서류 불합격 이의 신청. 한 번만, 접수 기간 안에. 고른 항목마다 무엇이 틀렸는지 적으면 8B 가 그 항목을 다시 평가한다."""
    app = ownedApplication(db, user, applicationId, forUpdate=True)
    row = screeningRow(db, app)
    if row is None or app.attempt_status != st.SCREEN_REJECTED:
        raise ApiError(409, "NOT_SCREEN_REJECTED", "서류 불합격 건만 이의 신청할 수 있습니다.")
    if row.appeal_at is not None:
        raise ApiError(409, "APPEAL_DONE", "이미 이의 신청을 했습니다.")
    if not isAcceptingApplications(app.posting):
        raise ApiError(409, "POSTING_CLOSED", "접수 기간이 끝나 이의 신청을 할 수 없습니다.")
    keys = [c.item for c in body.claims]
    if len(set(keys)) != len(keys) or any(k not in ITEM_BY_KEY or k in NOT_APPEALABLE for k in keys):
        raise ApiError(400, "APPEAL_ITEM", "이의 신청할 수 없는 항목입니다.")
    row.appeal = [{"item": c.item, "text": c.text.strip()} for c in body.claims]
    row.appeal_status, row.appeal_at = "pending", now()
    db.commit()
    resume_screening.scheduleAppeal(app.id)
    return {"appeal_at": row.appeal_at.isoformat(), "appeal_status": row.appeal_status}


@router.get("/admin/applications/{applicationId}/screening")
def adminScreening(applicationId: str, db: Session = Depends(getDb), _admin: User = Depends(requireAdmin)):
    """관리자: 1차·2차 항목별 결과·점수, 이의 신청 내용과 재평가 결과, 추가 서류, 참고 사항(경력) (보기만)."""
    app = db.get(Application, applicationId)
    if app is None:
        raise notFound()
    row = screeningRow(db, app)
    if row is None:
        raise notFound()
    resume = app.resume_snapshot or {}
    career = [{k: c.get(k, "") for k in ("company", "role", "start", "end", "description")} for c in resume.get("career", [])
              if (c.get("company") or c.get("role") or "").strip()]
    documents = [{k: d.get(k) for k in ("kind", "source", "name", "text")} for d in app.extra_documents or []]
    # 경력은 채점하지 않고 참고 사항으로만 보여 준다 (2026-11-18 사용자 결정)
    return {"attempt_status": app.attempt_status, "documents": documents, "career": career,
            "screening": screeningView(row, criteriaFor(app), forAdmin=True)}
