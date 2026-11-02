"""환경 점검 · 면접 시작/이어가기 · 이탈 신호 · 코딩테스트 · 미디어 (API 명세서 6장 · 8장)."""

import asyncio
import json
import os
from datetime import timedelta

from fastapi import APIRouter, Depends, File, Form, Request, Response, UploadFile, WebSocket
from sqlalchemy.orm import Session

from ..config import ENV
from ..db import SessionLocal, getDb
from ..deps import ownedApplication, requireApplicant
from ..domain import status as st
from ..errors import ApiError, notFound
from ..interview import lifecycle, registry
from ..interview.engine import BASE_QUESTION_COUNT, LiveSession
from ..models import Application, CodingSubmission, InterviewQuestion, InterviewSession, User
from ..schemas import CodeAutosave, CodeRun, CodeSubmit, PrecheckRequest
from ..security import COOKIE_NAME, resolveSession
from ..services import admission, coding, coding_bank, llm, question_compose, recording, sandbox_runner, speech, storage
from ..settings_store import getSetting
from ..timeutil import asKst, iso, now

router = APIRouter()
SUPPORTED_BROWSERS = {"chrome", "edge"}
MIN_BROWSER_VERSION = 120  # 'Chrome·Edge 최신 2개 버전'은 출시일에 따라 움직이므로 하한만 둔다
MIN_NETWORK_MBPS = 1.0
WS_CLOSE_UNAUTHORIZED = 4401
WS_CLOSE_ALREADY_USED = 4409  # 이미 쓴 세션 (새로고침 등). 화면은 상태를 다시 읽어 안내한다
WS_BASE = os.environ.get("PUBLIC_WS_BASE", "ws://127.0.0.1:8000")


def postingOpen(app: Application) -> bool:
    closeAt = asKst(app.posting.close_at)
    return closeAt is not None and now() < closeAt


@router.post("/applications/{applicationId}/precheck")
async def precheck(applicationId: str, body: PrecheckRequest, db: Session = Depends(getDb), user: User = Depends(requireApplicant)):
    app = ownedApplication(db, user, applicationId)
    if app.attempt_status not in (st.READY, st.INTERRUPTED):
        raise ApiError(409, "NOT_READY", "지금은 환경 점검을 할 수 없는 상태입니다.")
    try:
        version = int(body.browser.version.split(".")[0])
    except ValueError:
        version = 0
    try:
        mbps = float(body.network_mbps) if body.network_mbps else None
    except ValueError:
        mbps = None
    llmOk, sttOk = await asyncio.gather(llm.health(), speech.serviceHealthy(ENV.sttUrl))
    checks = {
        "browser": "ok" if body.browser.name.lower() in SUPPORTED_BROWSERS and version >= MIN_BROWSER_VERSION else "fail",
        "mic": "ok" if body.devices.mic else "fail",
        "camera": "ok" if body.devices.camera else "fail",
        "speaker": "ok" if body.devices.speaker else "fail",
        "network": "ok" if mbps is None or mbps >= MIN_NETWORK_MBPS else "fail",
        "ai_server": "ok" if llmOk and sttOk else "fail",
    }
    passed = all(v == "ok" for v in checks.values())
    validUntil = now() + timedelta(minutes=getSetting(db, "precheck_valid_min")) if passed else None
    app.precheck_valid_until = validUntil
    db.commit()
    return {"passed": passed, "checks": checks, "valid_until": iso(validUntil)}


def questionProgress(db: Session, app: Application) -> dict:
    composed = db.query(InterviewQuestion).filter_by(application_id=app.id, kind="base").count()
    return {"ready": app.questions_status == "ready", "composed": composed, "total": BASE_QUESTION_COUNT}


@router.get("/applications/{applicationId}/interview/state")
def interviewState(applicationId: str, db: Session = Depends(getDb), user: User = Depends(requireApplicant)):
    app = ownedApplication(db, user, applicationId)
    interruption = None
    if app.interruption_judged:
        interruption = {"judged": app.interruption_judged, "reason": app.end_detail if app.interruption_judged == "not_fault" else app.interruption_reason,
                        "at": iso(app.interrupted_at or app.completed_at)}
    return {
        "attempt_status": app.attempt_status, "phase": app.phase, "current_seq": app.current_seq,
        "questions": questionProgress(db, app), "interruption": interruption, "end_detail": app.end_detail,
        "precheck_valid_until": iso(app.precheck_valid_until), "resumes_left": lifecycle.resumesLeft(db, app),
        "resume_until": iso(app.posting.close_at), "release_at": iso(app.posting.release_at),
        "server_time": iso(now()),
    }


