"""로그인 실패 IP 차단. 계정과 무관하게 세어 계정 존재를 드러내지 않고, 남의 계정을 일부러 잠글 수도 없게 한다.

X-Forwarded-For 는 frontend 를 거친 요청에서만 믿고, 가장 오른쪽 값(가장 가까운 프록시가 적은 값)을 쓴다.
Next.js 는 받은 헤더를 그대로 넘기고 없으면 만들지 않는다. 그래서 헤더가 없으면 앞단 프록시가 없는 이 PC 안 접속으로 보고
frontend 주소를 쓰며, 외부에 공개할 때는 앞단 프록시가 이 헤더를 진짜 IP 로 덮어써야 한다.
"""

import ipaddress
import logging
import secrets
import socket
from datetime import timedelta

from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..config import ENV
from ..crypto import ipHash
from ..errors import ApiError
from ..models import AuditLog, LoginBlock
from ..settings_store import getSetting
from ..timeutil import asKst, now

log = logging.getLogger("huge")
UNKNOWN_IP = "unknown"


def isTrustedProxy(peer: str) -> bool:
    if not ENV.trustedProxyHost:
        return False
    try:
        return socket.gethostbyname(ENV.trustedProxyHost) == peer
    except OSError:
        return False


def normalizeIp(raw: str) -> str:
    try:
        ip = ipaddress.ip_address(raw.strip())
    except ValueError:
        return UNKNOWN_IP
    return str(getattr(ip, "ipv4_mapped", None) or ip)


def clientIp(request) -> str:
    peer = request.client.host if request.client else ""
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded and isTrustedProxy(peer):
        return normalizeIp(forwarded.split(",")[-1])
    return normalizeIp(peer)


def isExempt(ip: str) -> bool:
    if ip == UNKNOWN_IP:
        return False
    address = ipaddress.ip_address(ip)
    for item in filter(None, (part.strip() for part in ENV.loginExemptIps.split(","))):
        try:
            if address in ipaddress.ip_network(item, strict=False):
                return True
        except ValueError:
            log.warning("LOGIN_EXEMPT_IPS has an invalid entry")
    return False


def guardKey(request) -> str | None:
    """차단을 세는 키. 제외 대상이면 None."""
    ip = clientIp(request)
    return None if isExempt(ip) else ipHash(ip)


def isActive(row: LoginBlock | None) -> bool:
    return bool(row and row.blocked_until and asKst(row.blocked_until) > now())


def activeBlock(db: Session, key: str | None) -> LoginBlock | None:
    row = db.get(LoginBlock, key) if key else None
    return row if isActive(row) else None


def lockedRow(db: Session, key: str) -> LoginBlock:
    """처음 보는 IP 의 동시 요청이 겹쳐도 한 행으로 센다."""
    row = db.get(LoginBlock, key, with_for_update=True)
    if row is not None:
        return row
    try:
        with db.begin_nested():
            row = LoginBlock(ip_hash=key, fail_count=0, window_started_at=now())
            db.add(row)
        return row
    except IntegrityError:
        return db.get(LoginBlock, key, with_for_update=True)


def recordFailure(db: Session, key: str) -> LoginBlock | None:
    """실패 한 번을 센다. 차단 중이면 그 행을 돌려준다. 커밋은 부르는 쪽에서 한다."""
    row = lockedRow(db, key)
    if isActive(row):
        return row
    current = now()
    window = timedelta(minutes=getSetting(db, "login_block_window_min"))
    if row.blocked_until or asKst(row.window_started_at) + window <= current:
        row.fail_count, row.window_started_at = 0, current
        row.code, row.blocked_at, row.blocked_until = None, None, None
    row.fail_count += 1
    if row.fail_count < getSetting(db, "login_fail_limit"):
        return None
    row.code = secrets.token_hex(3).upper()
    row.blocked_at = current
    row.blocked_until = current + timedelta(hours=getSetting(db, "login_block_hours"))
    db.add(AuditLog(action="login_block.block", target=row.code, detail={"fail_count": row.fail_count}))
    return row


def blockedError(db: Session, row: LoginBlock) -> ApiError:
    until = asKst(row.blocked_until).strftime("%m월 %d일 %H:%M")
    return ApiError(429, "LOGIN_BLOCKED", f"로그인 실패가 반복되어 이 네트워크의 로그인을 제한했습니다. {until}에 자동으로 풀립니다. "
                                          f"바로 풀려면 문의 코드 {row.code} 를 담당자에게 알려 주세요.")


def activeBlocks(db: Session) -> list[LoginBlock]:
    return (db.query(LoginBlock).filter(LoginBlock.blocked_until > now())
            .order_by(LoginBlock.blocked_at.desc()).all())


def release(db: Session, code: str, adminId: str) -> bool:
    rows = db.query(LoginBlock).filter(LoginBlock.code == code.upper(), LoginBlock.blocked_until > now()).all()
    for row in rows:
        db.delete(row)
        db.add(AuditLog(actor_id=adminId, action="login_block.release", target=row.code))
    return bool(rows)


def purgeExpired(db: Session) -> int:
    """차단도 집계 기간도 끝난 행을 지운다. 커밋은 부르는 쪽에서 한다."""
    current = now()
    windowStart = current - timedelta(minutes=getSetting(db, "login_block_window_min"))
    return db.query(LoginBlock).filter(or_(
        LoginBlock.blocked_until <= current,
        LoginBlock.blocked_until.is_(None) & (LoginBlock.window_started_at <= windowStart),
    )).delete(synchronize_session=False)
