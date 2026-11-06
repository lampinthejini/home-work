"""관리자 API (API 명세서 4장 관리용 · 10장). 결과·판정을 바꾸는 주소는 두지 않는다 (AC-14)."""


from fastapi import APIRouter, Depends, Query, Response
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from .. import worker
from ..config import SETTING_DEFAULTS
from ..db import getDb
from ..deps import requireAdmin
from ..errors import ApiError, notFound
from ..interview import registry
from ..models import (
    Answer,
    Application,
    AuditLog,
    CodingSubmission,
    Highlight,
    InterviewQuestion,
    ItemScore,
    JobCode,
    JobPosting,
    Memo,
    Notification,
    Recording,
    Result,
    SessionEvent,
    User,
)
from ..schemas import DraftAiRequest, ManualDecisionIn, MemoIn, PostingIn
from ..services import evaluation, posting_draft, recording, storage
from ..services import postings as svc
from ..settings_store import allSettings, getSetting, setSetting
from ..timeutil import iso, now, releaseAtFor

router = APIRouter(prefix="/admin")


def getPostingOr404(db: Session, postingId: str) -> JobPosting:
    p = db.get(JobPosting, postingId)
    if p is None:
        raise notFound()
    return p


@router.get("/postings")
def listPostings(status: str = "", db: Session = Depends(getDb), _admin: User = Depends(requireAdmin)):
    query = db.query(JobPosting)
    if status:
        query = query.filter(JobPosting.status == status)
    rows = query.order_by(JobPosting.updated_at.desc()).all()
    counts = {}
    for postingId, in db.query(Application.posting_id).filter(Application.attempt_status != "drafting"):
        counts[postingId] = counts.get(postingId, 0) + 1
    items = []
    for p in rows:
        view = svc.postingView(p, withCriteria=True)
        view["applicant_count"] = counts.get(p.id, 0)
        items.append(view)
    return {"items": items, "total": len(items)}


@router.post("/postings", status_code=201)
def createPosting(body: PostingIn, db: Session = Depends(getDb), admin: User = Depends(requireAdmin)):
    posting = svc.newDraft(db, admin.email)
    svc.updatePosting(db, posting, body)
    return svc.postingView(posting, withCriteria=True)


@router.get("/postings/{postingId}")
def getPosting(postingId: str, db: Session = Depends(getDb), _admin: User = Depends(requireAdmin)):
    p = getPostingOr404(db, postingId)
    view = svc.postingView(p, withCriteria=True)
    c = svc.currentCriteria(p)
    view["criteria"]["locked"] = bool(c and (c.locked or svc.hasStartedAttempt(db, p)))
    view["revisions"] = svc.revisionsView(db, p.id)
    return view


@router.patch("/postings/{postingId}")
def patchPosting(postingId: str, body: PostingIn, db: Session = Depends(getDb), _admin: User = Depends(requireAdmin)):
    p = getPostingOr404(db, postingId)
    svc.updatePosting(db, p, body)
    return svc.postingView(p, withCriteria=True)


