"""비밀번호 해시(Argon2id)와 로그인 세션(HttpOnly 쿠키, 2시간 미끄러짐 만료) — TRD 11장."""

import hashlib
import secrets
from datetime import timedelta

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from sqlalchemy.orm import Session

from .models import LoginSession, User
from .settings_store import getSetting
from .timeutil import asKst, now

COOKIE_NAME = "huge_session"
hasher = PasswordHasher()


def hashPassword(password: str) -> str:
    return hasher.hash(password)


def verifyPassword(passwordHash: str, password: str) -> bool:
    try:
        return hasher.verify(passwordHash, password)
    except (VerifyMismatchError, InvalidHashError):
        return False


def tokenHash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def createSession(db: Session, user: User) -> str:
    token = secrets.token_urlsafe(32)
    hours = getSetting(db, "session_idle_hours")
    db.add(LoginSession(token_hash=tokenHash(token), user_id=user.id, expires_at=now() + timedelta(hours=hours)))
    db.commit()
    return token


def resolveSession(db: Session, token: str | None, touch: bool = True) -> User | None:
    if not token:
        return None
    row = db.get(LoginSession, tokenHash(token))
    if row is None or asKst(row.expires_at) <= now():
        return None
    if touch:
        row.expires_at = now() + timedelta(hours=getSetting(db, "session_idle_hours"))
        db.commit()
    return db.get(User, row.user_id)


def dropSession(db: Session, token: str | None) -> None:
    if not token:
        return
    row = db.get(LoginSession, tokenHash(token))
    if row:
        db.delete(row)
        db.commit()


SAFE_NEXT_PREFIXES = ("/jobs", "/apply/", "/exam/", "/mypage")


def safeNext(nextPath: str | None) -> str | None:
    """로그인 복귀 경로는 내부 경로 허용 목록만 받는다 (ACC-04). 화면 라우트 기준 (화면정의서 Tech-16)."""
    if not nextPath or not nextPath.startswith("/") or nextPath.startswith("//") or nextPath.startswith("/\\"):
        return None
    if "://" in nextPath:
        return None
    return nextPath if nextPath.startswith(SAFE_NEXT_PREFIXES) else None