def requirePrecheck(app: Application) -> None:
    if app.precheck_valid_until is None or asKst(app.precheck_valid_until) <= now():
        raise ApiError(409, "PRECHECK_REQUIRED", "환경 점검을 다시 해 주세요. 통과 표시는 15분 동안 유효합니다.")


def newSession(db: Session, app: Application, user: User) -> InterviewSession:
    previous = db.query(InterviewSession).filter_by(application_id=app.id).count()
    row = InterviewSession(application_id=app.id, user_id=user.id, recording_segment=previous + 1)
    db.add(row)
    db.commit()
    return row


def sessionResponse(row: InterviewSession, app: Application, db: Session) -> dict:
    return {"session_id": row.id, "ws_url": f"{WS_BASE}/ws/interview/{row.id}", "question_total": BASE_QUESTION_COUNT,
            "questions_ready": app.questions_status == "ready", "recording_segment": row.recording_segment}


@router.post("/applications/{applicationId}/interview/start")
def startInterview(applicationId: str, db: Session = Depends(getDb), user: User = Depends(requireApplicant)):
    app = ownedApplication(db, user, applicationId, forUpdate=True)
    if app.attempt_consumed_at is not None or app.attempt_status in st.FINAL_STATUSES - {st.NOT_TAKEN_CLOSED}:
        raise ApiError(409, "ALREADY_ATTEMPTED", "이미 응시한 지원입니다. 응시는 1회만 할 수 있습니다.")
    if not postingOpen(app):
        raise ApiError(409, "POSTING_CLOSED", "마감 시각이 지났습니다.")
    if app.attempt_status != st.READY:
        raise ApiError(409, "NOT_READY", "이력서 제출을 먼저 마쳐 주세요.")
    requirePrecheck(app)
    if not admission.tryAcquire(db, app, getSetting(db, "max_concurrent_interviews")):
        raise ApiError(429, "CAPACITY_FULL", "지금 면접 응시자가 많습니다. 잠시 후 다시 시도해 주세요.")
    app.attempt_status = st.transition(app.attempt_status, st.INTERVIEWING)
    app.interview_started_at = now()
    db.commit()
    if app.questions_status in ("none", "failed"):
        question_compose.scheduleCompose(app.id)
    return sessionResponse(newSession(db, app, user), app, db)


@router.post("/applications/{applicationId}/interview/resume")
def resumeInterview(applicationId: str, db: Session = Depends(getDb), user: User = Depends(requireApplicant)):
    app = ownedApplication(db, user, applicationId, forUpdate=True)
    if app.attempt_status != st.INTERRUPTED:
        raise ApiError(409, "NOT_INTERRUPTED", "이어갈 수 있는 면접이 없습니다.")
    if not postingOpen(app):
        raise ApiError(409, "POSTING_CLOSED", "마감 시각이 지났습니다.")
    requirePrecheck(app)
    target = st.CODING if app.phase == "coding" else st.INTERVIEWING
    if target == st.INTERVIEWING:
        admission.forceAcquire(db, app)
    app.attempt_status = st.transition(app.attempt_status, target)
    app.interruption_judged = None
    app.interruption_reason = None
    db.commit()
    data = sessionResponse(newSession(db, app, user), app, db)
    data.update({"phase": app.phase, "resume_seq": app.current_seq})
    return data


def sessionFor(db: Session, sessionId: str, userId: str) -> tuple[InterviewSession, Application]:
    row = db.get(InterviewSession, sessionId)
    if row is None or row.user_id != userId:
        raise notFound()
    return row, db.get(Application, row.application_id)


