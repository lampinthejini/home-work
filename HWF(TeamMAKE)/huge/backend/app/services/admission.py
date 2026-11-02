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
    app.holds_seat = True
    app.seat_released_at = None
    db.commit()
    return True


def forceAcquire(db: Session, app: Application) -> None:
    """이어가기: N 을 다시 확인하지 않고 들어온다 (TRD 5-3)."""
    if app.holds_seat:
        return
    redisClient().incr(ACTIVE_KEY)
    app.holds_seat = True
    app.seat_released_at = None
    db.commit()


def release(db: Session, app: Application) -> None:
    if not app.holds_seat:
        return
    redisClient().eval(RELEASE_LUA, 1, ACTIVE_KEY)
    app.holds_seat = False
    app.seat_released_at = now()
    db.commit()


def reconcile(db: Session) -> int:
    """Redis 숫자를 holds_seat 가 켜진 면접 수로 다시 맞춘다 (seat_reconcile_interval_min)."""
    count = db.query(Application).filter(Application.holds_seat.is_(True)).count()
    redisClient().set(ACTIVE_KEY, count)
    return count
