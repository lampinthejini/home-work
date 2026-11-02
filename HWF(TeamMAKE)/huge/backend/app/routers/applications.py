"""지원·동의·이력서 API (API 명세서 5장)."""

import asyncio

from fastapi import APIRouter, Depends, File, UploadFile
from sqlalchemy.orm import Session

from ..crypto import subjectHash
from ..db import getDb
from ..deps import ownedApplication, requireApplicant
from ..domain import status as st
from ..errors import ApiError, notFound
from ..models import Application, Consent, JobPosting, ResumeUpload, SavedResume, User
from ..schemas import ApplicationCreate, ConsentRequest, ResumeIn, ResumeSubmit
from ..services import question_compose, resume_extract, storage, withdrawal
from ..services.postings import currentCriteria, isAcceptingApplications
from ..settings_store import getSetting
from ..timeutil import iso, now

router = APIRouter()
backgroundTasks: set[asyncio.Task] = set()


def spawn(coro) -> None:
    task = asyncio.get_running_loop().create_task(coro)
    backgroundTasks.add(task)
    task.add_done_callback(backgroundTasks.discard)


def nextStep(db: Session, app: Application) -> str:
    return "resume" if db.query(Consent).filter_by(application_id=app.id, withdrawn_at=None).count() else "consent"


def requireDrafting(app: Application) -> None:
    if app.attempt_status != st.DRAFTING:
        raise ApiError(409, "RESUME_LOCKED", "이미 제출한 지원서는 고칠 수 없습니다.")


@router.post("/applications")
def createApplication(body: ApplicationCreate, db: Session = Depends(getDb), user: User = Depends(requireApplicant)):
    posting = db.get(JobPosting, body.posting_id)
    if posting is None or posting.status == "draft":
        raise notFound()
    # 같은 사용자의 지원 만들기를 한 줄로 세운다 (두 번 눌러 지원이 2건 생기지 않게)
    db.query(User).filter(User.id == user.id).with_for_update().one()
    existing = db.query(Application).filter_by(user_id=user.id, posting_id=posting.id).first()
    if existing is not None and existing.attempt_status != st.DRAFTING:
        raise ApiError(409, "ALREADY_APPLIED", "이미 지원한 공고입니다. 진행 상황은 마이페이지에서 확인할 수 있습니다.")
    if not isAcceptingApplications(posting):
        raise ApiError(409, "POSTING_CLOSED", "접수 기간이 아닙니다.")
    if posting.job_code != "AI_AX":
        raise ApiError(400, "JOB_NOT_OPEN", "준비 중인 직무입니다.")
    if existing is not None:
        return {"application_id": existing.id, "attempt_status": existing.attempt_status, "next_step": nextStep(db, existing)}
    app = Application(user_id=user.id, posting_id=posting.id, attempt_status=st.DRAFTING)
    db.add(app)
    db.commit()
    return {"application_id": app.id, "attempt_status": app.attempt_status, "next_step": "consent"}


@router.get("/applications/{applicationId}")
def getApplication(applicationId: str, db: Session = Depends(getDb), user: User = Depends(requireApplicant)):
    """지원 절차 화면의 공통 정보와 상태별 가드 (화면정의서 §2.3)."""
    app = ownedApplication(db, user, applicationId)
    p = app.posting
    c = currentCriteria(p)
    upload = db.get(ResumeUpload, app.resume_upload_id) if app.resume_upload_id else None
    return {
        "application_id": app.id, "attempt_status": app.attempt_status, "next_step": nextStep(db, app),
        "posting": {"posting_id": p.id, "title": p.title, "company_name": p.company_name, "close_at": iso(p.close_at),
                    "release_at": iso(p.release_at), "has_coding_test": bool(c and c.coding_enabled)},
        "resume": app.resume_snapshot, "resume_name": app.resume_name, "resume_method": app.resume_method,
        "pending_upload": None if upload is None else {"upload_id": upload.id, "stage": upload.stage, "file_name": upload.file_name},
        "questions_status": app.questions_status, "server_time": iso(now()),
        "consent_version": getSetting(db, "consent_version"),
    }


@router.post("/applications/{applicationId}/consent/withdraw", status_code=204)
async def withdrawConsent(applicationId: str, db: Session = Depends(getDb), user: User = Depends(requireApplicant)):
    """동의 철회 (APP-03): 진행 중 응시는 취소하고 이 지원의 데이터를 바로 지운다. 되돌릴 수 없다."""
    app = ownedApplication(db, user, applicationId, forUpdate=True)
    if not db.query(Consent).filter_by(application_id=app.id, withdrawn_at=None).count():
        raise ApiError(409, "NO_CONSENT", "철회할 동의가 없습니다.")
    await withdrawal.withdrawApplication(db, app, "consent")