@router.post("/postings/{postingId}/draft-ai", status_code=202)
async def draftAi(postingId: str, body: DraftAiRequest, db: Session = Depends(getDb), admin: User = Depends(requireAdmin)):
    """AI 공고 초안 (S-R02). 정해진 값은 바로 복사하고, 문장은 뒤에서 AI 가 채운다 (G-06)."""
    p = getPostingOr404(db, postingId)
    if p.status != "draft":
        raise ApiError(409, "ALREADY_PUBLISHED", "임시저장 공고에만 AI 초안을 만들 수 있습니다.")
    if posting_draft.drafts.get(p.id, {}).get("status") == "running":
        raise ApiError(409, "DRAFT_RUNNING", "이미 초안을 만들고 있습니다.")
    job = db.get(JobCode, body.job_code)
    if job is None or job.status != "open":
        raise ApiError(400, "JOB_NOT_OPEN", "준비 중인 직무입니다.")
    if body.open_at > body.close_at:
        raise ApiError(400, "POSTING_INCOMPLETE", "접수 시작일은 마감일보다 앞이어야 합니다.")
    if body.close_at <= now():
        raise ApiError(400, "POSTING_INCOMPLETE", "마감일은 지금 이후여야 합니다.")
    # 정해진 값은 AI 를 거치지 않는다 (AI 가 잘못 바꿀 여지를 없앰)
    svc.updatePosting(db, p, PostingIn(job_code=body.job_code, employment_type=body.employment_type, location=body.location.strip(),
                                       headcount=body.headcount, open_at=body.open_at, close_at=body.close_at))
    c = svc.currentCriteria(p)
    if c is not None and not c.locked:
        c.coding_enabled = body.coding_test
    p.source = "ai_draft"
    db.add(AuditLog(actor_id=admin.id, action="posting.draft_ai", target=p.id))
    db.commit()
    skills = [s.strip()[:50] for s in body.skills if s.strip()]
    body = body.model_copy(update={"duties": [d.strip()[:50] for d in body.duties if d.strip()], "skills": skills})
    posting_draft.start(p.id, posting_draft.buildPrompt(body, job.name), fallbackIntro=posting_draft.fallbackIntro(body, job.name))
    return {"job_id": p.id, "status": "running"}


@router.get("/postings/{postingId}/draft-ai/status")
def draftAiStatus(postingId: str, db: Session = Depends(getDb), _admin: User = Depends(requireAdmin)):
    p = getPostingOr404(db, postingId)
    if p.source != "ai_draft":
        raise notFound()
    return posting_draft.status(p.id, p)


@router.post("/postings/{postingId}/publish")
def publish(postingId: str, db: Session = Depends(getDb), admin: User = Depends(requireAdmin)):
    p = getPostingOr404(db, postingId)
    if p.status != "draft":
        raise ApiError(409, "ALREADY_PUBLISHED", "이미 게시했거나 마감된 공고입니다.")
    svc.validateForPublish(db, p)
    p.status = "published"
    p.published_at = now()
    p.release_at = releaseAtFor(p.close_at)
    db.add(AuditLog(actor_id=admin.id, action="posting.publish", target=p.id))
    db.commit()
    return svc.postingView(p, withCriteria=True)


@router.post("/postings/{postingId}/close")
async def close(postingId: str, db: Session = Depends(getDb), admin: User = Depends(requireAdmin)):
    p = getPostingOr404(db, postingId)
    if p.status != "published":
        raise ApiError(409, "NOT_PUBLISHED", "게시 중인 공고만 마감할 수 있습니다.")
    result = svc.closePosting(db, p)
    db.add(AuditLog(actor_id=admin.id, action="posting.close", target=p.id))
    db.commit()
    await registry.terminateMany(result.pop("live_application_ids"), "closed")
    return result


@router.delete("/postings/{postingId}", status_code=204)
def deletePosting(postingId: str, db: Session = Depends(getDb), _admin: User = Depends(requireAdmin)):
    p = getPostingOr404(db, postingId)
    if db.query(Application).filter_by(posting_id=p.id).count():
        raise ApiError(409, "HAS_APPLICANTS", "지원자가 있는 공고는 지울 수 없습니다. 마감만 할 수 있습니다.")
    # 이 공고를 가리키는 관리자 알림(마감 임박 등)은 누르면 없는 공고로 가므로 같이 지운다
    db.query(Notification).filter(Notification.link == f"/admin/applicants?posting={p.id}").delete()
    db.delete(p)
    db.commit()


def score(value) -> str | None:
    return None if value is None else f"{value:.2f}"


SORT_KEYS = {"total_score", "interview_score", "coding_score", "applied_at"}


