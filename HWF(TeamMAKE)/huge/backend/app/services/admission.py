"""동시 면접 입장 관리 (TRD 5-3, ADR-08). Redis Lua 로 비교와 더하기를 한 번에 한다.

자리 표시(applications.holds_seat)를 함께 바꿔 같은 면접이 두 번 더하거나 빼지 않게 한다.
자동 보호(GPU 메모리 92%·다음 질문 시간)는 2단계에서 붙인다.
"""

import redis
from sqlalchemy.orm import Session

from ..config import ENV
from ..models import Application
from ..timeutil import now

ACTIVE_KEY = "interview:active"
PENDING_PREFIX = "interview:pending:"  # Redis 에 더했지만 DB 커밋 전인 입장. reconcile 이 빼먹지 않게 한다 (E10)
PENDING_TTL_SEC = 60

ACQUIRE_LUA = """
local active = tonumber(redis.call('GET', KEYS[1]) or '0')
if active < tonumber(ARGV[1]) then
  redis.call('INCR', KEYS[1])
  return 1
end
return 0
"""

RELEASE_LUA = """
local active = tonumber(redis.call('GET', KEYS[1]) or '0')
if active > 0 then redis.call('DECR', KEYS[1]) end
return 1
"""

_redis = None


def redisClient() -> redis.Redis:
    global _redis
    if _redis is None:
        _redis = redis.Redis.from_url(ENV.redisUrl)
    return _redis


def tryAcquire(db: Session, app: Application, limit: int) -> bool:
    if app.holds_seat:
        return True
    if not redisClient().eval(ACQUIRE_LUA, 1, ACTIVE_KEY, limit):
        return False
    markPending(app)
    # 커밋은 부른 쪽이 상태 전환과 함께 한다. 여기서 커밋하면 FOR UPDATE 잠금이 풀려 시작이 두 번 통과한다 (E10)
    app.holds_seat = True
    app.seat_released_at = None
    db.flush()
    return True


def forceAcquire(db: Session, app: Application) -> None:
    """이어가기: N 을 다시 확인하지 않고 들어온다 (TRD 5-3)."""
    if app.holds_seat:
        return
    redisClient().incr(ACTIVE_KEY)
    markPending(app)
    app.holds_seat = True
    app.seat_released_at = None
    db.flush()


def release(db: Session, app: Application) -> None:
    if not app.holds_seat:
        return
    redisClient().eval(RELEASE_LUA, 1, ACTIVE_KEY)
    redisClient().delete(f"{PENDING_PREFIX}{app.id}")
    app.holds_seat = False
    app.seat_released_at = now()
    db.commit()


def reconcile(db: Session) -> int:
    """Redis 숫자를 holds_seat 가 켜진 면접 수(커밋 전 입장 포함)로 다시 맞춘다. jobs 의 1분 주기 작업이 부른다."""
    holding = {appId for (appId,) in db.query(Application.id).filter(Application.holds_seat.is_(True)).all()}
    pending = {key.decode().removeprefix(PENDING_PREFIX) for key in redisClient().scan_iter(f"{PENDING_PREFIX}*")}
    count = len(holding | pending)
    redisClient().set(ACTIVE_KEY, count)
    return count


def markPending(app: Application) -> None:
    redisClient().set(f"{PENDING_PREFIX}{app.id}", 1, ex=PENDING_TTL_SEC)
