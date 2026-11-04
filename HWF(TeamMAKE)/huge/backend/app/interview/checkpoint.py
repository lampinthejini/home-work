"""LangGraph 체크포인트 저장소 (ADR-07, TRD 7-5, 테이블 정의서 LangGraph 체크포인트 표 3개).

면접 진행 그래프의 thread_id 는 지원 번호다. 상태 원장은 여전히 applications 이고, 체크포인트는 그래프를
이어 가는 데만 쓴다 (AI 아키텍처 6.1). 그래프 상태에는 번호·시각·사유만 넣고 답변·이력서 글은 넣지 않는다.

PostgreSQL 이면 AsyncPostgresSaver(테이블은 setup() 이 만든다), 그 밖(개발용 SQLite·테스트)은 메모리.
"""

import logging

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import InMemorySaver
from sqlalchemy import text
from sqlalchemy.orm import Session

from ..config import ENV

log = logging.getLogger("huge.checkpoint")

CHECKPOINT_TABLES = ("checkpoint_writes", "checkpoint_blobs", "checkpoints")

_saver: BaseCheckpointSaver | None = None
_pool = None


def conninfo() -> str | None:
    url = ENV.databaseUrl
    if not url.startswith("postgresql"):
        return None
    return url.replace("postgresql+psycopg://", "postgresql://", 1)


async def openSaver() -> None:
    """api 시작 때 한 번. 체크포인트 표가 없으면 만든다."""
    global _saver, _pool
    info = conninfo()
    if info is None:
        _saver = InMemorySaver()
        return
    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
    from psycopg.rows import dict_row
    from psycopg_pool import AsyncConnectionPool

    _pool = AsyncConnectionPool(info, min_size=1, max_size=4, open=False,
                                kwargs={"autocommit": True, "prepare_threshold": 0, "row_factory": dict_row})
    await _pool.open()
    _saver = AsyncPostgresSaver(_pool)
    await _saver.setup()
    log.info("langgraph checkpoint store ready (postgres)")


async def closeSaver() -> None:
    global _saver, _pool
    if _pool is not None:
        await _pool.close()
    _pool = None
    _saver = None


def saver() -> BaseCheckpointSaver:
    global _saver
    if _saver is None:  # 테스트처럼 api 시작 과정을 거치지 않은 경우
        _saver = InMemorySaver()
    return _saver


def deleteThread(db: Session, threadId: str) -> int:
    """지원 1건의 체크포인트를 같은 트랜잭션에서 지운다 (보관 삭제·동의 철회·탈퇴). 지운 체크포인트 수."""
    if isinstance(_saver, InMemorySaver):
        _saver.delete_thread(threadId)
    if db.get_bind().dialect.name != "postgresql":
        return 0
    if db.execute(text("SELECT to_regclass('public.checkpoints')")).scalar() is None:
        return 0  # api 가 한 번도 시작되지 않아 표가 아직 없다
    count = db.execute(text("SELECT count(*) FROM checkpoints WHERE thread_id = :t"), {"t": threadId}).scalar() or 0
    for table in CHECKPOINT_TABLES:
        db.execute(text(f"DELETE FROM {table} WHERE thread_id = :t"), {"t": threadId})
    return int(count)