@router.get("/postings/{postingId}/applicants")
def applicants(postingId: str, page: int = Query(1, ge=1), size: int = Query(50, ge=1, le=200),
               result: str | None = Query(None, pattern="^(undecided|pass|fail)$"),
               analysis_status: str | None = Query(None, pattern="^(pending|running|decided|needs_review)$"),
               sort: str = Query("-applied_at"),
               db: Session = Depends(getDb), _admin: User = Depends(requireAdmin)):
    """지원자 목록 (ADM-01). 분석 전 행은 점수·decision 이 null. 결정을 바꾸는 입력은 없다."""
    p = getPostingOr404(db, postingId)
    if sort.lstrip("-") not in SORT_KEYS:
        raise ApiError(400, "INVALID_SORT", "정렬 기준이 올바르지 않습니다.")
    query = (db.query(Application, Result).outerjoin(Result, Result.application_id == Application.id)
             .filter(Application.posting_id == p.id, Application.attempt_status != "drafting"))
    if analysis_status:
        query = query.filter(Application.analysis_status == analysis_status)
    if result == "undecided":
        query = query.filter(Result.id.is_(None))
    elif result:
        query = query.filter(Result.ai_decision == result)
    key = sort.lstrip("-")
    column = Application.submitted_at if key == "applied_at" else getattr(Result, key)
    order = column.desc() if sort.startswith("-") else column.asc()
    total = query.count()
    rows = query.order_by(order.nulls_last(), Application.submitted_at.desc()).offset((page - 1) * size).limit(size).all()
    items = []
    for a, r in rows:
        away = db.query(SessionEvent).filter_by(application_id=a.id, judged="cheating").count()
        faults = db.query(SessionEvent).filter_by(application_id=a.id, judged="fault").count()
        items.append({
            "application_id": a.id, "name": a.user.name, "email": a.user.email,
            "attempt_status": a.attempt_status, "analysis_status": a.analysis_status, "review_reason": a.review_reason,
            "submitted_at": iso(a.submitted_at), "completed_at": iso(a.completed_at),
            "away_count": away, "fault_count": faults,
            "interview_score": score(r.interview_score) if r and r.scored else None, "coding_score": score(r.coding_score) if r and r.scored else None,
            "total_score": score(r.total_score) if r and r.scored else None, "decision": r.ai_decision if r else None,
            "purge_at": iso(a.purge_at),
        })
    return {"posting": svc.postingView(p), "items": items, "has_coding_test": bool(svc.currentCriteria(p) and svc.currentCriteria(p).coding_enabled),
            "total": total, "page": page, "size": size}


def resultView(r: Result | None) -> dict | None:
    if r is None:
        return None
    return {"decision": r.ai_decision, "reason": r.ai_reason, "quotes": r.ai_reason_quotes,
            "item_scores": r.item_points, "interview_score": score(r.interview_score) if r.scored else None,
            "coding_score": score(r.coding_score) if r.scored else None,
            "total_score": score(r.total_score) if r.scored else None, "pass_score": score(r.pass_score), "strengths": r.strengths,
            "improvements": r.improvements, "summary": r.summary, "decision_check": r.decision_check,
            "model_version": r.model_version, "prompt_version": r.prompt_version, "rubric_version": r.rubric_version,
            "decided_at": iso(r.decided_at)}


