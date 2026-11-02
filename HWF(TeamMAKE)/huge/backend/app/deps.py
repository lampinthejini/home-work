"""인증·인가 의존성. 남의 데이터는 404 로 숨긴다 (ACC-06, 기술 아키텍처 10장 require_owner)."""

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from .db import getDb
from .errors import ApiError, notFound
from .models import Application, User
from .security import COOKIE_NAME, resolveSession


def optionalUser(request: Request, db: Session = Depends(getDb)) -> User | None:
    return resolveSession(db, request.cookies.get(COOKIE_NAME))


def currentUser(user: User | None = Depends(optionalUser)) -> User:
    if user is None:
        raise ApiError(401, "LOGIN_REQUIRED", "로그인이 필요합니다.")
    return user


def activeUser(user: User = Depends(currentUser)) -> User:
    """관리자 초기 비밀번호를 바꾸기 전에는 비밀번호 변경·로그아웃·내 정보 말고는 막는다."""
    if user.must_change_password:
        raise ApiError(403, "PASSWORD_CHANGE_REQUIRED", "비밀번호를 먼저 변경해 주세요.")
    return user


def requireApplicant(user: User = Depends(activeUser)) -> User:
    if user.role != "applicant":
        raise ApiError(403, "FORBIDDEN", "접근 권한이 없습니다.")
    return user


def requireAdmin(user: User = Depends(activeUser)) -> User:
    if user.role != "admin":
        raise ApiError(403, "FORBIDDEN", "접근 권한이 없습니다.")
    return user


def ownedApplication(db: Session, user: User, applicationId: str, forUpdate: bool = False) -> Application:
    query = db.query(Application).filter(Application.id == applicationId, Application.user_id == user.id)
    if forUpdate and db.bind.dialect.name == "postgresql":
        query = query.with_for_update()
    app = query.one_or_none()
    if app is None:
        raise notFound()
    return app