@router.post("/applications/{applicationId}/consent", status_code=201)
def consent(applicationId: str, body: ConsentRequest, db: Session = Depends(getDb), user: User = Depends(requireApplicant)):
    app = ownedApplication(db, user, applicationId)
    requireDrafting(app)
    if not all(body.items.model_dump().values()):
        raise ApiError(400, "AGREEMENT_REQUIRED", "5개 항목에 모두 동의해야 진행할 수 있습니다.")
    if body.consent_version != getSetting(db, "consent_version"):
        raise ApiError(409, "CONSENT_VERSION_CHANGED", "동의 문구가 바뀌었습니다. 다시 확인해 주세요.")
    row = Consent(application_id=app.id, subject_hash=subjectHash(user.email),
                  consent_version=body.consent_version, items=body.items.model_dump())
    db.add(row)
    db.commit()
    return {"consent_id": row.id, "agreed_at": iso(row.agreed_at)}


async def acceptUpload(db: Session, user: User, file: UploadFile, applicationId: str | None) -> ResumeUpload:
    limitBytes = getSetting(db, "upload_max_mb") * 1024 * 1024
    data = await file.read(limitBytes + 1)
    if len(data) > limitBytes:
        raise ApiError(413, "FILE_TOO_LARGE", "이력서를 불러오는 데 실패했습니다.")
    contentType = resume_extract.detectType(file.filename or "", data[:16])
    if contentType is None:
        raise ApiError(400, "UNSUPPORTED_FILE", "이력서를 불러오는 데 실패했습니다.")
    try:
        textPages, scannedPages, _ = await asyncio.to_thread(resume_extract.countPages, data, contentType)
    except Exception as exc:  # noqa: BLE001 — 깨진 PDF
        raise ApiError(400, "UNSUPPORTED_FILE", "이력서를 불러오는 데 실패했습니다.") from exc
    upload = ResumeUpload(user_id=user.id, application_id=applicationId, file_key="", file_name=(file.filename or "resume")[:255],
                          content_type=contentType, pages_text=textPages, pages_scanned=scannedPages)
    upload.estimated_seconds = resume_extract.estimateSeconds(textPages, scannedPages, getSetting(db, "ocr_sec_per_page"), getSetting(db, "resume_llm_sec"))
    db.add(upload)
    db.flush()
    upload.file_key = f"resumes/{user.id}/{upload.id}"
    await asyncio.to_thread(storage.putObject, upload.file_key, data, contentType)
    db.commit()
    spawn(resume_extract.runExtraction(upload.id))
    return upload


def uploadAccepted(upload: ResumeUpload) -> dict:
    return {"upload_id": upload.id, "file_name": upload.file_name,
            "pages": {"text": upload.pages_text, "scanned": upload.pages_scanned}, "estimated_seconds": upload.estimated_seconds}


def uploadStatus(upload: ResumeUpload) -> dict:
    elapsed = int(((upload.finished_at or now()) - upload.started_at).total_seconds()) if upload.started_at else 0
    resume, ocrMeta = resume_extract.splitResult(upload.result if upload.stage == "done" else None)
    confidence = ocrMeta.get("confidence")
    return {"upload_id": upload.id, "stage": upload.stage, "estimated_seconds": upload.estimated_seconds,
            "elapsed_seconds": max(elapsed, 0), "method": upload.method, "result": resume,
            "ocr_confidence": f"{confidence:.2f}" if confidence is not None else None,
            "ocr_low_conf_fields": ocrMeta.get("low_conf_fields", []), "fail_reason": upload.fail_reason, "file_name": upload.file_name}


@router.post("/applications/{applicationId}/resume/upload", status_code=202)
async def uploadResume(applicationId: str, file: UploadFile = File(...), db: Session = Depends(getDb), user: User = Depends(requireApplicant)):
    app = ownedApplication(db, user, applicationId)
    requireDrafting(app)
    upload = await acceptUpload(db, user, file, app.id)
    app.resume_upload_id = upload.id
    db.commit()
    return uploadAccepted(upload)


@router.get("/applications/{applicationId}/resume/extract-status")
def extractStatus(applicationId: str, db: Session = Depends(getDb), user: User = Depends(requireApplicant)):
    app = ownedApplication(db, user, applicationId)
    upload = db.get(ResumeUpload, app.resume_upload_id) if app.resume_upload_id else None
    if upload is None:
        raise notFound()
    return uploadStatus(upload)