@router.get("/applicants/{applicationId}")
def applicantDetail(applicationId: str, db: Session = Depends(getDb), admin: User = Depends(requireAdmin)):
    a = db.get(Application, applicationId)
    if a is None or a.attempt_status == "drafting":
        raise notFound()
    questions = db.query(InterviewQuestion).filter_by(application_id=a.id).order_by(InterviewQuestion.seq, InterviewQuestion.answer_order).all()
    answers = {ans.interview_question_id: ans for ans in db.query(Answer).filter_by(application_id=a.id)}
    scoresByQuestion: dict[int, list] = {}
    for s in db.query(ItemScore).filter_by(application_id=a.id).order_by(ItemScore.id):
        scoresByQuestion.setdefault(s.interview_question_id, []).append(
            {"item": s.eval_item, "score": s.score, "quote": s.quote, "quote_verified": s.quote_verified})
    baseAnswerId = {q.seq: answers[q.id].id for q in questions if q.kind == "base" and q.id in answers}
    qa = []
    for q in questions:
        ans = answers.get(q.id)
        qa.append({
            "scores": scoresByQuestion.get(q.id, []) if q.kind == "base" else [],
            "seq": q.seq, "kind": q.kind, "qtype": q.qtype, "text": q.text, "source": q.source,
            "substituted": q.substituted, "substitute_reason": q.substitute_reason, "regen_count": q.regen_count,
            "followup_reason": q.followup_reason, "asked_at": iso(q.asked_at),
            "answer": None if ans is None else {
                "transcript": ans.transcript, "audio_sec": ans.audio_sec, "end_reason": ans.end_reason,
                "media_url": f"/api/admin/media/answers/{ans.id}" if ans.audio_key else None,
            },
        })
    events = db.query(SessionEvent).filter_by(application_id=a.id).order_by(SessionEvent.at).all()
    coding = db.query(CodingSubmission).filter_by(application_id=a.id).order_by(CodingSubmission.problem_no).all()
    seqOf = {q.id: q.seq for q in questions}
    highlights = [{"seq": seqOf.get(h.interview_question_id), "kind": h.kind, "item": h.eval_item, "start_ms": h.start_ms,
                   "end_ms": h.end_ms, "quote": h.quote,
                   "media_url": f"/api/admin/media/answers/{baseAnswerId[seqOf[h.interview_question_id]]}"
                   if seqOf.get(h.interview_question_id) in baseAnswerId else None}
                  for h in db.query(Highlight).filter_by(application_id=a.id).order_by(Highlight.id)]
    result = db.query(Result).filter_by(application_id=a.id).first()
    recordings = db.query(Recording).filter_by(application_id=a.id).order_by(Recording.segment_no).all()
    db.add(AuditLog(actor_id=admin.id, action="applicant.view", target=a.id))
    db.commit()
    return {
        "application_id": a.id,
        "applicant": {"name": a.user.name, "email": a.user.email, "phone": a.user.phone},
        "posting": svc.postingView(a.posting, withCriteria=True),
        "attempt_status": a.attempt_status, "analysis_status": a.analysis_status, "review_reason": a.review_reason,
        "release_status": a.release_status, "release_at": iso(a.release_at), "purge_at": iso(a.purge_at),
        "review_deadline": iso(evaluation.reviewDeadline(a)) if a.analysis_status == "needs_review" else None,
        "result": resultView(result), "highlights": highlights,
        "instruction_hits": evaluation.instructionHits(evaluation.loadQuestions(db, a)),
        "resume": a.resume_snapshot, "resume_method": a.resume_method, "edited_fields": a.edited_fields,
        "submitted_at": iso(a.submitted_at), "completed_at": iso(a.completed_at),
        "questions": qa,
        "events": [{"type": e.type, "detail": e.detail, "judged": e.judged, "seq": e.seq, "at": iso(e.at)} for e in events],
        "coding": [{"problem_no": c.problem_no, "code": c.code, "passed": c.passed, "total": c.total,
                    "paste_blocked": c.paste_blocked, "grade_status": c.grade_status, "saved_at": iso(c.saved_at),
                    "feedback": c.feedback} for c in coding],
        "recordings": [{"segment_no": r.segment_no, "media_url": f"/api/admin/media/recordings/{a.id}/{r.segment_no}",
                        "size_bytes": r.size_bytes, "started_at": iso(r.started_at), "last_chunk_at": iso(r.last_chunk_at)}
                       for r in recordings],
        "recording_until": iso(min(recording.expiresAt(r, a) for r in recordings)) if recordings else None,
        "memos": [memoView(m) for m in db.query(Memo).filter_by(application_id=a.id).order_by(Memo.created_at)],
    }


def memoView(m: Memo) -> dict:
    return {"memo_id": m.id, "body": m.body, "created_at": iso(m.created_at), "updated_at": iso(m.updated_at)}


def memoBody(body: MemoIn) -> str:
    text = body.body.strip()
    if not text:
        raise ApiError(400, "MEMO_EMPTY", "메모 내용을 입력해 주세요.")
    return text


def getMemoOr404(db: Session, memoId: str) -> Memo:
    m = db.get(Memo, memoId)
    if m is None:
        raise notFound()
    return m


