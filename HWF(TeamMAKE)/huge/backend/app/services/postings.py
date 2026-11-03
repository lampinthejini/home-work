"""공고·평가 기준 규칙 (PRD JOB-01~07, 화면정의서 §10.3, API 명세서 4장)."""

from sqlalchemy.orm import Session

from ..domain import status as st
from ..domain.scoring import DEFAULT_WEIGHTS, validateCodingRatio, validateWeights
from ..errors import ApiError
from ..models import Application, EvaluationCriteria, JobCode, JobPosting, PostingRevision
from ..timeutil import asKst, iso, now, releaseAtFor
from . import admission

REQUIRED_FIELDS = ["title", "company_intro", "duties", "requirements", "employment_type",
                   "location", "headcount", "open_at", "close_at", "contact_email"]
SHORT_REVISABLE = {"title": "제목", "employment_type": "고용 형태", "location": "근무지",
                   "headcount": "모집 인원", "contact_email": "문의 이메일"}
LONG_REVISABLE = {"company_intro": "부서 소개", "duties": "주요 업무", "requirements": "자격 요건", "preferred": "우대 사항"}
LOCKED_AFTER_PUBLISH = {"job_code", "open_at", "close_at"}
EMPLOYMENT_TYPES = {"full_time": "정규직", "contract": "계약직", "intern": "인턴"}

JOB_CODES = [
    ("AI_AX", "AI/AX 엔지니어", "open"),
    ("BACKEND", "백엔드 개발자", "preparing"),
    ("FRONTEND", "프론트엔드 개발자", "preparing"),
    ("DATA_ENG", "데이터 엔지니어", "preparing"),
    ("DATA_SCI", "데이터 사이언티스트·분석가", "preparing"),
    ("DEVOPS", "DevOps·클라우드", "preparing"),
    ("MOBILE", "모바일 앱", "preparing"),
]


def seedJobCodes(db: Session) -> None:
    for order, (code, name, status) in enumerate(JOB_CODES):
        if db.get(JobCode, code) is None:
            db.add(JobCode(code=code, name=name, status=status, sort_order=order))
    db.commit()


def currentCriteria(posting: JobPosting) -> EvaluationCriteria | None:
    return posting.criteria[-1] if posting.criteria else None


def hasStartedAttempt(db: Session, posting: JobPosting) -> bool:
    return db.query(Application).filter(Application.posting_id == posting.id, Application.attempt_consumed_at.isnot(None)).count() > 0


def criteriaView(c: EvaluationCriteria | None) -> dict | None:
    if c is None:
        return None
    return {"version": c.version, "locked": c.locked, "weights": c.weights, "coding_enabled": c.coding_enabled,
            "coding_ratio": c.coding_ratio, "pass_score": c.pass_score}


def postingView(p: JobPosting, withCriteria: bool = False) -> dict:
    c = currentCriteria(p)
    data = {
        "posting_id": p.id, "status": p.status, "source": p.source, "title": p.title, "job_code": p.job_code,
        "company_name": p.company_name, "company_intro": p.company_intro, "duties": p.duties,
        "requirements": p.requirements, "preferred": p.preferred, "employment_type": p.employment_type,
        "location": p.location, "headcount": p.headcount, "open_at": iso(p.open_at), "close_at": iso(p.close_at),
        "release_at": iso(p.release_at), "contact_email": p.contact_email,
        "has_coding_test": bool(c and c.coding_enabled),
    }
    if withCriteria:
        data["criteria"] = criteriaView(c)
        data["created_at"] = iso(p.created_at)
        data["updated_at"] = iso(p.updated_at)
    return data


def revisionSummary(field: str, before: str, after: str) -> str:
    """지원자에게 보여 줄 수정 사항 한 줄 (테이블 정의서 4-6 summary). 예: 근무지: 서울 강남구 → 서울 서초구"""
    label = SHORT_REVISABLE.get(field) or LONG_REVISABLE.get(field) or ("코딩테스트" if field == "coding_enabled" else field)
    if field in LONG_REVISABLE:
        return f"{label} 내용이 수정되었습니다"
    return f"{label}: {before} → {after}"[:300]


def revisionsView(db: Session, postingId: str) -> list[dict]:
    rows = db.query(PostingRevision).filter_by(posting_id=postingId).order_by(PostingRevision.revised_at.desc()).all()
    # 요약 칸이 생기기 전 행은 그 자리에서 만든다
    return [{"revised_at": iso(r.revised_at), "field": r.field, "summary": r.summary or revisionSummary(r.field, r.before, r.after)}
            for r in rows]


def isAcceptingApplications(p: JobPosting) -> bool:
    t = now()
    return p.status == "published" and p.open_at is not None and p.close_at is not None and asKst(p.open_at) <= t < asKst(p.close_at)


def displayValue(field: str, value) -> str:
    if field == "employment_type":
        return EMPLOYMENT_TYPES.get(value, str(value))
    if field == "headcount":
        return f"{value}명"
    if field == "coding_enabled":
        return "있음" if value else "없음"
    return str(value)