@router.get("/applications/{applicationId}/resume/file")
def resumeFile(applicationId: str, db: Session = Depends(getDb), user: User = Depends(requireApplicant)):
    from fastapi.responses import Response

    app = ownedApplication(db, user, applicationId)
    upload = db.get(ResumeUpload, app.resume_upload_id) if app.resume_upload_id else None
    if upload is None:
        raise notFound()
    data, contentType = storage.getObject(upload.file_key)
    return Response(content=data, media_type=contentType, headers={"cache-control": "private, no-store"})


@router.delete("/applications/{applicationId}/resume/upload", status_code=204)
def cancelUpload(applicationId: str, db: Session = Depends(getDb), user: User = Depends(requireApplicant)):
    app = ownedApplication(db, user, applicationId)
    requireDrafting(app)
    upload = db.get(ResumeUpload, app.resume_upload_id) if app.resume_upload_id else None
    if upload is not None:
        storage.deletePrefix(upload.file_key)
        db.delete(upload)
    app.resume_upload_id = None
    db.commit()


def checkRequired(resume: ResumeIn) -> None:
    """필수: 성명과 학력 또는 경력 1건 이상 (APP-05)."""
    missing = []
    if not resume.name.strip():
        missing.append("성명")
    hasEducation = any(e.school.strip() for e in resume.education)
    hasCareer = any(c.company.strip() for c in resume.career)
    if not (hasEducation or hasCareer):
        missing.append("학력 또는 경력")
    if missing:
        raise ApiError(422, "RESUME_REQUIRED_MISSING", "필수 항목이 비어 있습니다: " + ", ".join(missing))


@router.post("/applications/{applicationId}/resume")
async def submitResume(applicationId: str, body: ResumeSubmit, db: Session = Depends(getDb), user: User = Depends(requireApplicant)):
    app = ownedApplication(db, user, applicationId, forUpdate=True)
    requireDrafting(app)
    if nextStep(db, app) == "consent":
        raise ApiError(409, "CONSENT_REQUIRED", "필수 동의를 먼저 해 주세요.")
    if not isAcceptingApplications(app.posting):
        raise ApiError(409, "POSTING_CLOSED", "접수 기간이 아닙니다.")
    checkRequired(body.resume)
    if body.method == "upload":
        upload = db.get(ResumeUpload, body.upload_id) if body.upload_id else None
        if upload is None or upload.user_id != user.id:
            raise ApiError(400, "UPLOAD_REQUIRED", "올린 이력서 파일을 찾을 수 없습니다.")
    resume = body.resume.model_dump()
    app.resume_name = resume.pop("name")
    app.resume_snapshot = resume
    app.resume_method = body.method
    app.edited_fields = body.edited_fields[:200]
    app.attempt_status = st.transition(app.attempt_status, st.READY)
    app.submitted_at = now()
    criteria = currentCriteria(app.posting)
    app.criteria_version = criteria.version if criteria else None
    db.commit()
    question_compose.scheduleCompose(app.id)  # 이력서 확정 직후 질문 구성 시작 (QST-03)
    return {"attempt_status": app.attempt_status, "close_at": iso(app.posting.close_at), "release_at": iso(app.posting.release_at)}


# ---- 마이페이지 등록 이력서 (1개, G-07) ----

@router.get("/me/resume")
def getSavedResume(db: Session = Depends(getDb), user: User = Depends(requireApplicant)):
    row = db.get(SavedResume, user.id)
    if row is None:
        raise notFound()
    return {"resume": {"name": row.name or "", **row.resume}, "updated_at": iso(row.updated_at)}


@router.put("/me/resume")
def putSavedResume(body: ResumeIn, db: Session = Depends(getDb), user: User = Depends(requireApplicant)):
    data = body.model_dump()
    name = data.pop("name")
    row = db.get(SavedResume, user.id)
    if row is None:
        row = SavedResume(user_id=user.id, resume=data, name=name)
        db.add(row)
    else:
        row.resume, row.name = data, name
    db.commit()
    return {"resume": {"name": name, **data}, "updated_at": iso(row.updated_at)}


@router.delete("/me/resume", status_code=204)
def deleteSavedResume(db: Session = Depends(getDb), user: User = Depends(requireApplicant)):
    row = db.get(SavedResume, user.id)
    if row is not None:
        db.delete(row)
        db.commit()