# 메모 본문은 감사 로그에 넣지 않는다 (지원자 개인 평가 내용)
@router.post("/applicants/{applicationId}/memo", status_code=201)
def createMemo(applicationId: str, body: MemoIn, db: Session = Depends(getDb), admin: User = Depends(requireAdmin)):
    a = db.get(Application, applicationId)
    if a is None or a.attempt_status == "drafting":
        raise notFound()
    m = Memo(application_id=a.id, author_id=admin.id, body=memoBody(body))
    db.add(m)
    db.flush()
    db.add(AuditLog(actor_id=admin.id, action="memo.create", target=a.id, detail={"memo_id": m.id}))
    db.commit()
    return memoView(m)


@router.patch("/memos/{memoId}")
def updateMemo(memoId: str, body: MemoIn, db: Session = Depends(getDb), admin: User = Depends(requireAdmin)):
    m = getMemoOr404(db, memoId)
    m.body = memoBody(body)
    m.updated_at = now()
    db.add(AuditLog(actor_id=admin.id, action="memo.update", target=m.application_id, detail={"memo_id": m.id}))
    db.commit()
    return memoView(m)


@router.delete("/memos/{memoId}", status_code=204)
def deleteMemo(memoId: str, db: Session = Depends(getDb), admin: User = Depends(requireAdmin)):
    m = getMemoOr404(db, memoId)
    db.add(AuditLog(actor_id=admin.id, action="memo.delete", target=m.application_id, detail={"memo_id": m.id}))
    db.delete(m)
    db.commit()


@router.post("/analysis/{applicationId}/reprocess", status_code=202)
def reprocess(applicationId: str, db: Session = Depends(getDb), admin: User = Depends(requireAdmin)):
    """'확인 필요' 건을 같은 응시 자료로 처음부터 다시 돌린다. 결과를 사람이 고치지는 않는다 (EVL-05·08)."""
    a = db.get(Application, applicationId)
    if a is None or a.attempt_status == "drafting":
        raise notFound()
    if a.analysis_status != "needs_review":
        raise ApiError(409, "NOT_NEEDS_REVIEW", "평가 지연 상태인 건만 다시 돌릴 수 있습니다.")
    # 채점 지시 의심 건은 관리자가 답변을 확인했다는 기록을 따로 남기고, 그 뒤로는 그대로 채점한다
    detail = {}
    action = "analysis.reprocess"
    if a.review_reason == "instruction_suspected":
        action = evaluation.INSTRUCTION_ACK
        detail = {"hits_digest": evaluation.hitsDigest(evaluation.instructionHits(evaluation.loadQuestions(db, a)))}
    # 사유를 지우지 않는다: 지우면 확인 필요가 된 시각도 지워져 3일 기한이 늘어난다
    a.analysis_status = "pending"
    db.add(AuditLog(actor_id=admin.id, action=action, target=a.id, detail=detail))
    db.commit()
    worker.requestReprocess(a.id)
    return {"analysis_status": "running"}


@router.post("/analysis/{applicationId}/decision")
def manualDecision(applicationId: str, body: ManualDecisionIn, db: Session = Depends(getDb), admin: User = Depends(requireAdmin)):
    """자동 채점을 끝내지 못한 건만 관리자가 합격·불합격과 사유를 정한다. 자동 채점 결과는 바꿀 수 없다 (CONFLICTS U8)."""
    a = db.get(Application, applicationId, with_for_update=True)
    if a is None or a.attempt_status == "drafting":
        raise notFound()
    if a.analysis_status != "needs_review":
        raise ApiError(409, "NOT_NEEDS_REVIEW", "평가 지연 상태인 건만 직접 결정할 수 있습니다.")
    reason = body.reason.strip()
    if len(reason) < evaluation.MANUAL_REASON_MIN:
        raise ApiError(400, "REASON_TOO_SHORT", f"결정 사유를 {evaluation.MANUAL_REASON_MIN}자 이상 입력해 주세요.")
    if not evaluation.decideManually(db, a, body.decision, reason, admin.id):
        raise ApiError(409, "CRITERIA_MISSING", "이 공고의 평가 기준을 찾을 수 없습니다.")
    db.commit()
    return {"analysis_status": a.analysis_status, "decision": body.decision, "release_at": iso(a.release_at)}