@router.post("/interview/{sessionId}/events", status_code=204)
async def beaconEvent(sessionId: str, request: Request, db: Session = Depends(getDb)):
    """sendBeacon 수신. Content-Type 과 상관없이 본문을 직접 풀고, 못 풀어도 204 (API 명세서 6장)."""
    user = resolveSession(db, request.cookies.get(COOKIE_NAME), touch=False)
    row = db.get(InterviewSession, sessionId)
    if user is None or row is None or row.user_id != user.id:
        return Response(status_code=204)
    raw = (await request.body())[:4000]
    try:
        payload = json.loads(raw)
        kind = payload.get("type") if payload.get("type") in ("unload", "permission") else "beacon_unknown"
        detail = str(payload.get("detail") or payload.get("device") or "")
    except (json.JSONDecodeError, AttributeError, UnicodeDecodeError):
        kind, detail = "beacon_unparsed", raw.decode(errors="replace")
    app = db.get(Application, row.application_id)
    lifecycle.logEvent(db, app, kind, detail, sessionId=sessionId)
    db.commit()
    return Response(status_code=204)


@router.post("/interview/{sessionId}/recording", status_code=204)
async def recordingChunk(sessionId: str, segment_no: int = Form(ge=1), chunk_no: int = Form(ge=0, le=99999),
                         phase: str = Form(pattern="^(interview|coding)$"), file: UploadFile = File(...),
                         db: Session = Depends(getDb), user: User = Depends(requireApplicant)):
    """카메라 녹화 10초 조각 (API 명세서 6장). 같은 조각을 다시 올리면 한 번만 저장한다."""
    row, app = sessionFor(db, sessionId, user.id)
    data = await file.read(recording.CHUNK_MAX_BYTES + 1)
    recording.saveChunk(db, row, app, segment_no, chunk_no, data)
    return Response(status_code=204)


@router.websocket("/ws/interview/{sessionId}")
async def interviewSocket(ws: WebSocket, sessionId: str):
    if ws.headers.get("origin") != ENV.publicOrigin:
        await ws.close(code=WS_CLOSE_UNAUTHORIZED)
        return
    db = SessionLocal()
    try:
        user = resolveSession(db, ws.cookies.get(COOKIE_NAME))
        row = db.get(InterviewSession, sessionId)
        app = db.get(Application, row.application_id) if row else None
        ok = (user is not None and row is not None and row.user_id == user.id and row.ended_at is None
              and app is not None and app.attempt_status in st.IN_PROGRESS)
    finally:
        db.close()
    # 핸드셰이크 전에 닫으면 브라우저는 1006 만 받는다. 수락한 뒤 닫아 화면이 이유를 알 수 있게 한다
    if not ok:
        await ws.accept()
        await ws.close(code=WS_CLOSE_UNAUTHORIZED)
        return
    if not registry.claimSession(sessionId):
        await ws.accept()
        await ws.close(code=WS_CLOSE_ALREADY_USED)
        return
    await ws.accept()
    await LiveSession(ws, app.id, sessionId).serve()


# ---------- 코딩테스트 ----------

def codingApp(db: Session, sessionId: str, user: User) -> Application:
    _row, app = sessionFor(db, sessionId, user.id)
    if app.phase != "coding":
        raise ApiError(409, "NOT_CODING", "코딩테스트 단계가 아닙니다.")
    return app


def autoSubmitIfOver(db: Session, app: Application) -> None:
    if app.attempt_status == st.CODING and lifecycle.codingRemaining(app) == 0:
        coding.finishCoding(db, app)
        raise ApiError(409, "TIME_OVER", "시간이 끝나 마지막 저장 코드로 자동 제출되었습니다.")


@router.get("/coding/{sessionId}")
async def codingView(sessionId: str, db: Session = Depends(getDb), user: User = Depends(requireApplicant)):
    app = codingApp(db, sessionId, user)
    if app.attempt_status == st.CODING:
        autoSubmitIfOver(db, app)
    saved = {r.problem_no: r for r in db.query(CodingSubmission).filter_by(application_id=app.id)}
    problems = []
    for no, key in enumerate(coding_bank.SELECTED, start=1):
        view = coding_bank.publicView(no, key)
        row = saved.get(no)
        view["saved_code"] = row.code if row else view["starter"]
        view["saved_at"] = iso(row.saved_at) if row else None
        problems.append(view)
    return {"started": app.coding_started_at is not None or (app.coding_remaining_sec or 0) < getSetting(db, "coding_limit_sec"),
            "running": app.coding_started_at is not None, "remaining_sec": lifecycle.codingRemaining(app),
            "attempt_status": app.attempt_status, "away_count": app.away_count, "problems": problems,
            "auto_start_sec": getSetting(db, "coding_intro_auto_start_sec"), "release_at": iso(app.posting.release_at)}


