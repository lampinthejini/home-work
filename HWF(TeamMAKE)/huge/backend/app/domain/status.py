"""응시 상태 전이 (TRD 7-1, 기술 아키텍처 6-4 상태도). 상태 원장은 applications.attempt_status."""

DRAFTING = "drafting"
READY = "ready"
INTERVIEWING = "interviewing"
CODING = "coding"
INTERRUPTED = "interrupted"
COMPLETED = "completed"
ENDED = "ended"
ENDED_CLOSED = "ended_closed"
CANCELLED = "cancelled"
NOT_TAKEN_CLOSED = "not_taken_closed"

FINAL_STATUSES = {COMPLETED, ENDED, ENDED_CLOSED, CANCELLED, NOT_TAKEN_CLOSED}
IN_PROGRESS = {INTERVIEWING, CODING}

ALLOWED = {
    DRAFTING: {READY, NOT_TAKEN_CLOSED},
    READY: {INTERVIEWING, NOT_TAKEN_CLOSED},
    INTERVIEWING: {CODING, COMPLETED, INTERRUPTED, ENDED, CANCELLED, ENDED_CLOSED},
    CODING: {COMPLETED, INTERRUPTED, ENDED, CANCELLED, ENDED_CLOSED},
    INTERRUPTED: {INTERVIEWING, CODING, ENDED_CLOSED},
}


class TransitionError(Exception):
    pass


def transition(current: str, target: str) -> str:
    if target not in ALLOWED.get(current, set()):
        raise TransitionError(f"{current} → {target} 는 허용되지 않는 전이입니다")
    return target


def statusOnClose(current: str) -> str | None:
    """공고 마감 시각의 처리 (INT-10, D-04). 바꿀 필요가 없으면 None."""
    if current in (DRAFTING, READY):
        return NOT_TAKEN_CLOSED
    if current in (INTERVIEWING, CODING, INTERRUPTED):
        return ENDED_CLOSED
    return None


def nextAction(status: str, released: bool) -> str | None:
    """마이페이지 카드 버튼 (API 명세서 9장 next_action, 화면정의서 §3.4)."""
    if status == DRAFTING:
        return "continue_draft"
    if status == READY:
        return "precheck"
    if status == INTERRUPTED:
        return "resume"
    if status in (COMPLETED, ENDED, ENDED_CLOSED, CANCELLED) and released:
        return "view_result"
    return None


def judgeDisconnect(recentEventTypes: set[str]) -> str:
    """끊기기 직전 unload_lookback_sec 안의 기록으로 판단 (TRD 7-2). 원인 모름은 지원자에게 유리하게 '장애'."""
    if recentEventTypes & {"unload", "permission"}:
        return "not_fault"
    return "fault"


MY_APPLICATIONS_ORDER = {INTERRUPTED: 0, READY: 1, DRAFTING: 2}