SETTING_HISTORY_SIZE = 10
# 키별 허용 범위 (CONFLICTS D2). 화면에서 바꾸는 키는 max_concurrent_interviews 하나다 (화면정의서 S-R10)
SETTING_RANGES = {"max_concurrent_interviews": (1, 20)}


@router.get("/settings")
def getSettings(db: Session = Depends(getDb), _admin: User = Depends(requireAdmin)):
    """현재 N · 지금 자리를 잡은 면접 수(AI 면접 진행 + 끊긴 지 10분 이내 장애 중단) · 최근 변경 (API 명세서 10장)."""
    history = (db.query(AuditLog).filter(AuditLog.action == "settings.change", AuditLog.target == "max_concurrent_interviews")
               .order_by(AuditLog.at.desc()).limit(SETTING_HISTORY_SIZE).all())
    return {
        "max_concurrent_interviews": getSetting(db, "max_concurrent_interviews"),
        "active_interviews": db.query(Application).filter(Application.holds_seat.is_(True)).count(),
        "history": [{"key": h.target, "from": (h.detail or {}).get("from"), "to": (h.detail or {}).get("value"), "at": iso(h.at)}
                    for h in history],
        "items": allSettings(db),
    }


@router.put("/settings/{key}")
def putSetting(key: str, body: dict, db: Session = Depends(getDb), admin: User = Depends(requireAdmin)):
    if key not in SETTING_DEFAULTS:
        raise notFound()
    if key not in SETTING_RANGES:
        raise ApiError(400, "INVALID_SETTING", "이 설정은 화면에서 바꿀 수 없습니다 (서버 설정 파일에서 관리).")
    if set(body) != {"value"}:
        raise ApiError(400, "INVALID_SETTING", "설정값 형식이 맞지 않습니다.")
    value = body["value"]
    expected = type(SETTING_DEFAULTS[key][0])
    if not isinstance(value, expected) or isinstance(value, bool) != (expected is bool):
        raise ApiError(400, "INVALID_SETTING", "설정값 형식이 맞지 않습니다.")
    low, high = SETTING_RANGES.get(key, (None, None))
    if (low is not None and value < low) or (high is not None and value > high):
        raise ApiError(400, "INVALID_SETTING", f"{low}~{high} 사이로 입력해 주세요.")
    previous = getSetting(db, key)
    setSetting(db, key, value, actorId=admin.id)
    db.add(AuditLog(actor_id=admin.id, action="settings.change", target=key, detail={"from": previous, "value": value}))
    db.commit()
    return {"key": key, "value": value}


@router.get("/media/answers/{answerId}")
def answerAudio(answerId: str, db: Session = Depends(getDb), admin: User = Depends(requireAdmin)):
    ans = db.get(Answer, answerId)
    if ans is None or ans.audio_key is None:
        raise notFound()
    data, contentType = storage.getObject(ans.audio_key)
    db.add(AuditLog(actor_id=admin.id, action="answer.listen", target=ans.application_id))
    db.commit()
    return Response(content=data, media_type=contentType, headers={"cache-control": "private, no-store"})


@router.get("/media/recordings/{applicationId}/{segmentNo}")
def recordingVideo(applicationId: str, segmentNo: int, db: Session = Depends(getDb), admin: User = Depends(requireAdmin)):
    """녹화 다시 보기. 보관 기한(응시 끝 + 3일)이 지났으면 410. 재생할 때마다 감사 로그 (API 명세서 2-6)."""
    a = db.get(Application, applicationId)
    rec = db.query(Recording).filter_by(application_id=applicationId, segment_no=segmentNo).first() if a else None
    if rec is None:
        raise notFound()
    if recording.expiresAt(rec, a) <= now():
        raise ApiError(410, "MEDIA_EXPIRED", "보관 기간이 지나 볼 수 없습니다.")
    db.add(AuditLog(actor_id=admin.id, action="recording.play", target=a.id, detail={"segment_no": segmentNo}))
    db.commit()
    return StreamingResponse(recording.streamSegment(rec.file_key), media_type="video/webm", headers={"cache-control": "private, no-store"})
