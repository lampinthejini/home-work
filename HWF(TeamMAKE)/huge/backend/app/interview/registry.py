"""지금 연결된 면접 세션 목록. 마감·관리자 조작이 진행 중 면접을 끝낼 때 쓴다 (1단계: api 프로세스 1개 기준)."""

live: dict[str, "object"] = {}  # application_id → LiveSession
# 세션 토큰은 한 번만 연결할 수 있다. 새로고침으로 다시 붙어 '창 닫기 = 응시 종료' 판정을 피하지 못하게 한다 (PRD 7-2)
connectedSessions: set[str] = set()


def claimSession(sessionId: str) -> bool:
    if sessionId in connectedSessions:
        return False
    connectedSessions.add(sessionId)
    return True


def get(applicationId: str):
    return live.get(applicationId)


def register(applicationId: str, session) -> None:
    live[applicationId] = session


def unregister(applicationId: str, session) -> None:
    if live.get(applicationId) is session:
        live.pop(applicationId, None)


async def terminateMany(applicationIds: list[str], reason: str, detail: str | None = None) -> None:
    for applicationId in applicationIds:
        session = live.get(applicationId)
        if session is not None:
            await session.terminateFromOutside(reason, detail)
