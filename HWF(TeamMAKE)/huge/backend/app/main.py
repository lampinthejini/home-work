"""Huge API — Team AIIT. 화면은 Next.js 가 /api/* 를 이 서버로 넘겨 같은 출처로 부른다 (TRD 3장)."""

import asyncio
import logging
import re
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from . import jobs, migrate
from .db import Base, SessionLocal, engine
from .domain import status as st
from .errors import ApiError, apiErrorHandler, unexpectedErrorHandler, validationErrorHandler
from .interview import checkpoint, lifecycle
from .models import Application, InterviewSession
from .routers import admin, admin_ops, admin_questions, applications, auth, interview, me, postings
from .services import admission, llm, question_compose, resume_extract, storage
from .services.postings import seedJobCodes
from .settings_store import getSetting
from .timeutil import now

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("huge")
backgroundTasks: set[asyncio.Task] = set()


async def warmUp() -> None:
    """첫 LLM 호출은 프롬프트 처리에 45초가 걸렸다(2026-10-30 실측). 첫 지원자가 기다리지 않게 미리 부른다."""
    from pydantic import BaseModel

    class Ping(BaseModel):
        ok: bool

    try:
        await llm.structured(Ping, "JSON 으로만 답한다.", "ok=true 로 답하라.", timeoutSec=120, maxTokens=20)
        log.info("llm warm-up done")
    except llm.LlmError as exc:
        log.warning("llm warm-up failed: %s", exc)


def recoverAfterRestart() -> None:
    """재시작 전 '질문 구성 중'이던 지원은 다시 구성하고, 끊긴 이력서 추출은 실패로 두고, Redis 자리 수를 DB 에 맞춘다."""
    db = SessionLocal()
    try:
        resume_extract.failUnfinished(db)
        for app in db.query(Application).filter(Application.questions_status == "composing").all():
            app.questions_status = "none"
            db.commit()
            question_compose.scheduleCompose(app.id)
        # 재시작으로 끊긴 면접: 이 프로세스에 붙은 세션이 하나도 없으므로 모두 원인 미상 장애로 돌린다 (TRD 7-2)
        for app in db.query(Application).filter(Application.attempt_status.in_(st.IN_PROGRESS)).all():
            lifecycle.markInterrupted(db, app, "unknown")
        db.query(InterviewSession).filter(InterviewSession.ended_at.is_(None)).update({"ended_at": now()})
        db.commit()
        admission.reconcile(db)
    finally:
        db.close()


def spawn(coro) -> None:
    task = asyncio.get_running_loop().create_task(coro)
    backgroundTasks.add(task)
    task.add_done_callback(backgroundTasks.discard)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    Base.metadata.create_all(engine)
    migrate.addColumns(engine)
    with SessionLocal() as db:
        seedJobCodes(db)
    await asyncio.to_thread(storage.ensureBucket)
    recoverAfterRestart()
    await checkpoint.openSaver()  # 면접 진행 그래프 체크포인트 (ADR-07)
    spawn(warmUp())
    spawn(jobs.runForever())
    yield
    for task in list(backgroundTasks):
        task.cancel()
    await checkpoint.closeSaver()


UPLOAD_PATH = re.compile(r"/applications/[^/]+/resume/upload")
MULTIPART_OVERHEAD_BYTES = 1024 * 1024


def uploadLimitBytes() -> int:
    with SessionLocal() as db:
        return getSetting(db, "upload_max_mb") * 1024 * 1024 + MULTIPART_OVERHEAD_BYTES


class UploadSizeGuard:
    """FastAPI 는 본문을 임시 파일로 다 받은 뒤 핸들러를 부른다. 큰 요청은 그 전에 Content-Length 로 거절한다.

    브라우저 업로드에는 항상 길이가 있고, 길이보다 많이 보내면 uvicorn 이 끊는다. 그래서 길이가 없으면 받지 않는다.
    """

    def __init__(self, inner):
        self.inner = inner

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and scope["method"] == "POST" and UPLOAD_PATH.fullmatch(scope["path"]):
            length = dict(scope["headers"]).get(b"content-length", b"")
            if not length.isdigit():
                return await JSONResponse({"code": "LENGTH_REQUIRED", "message": "이력서를 불러오는 데 실패했습니다."}, 411)(scope, receive, send)
            if int(length) > await asyncio.to_thread(uploadLimitBytes):
                return await JSONResponse({"code": "FILE_TOO_LARGE", "message": "이력서를 불러오는 데 실패했습니다."}, 413)(scope, receive, send)
        await self.inner(scope, receive, send)


app = FastAPI(title="Huge API (Team AIIT)", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
app.add_middleware(UploadSizeGuard)
app.add_exception_handler(ApiError, apiErrorHandler)
app.add_exception_handler(RequestValidationError, validationErrorHandler)
app.add_exception_handler(Exception, unexpectedErrorHandler)
for module in (auth, postings, applications, interview, me, admin_ops, admin_questions, admin):
    app.include_router(module.router)


@app.get("/health")
def health():
    return {"status": "ok"}