def requireCoding(app: Application) -> None:
    if app.attempt_status != st.CODING:
        raise ApiError(409, "NOT_CODING", "코딩테스트가 진행 중이 아닙니다.")


@router.post("/coding/{sessionId}/start")
def codingStart(sessionId: str, db: Session = Depends(getDb), user: User = Depends(requireApplicant)):
    app = codingApp(db, sessionId, user)
    requireCoding(app)
    live = registry.get(app.id)
    if app.coding_started_at is None and not (live is not None and live.warned):
        app.coding_started_at = now()
        db.commit()
    return {"remaining_sec": lifecycle.codingRemaining(app)}


@router.post("/coding/{sessionId}/run")
async def codingRun(sessionId: str, body: CodeRun, db: Session = Depends(getDb), user: User = Depends(requireApplicant)):
    app = codingApp(db, sessionId, user)
    requireCoding(app)
    autoSubmitIfOver(db, app)
    key = coding_bank.SELECTED[body.problem_no - 1]
    examples = coding_bank.PROBLEMS[key]["examples"]
    try:
        result = await asyncio.to_thread(coding.runExamples, body.code, examples)
    except sandbox_runner.SandboxBusy as exc:
        raise ApiError(503, "SANDBOX_BUSY", "실행 상자가 바쁩니다. 잠시 후 다시 실행해 주세요.") from exc
    except sandbox_runner.SandboxInfraError as exc:
        raise ApiError(503, "SANDBOX_DOWN", "코드 실행 환경에 문제가 있습니다. 잠시 후 다시 실행해 주세요.") from exc
    results = []
    for r in result.get("results", []):
        expected = examples[r["no"] - 1][1]
        results.append({"example_no": r["no"], "passed": r["passed"], "expected": expected, "actual": r.get("actual"),
                        "stdout": r.get("stdout", ""), "stderr": r.get("stderr", ""), "time_ms": r.get("time_ms")})
    return {"status": result.get("status"), "results": results, "error": result.get("error")}


@router.post("/coding/{sessionId}/autosave", status_code=204)
async def codingAutosave(sessionId: str, body: CodeAutosave, db: Session = Depends(getDb), user: User = Depends(requireApplicant)):
    app = codingApp(db, sessionId, user)
    requireCoding(app)
    # 시간이 지난 뒤 들어온 저장은 받지 않는다 (마감 시점의 마지막 저장 코드로 채점)
    autoSubmitIfOver(db, app)
    row = db.query(CodingSubmission).filter_by(application_id=app.id, problem_no=body.problem_no).one_or_none()
    if row is None:
        raise notFound()
    row.code = body.code
    row.saved_at = now()
    row.paste_blocked += body.paste_blocked
    db.commit()


@router.post("/coding/{sessionId}/submit")
async def codingSubmit(sessionId: str, body: CodeSubmit, db: Session = Depends(getDb), user: User = Depends(requireApplicant)):
    app = codingApp(db, sessionId, user)
    if app.attempt_status != st.CODING:
        if app.attempt_status == st.COMPLETED:
            raise ApiError(409, "TIME_OVER", "이미 제출되었습니다.")
        raise ApiError(409, "NOT_CODING", "코딩테스트가 진행 중이 아닙니다.")
    autoSubmitIfOver(db, app)
    coding.finishCoding(db, app, {c.problem_no: c.code for c in body.codes})
    live = registry.get(app.id)
    if live is not None:
        await live.terminateFromOutside("completed")
    return {"attempt_status": app.attempt_status, "release_at": iso(app.posting.release_at)}


# ---------- 미디어 ----------

@router.get("/media/questions/{questionId}")
def questionAudio(questionId: int, db: Session = Depends(getDb), user: User = Depends(requireApplicant)):
    row = db.get(InterviewQuestion, questionId)
    if row is None or row.audio_key is None:
        raise notFound()
    ownedApplication(db, user, row.application_id)
    if row.asked_at is None:
        raise notFound()  # 아직 내지 않은 질문은 미리 들을 수 없다
    data, contentType = storage.getObject(row.audio_key)
    return Response(content=data, media_type=contentType, headers={"cache-control": "private, no-store"})
