"""코딩테스트 제출·채점 (PRD COD-01~06, API 명세서 8장).

채점은 숨겨진 테스트 통과 비율만 낸다. 점수 합산·AI 판정은 채점 worker 가 한다.
실행 상자는 api 가 아니라 worker-sandbox(큐 sandbox)만 만든다 — api 에 docker.sock 을 주지 않는다 (ADR-09, R-06).
"""

import logging

from sqlalchemy.orm import Session

from ..db import SessionLocal
from ..domain import status as st
from ..interview import lifecycle
from ..models import Application, CodingSubmission
from ..timeutil import now
from . import coding_bank, sandbox_runner

log = logging.getLogger("huge.coding")
GRADED_STATUSES = {st.COMPLETED, st.ENDED, st.ENDED_CLOSED}  # 응시 취소는 평가하지 않는다
RUN_WAIT_SEC = 40  # [실행] 응답을 기다리는 한도 (상자 10초 + 다른 실행 대기)


def scheduleGrade(applicationId: str) -> None:
    """숨겨진 테스트 채점을 worker-sandbox 에 넣는다. 같은 건은 5분 안에 다시 넣지 않는다."""
    from .. import worker
    worker.enqueueGrade(applicationId)


def runExamples(code: str, cases: list[tuple[str, str]]) -> dict:
    """[실행]: worker-sandbox 에서 예시 입력으로 돌리고 결과를 기다린다. 못 받으면 인프라 오류 (오답 아님)."""
    from .. import worker
    try:
        result = worker.celery.send_task(worker.SANDBOX_RUN_TASK, args=[code, [list(c) for c in cases]], queue="sandbox",
                                         expires=RUN_WAIT_SEC, retry=False)
    except Exception as exc:  # noqa: BLE001 — 브로커 오류
        raise sandbox_runner.SandboxInfraError(type(exc).__name__) from exc
    try:
        out = result.get(timeout=RUN_WAIT_SEC)
    except Exception as exc:  # noqa: BLE001 — 시간 초과·브로커 오류
        raise sandbox_runner.SandboxInfraError(type(exc).__name__) from exc
    finally:
        result.forget()
    if out.get("infra") == "busy":
        raise sandbox_runner.SandboxBusy()
    if out.get("infra"):
        raise sandbox_runner.SandboxInfraError(out["infra"])
    return out


def saveCodes(db: Session, app: Application, codes: dict[int, str]) -> None:
    for row in db.query(CodingSubmission).filter_by(application_id=app.id):
        if row.problem_no in codes:
            row.code = codes[row.problem_no]
            row.saved_at = now()
        row.final = True
    db.commit()


def finishCoding(db: Session, app: Application, codes: dict[int, str] | None = None) -> None:
    """제출 또는 시간 끝 자동 제출. 응시 완료로 바꾸고 숨겨진 테스트 채점을 뒤에서 돌린다."""
    saveCodes(db, app, codes or {})
    lifecycle.finish(db, app, st.COMPLETED, "coding_submitted" if codes else "coding_timeout")
    scheduleGrade(app.id)


def gradeAll(applicationId: str) -> None:
    """worker-sandbox 안에서만 부른다."""
    db = SessionLocal()
    try:
        rows = (db.query(CodingSubmission).filter_by(application_id=applicationId)
                .filter((CodingSubmission.grade_status.is_(None)) | (CodingSubmission.grade_status == "infra_error"))
                .order_by(CodingSubmission.problem_no))
        for row in rows:
            hidden = coding_bank.PROBLEMS[row.problem_key]["hidden"]
            try:
                result = sandbox_runner.run(row.code, hidden)
            except (sandbox_runner.SandboxBusy, sandbox_runner.SandboxInfraError) as exc:
                # 인프라 오류는 오답이 아니다 → 다시 채점할 수 있게 표시만 한다 (기술 아키텍처 6-6)
                log.warning("grading deferred for %s/%d: %s", applicationId, row.problem_no, type(exc).__name__)
                row.grade_status = "infra_error"
                db.commit()
                continue
            results = result.get("results", [])
            row.total = len(hidden)
            row.passed = sum(1 for r in results if r.get("passed"))
            row.grade_status = result.get("status", "runtime_error")
            db.commit()
    finally:
        db.close()