def applyCriteria(db: Session, posting: JobPosting, body, locked: bool) -> list[tuple[str, str, str]]:
    """평가 기준 반영. 잠기면 409. 게시 중 코딩 사용 여부가 바뀌면 수정 사항으로 남길 값을 돌려준다."""
    if locked:
        raise ApiError(409, "CRITERIA_LOCKED", "첫 응시가 시작되어 평가 기준을 바꿀 수 없습니다.")
    reason = validateWeights(body.weights)
    if reason:
        raise ApiError(400, "WEIGHT_SUM", reason)
    if body.coding_enabled and not validateCodingRatio(body.coding_ratio):
        raise ApiError(400, "CODING_RATIO", "코딩테스트 반영 비율은 10% 단위(10~90)여야 합니다.")
    c = currentCriteria(posting)
    changes = []
    if c is None:
        posting.criteria.append(EvaluationCriteria(version=1, weights=body.weights, coding_enabled=body.coding_enabled,
                                                   coding_ratio=body.coding_ratio, pass_score=body.pass_score))
        return changes
    if posting.status == "published" and c.coding_enabled != body.coding_enabled:
        changes.append(("coding_enabled", displayValue("coding_enabled", c.coding_enabled), displayValue("coding_enabled", body.coding_enabled)))
    c.weights = body.weights
    c.coding_enabled = body.coding_enabled
    c.coding_ratio = body.coding_ratio
    c.pass_score = body.pass_score
    return changes


def updatePosting(db: Session, posting: JobPosting, body) -> JobPosting:
    if posting.status == "closed":
        raise ApiError(409, "POSTING_CLOSED", "마감된 공고는 고칠 수 없습니다.")
    fields = body.model_dump(exclude_unset=True, exclude={"criteria"})
    if "job_code" in fields:
        job = db.get(JobCode, fields["job_code"])
        if job is None:
            raise ApiError(400, "JOB_NOT_OPEN", "없는 직무입니다.")
    published = posting.status == "published"
    revisions = []
    for field, value in fields.items():
        before = getattr(posting, field)
        if field in ("open_at", "close_at") and value is not None:
            value = asKst(value)
            if before is not None and asKst(before) == value:
                continue
        elif before == value:
            continue
        if published and field in LOCKED_AFTER_PUBLISH:
            raise ApiError(409, "FIELD_LOCKED_AFTER_PUBLISH", "게시 후에는 바꿀 수 없는 항목입니다.")
        if published and field in SHORT_REVISABLE:
            revisions.append((field, displayValue(field, before), displayValue(field, value)))
        elif published and field in LONG_REVISABLE:
            revisions.append((field, "", ""))
        setattr(posting, field, value)
    if posting.open_at and posting.close_at and asKst(posting.open_at) > asKst(posting.close_at):
        raise ApiError(400, "POSTING_INCOMPLETE", "접수 시작일은 마감일보다 앞이어야 합니다.")
    if body.criteria is not None:
        c = currentCriteria(posting)
        revisions += applyCriteria(db, posting, body.criteria, locked=bool(c and (c.locked or hasStartedAttempt(db, posting))))
    if posting.close_at:
        posting.release_at = releaseAtFor(posting.close_at)
    revisedAt = now()
    for field, before, after in revisions:
        db.add(PostingRevision(posting_id=posting.id, field=field, before=before, after=after, revised_at=revisedAt,
                               summary=revisionSummary(field, before, after)))
    db.commit()
    return posting


def validateForPublish(db: Session, posting: JobPosting) -> None:
    missing = [f for f in REQUIRED_FIELDS if getattr(posting, f) in (None, "")]
    if missing or currentCriteria(posting) is None:
        raise ApiError(400, "POSTING_INCOMPLETE", "필수 항목을 모두 채워 주세요: " + ", ".join(missing or ["평가 기준"]))
    job = db.get(JobCode, posting.job_code)
    if job is None or job.status != "open":
        raise ApiError(400, "JOB_NOT_OPEN", "준비 중인 직무는 게시할 수 없습니다.")
    if asKst(posting.open_at) > asKst(posting.close_at):
        raise ApiError(400, "POSTING_INCOMPLETE", "접수 시작일은 마감일보다 앞이어야 합니다.")
    if asKst(posting.close_at) <= now():
        raise ApiError(400, "POSTING_INCOMPLETE", "마감일은 지금 이후여야 합니다.")


def closePosting(db: Session, posting: JobPosting) -> dict:
    """마감: 시작 전 → 미응시(마감), 진행 중·장애 중단 → 응시 종료(마감) (INT-10, D-04).

    진행 중인 면접 세션 종료(terminate closed)는 호출한 쪽이 면접 엔진에 알린다.
    """
    posting.status = "closed"
    posting.closed_at = now()
    if posting.close_at is None or asKst(posting.close_at) > posting.closed_at:
        posting.close_at = posting.closed_at
        posting.release_at = releaseAtFor(posting.close_at)
    notTaken, endedByClose, liveIds = 0, 0, []
    for app in db.query(Application).filter(Application.posting_id == posting.id).all():
        target = st.statusOnClose(app.attempt_status)
        if target is None:
            continue
        if app.attempt_status in st.IN_PROGRESS:
            liveIds.append(app.id)
        app.attempt_status = target
        if target == st.NOT_TAKEN_CLOSED:
            notTaken += 1
        else:
            endedByClose += 1
            app.completed_at = now()
    db.commit()
    for app in db.query(Application).filter(Application.posting_id == posting.id, Application.holds_seat.is_(True)).all():
        admission.release(db, app)
    if endedByClose:
        from .. import worker  # 마감으로 끝난 응시도 답한 문항까지 채점한다 (D-04)

        for app in db.query(Application).filter(Application.posting_id == posting.id, Application.attempt_status == st.ENDED_CLOSED):
            worker.enqueueEvaluation(app.id)
    return {"closed_at": iso(posting.closed_at), "not_taken": notTaken, "ended_by_close": endedByClose, "live_application_ids": liveIds}


def newDraft(db: Session, adminEmail: str) -> JobPosting:
    posting = JobPosting(status="draft", source="manual", contact_email=adminEmail)
    posting.criteria.append(EvaluationCriteria(version=1, weights=dict(DEFAULT_WEIGHTS), coding_enabled=False, coding_ratio=30, pass_score=70))
    db.add(posting)
    db.commit()
    return posting
