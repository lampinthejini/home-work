"""인증·계정 API (API 명세서 3장)."""

import secrets
from datetime import timedelta

from fastapi import APIRouter, BackgroundTasks, Depends, Request, Response
from sqlalchemy.orm import Session

from .. import db as dbModule
from .. import worker
from ..config import ENV
from ..db import getDb
from ..deps import currentUser, requireApplicant
from ..domain.password_policy import checkPassword
from ..errors import ApiError
from ..models import AuditLog, LoginSession, User
from ..schemas import LoginRequest, MePatch, PasswordChangeRequest, PasswordResetConfirm, PasswordResetRequest, SignupRequest, WithdrawRequest
from ..security import COOKIE_NAME, createSession, dropSession, hashPassword, safeNext, tokenHash, verifyPassword
from ..services import admission, login_block, withdrawal
from ..settings_store import getSetting
from ..timeutil import asKst, iso, now

router = APIRouter()


def policyError(password: str, email: str) -> None:
    violations = checkPassword(password, email)
    if violations:
        raise ApiError(400, "PASSWORD_POLICY", " · ".join(violations))


def userView(user: User) -> dict:
    return {
        "user_id": user.id,
        "email": user.email,
        "name": user.name,
        "phone": user.phone,
        "role": user.role,
        "password_change_required": user.must_change_password,
    }


@router.post("/auth/signup", status_code=201)
def signup(body: SignupRequest, db: Session = Depends(getDb)):
    email = body.email.strip().lower()
    a = body.agreements
    if not (a.age_14_plus and a.terms and a.privacy):
        raise ApiError(400, "AGREEMENT_REQUIRED", "필수 동의 항목에 모두 동의해 주세요.")
    policyError(body.password, email)
    if db.query(User).filter(User.email == email).first():
        raise ApiError(409, "EMAIL_TAKEN", "이미 가입된 이메일입니다.")
    user = User(email=email, password_hash=hashPassword(body.password), name=body.name.strip(), phone=body.phone,
                role="applicant", agreements={**a.model_dump(), "agreed_at": iso(now())})
    db.add(user)
    db.commit()
    return {"user_id": user.id, "email": user.email}


# 없는 계정도 같은 시간만큼 해시 검증을 해서, 응답 시간으로 가입 여부를 알 수 없게 한다
DUMMY_HASH = hashPassword("dummy-password-for-timing")
COOKIE_SECURE = ENV.publicOrigin.startswith("https://")
INVALID_MESSAGE = "이메일 또는 비밀번호가 올바르지 않습니다. 계속 안 되면 잠시 뒤 다시 시도해 주세요."


def countAdminFailure(db: Session, user: User) -> None:
    """관리자 계정만 잠근다. 뚫렸을 때 피해가 크고, 일부러 잠가도 10분 불편에 그친다."""
    user.failed_logins += 1
    if user.failed_logins >= getSetting(db, "login_fail_limit"):
        user.locked_until = now() + timedelta(minutes=getSetting(db, "login_lock_min"))
        user.failed_logins = 0


@router.post("/auth/login")
def login(body: LoginRequest, request: Request, response: Response, db: Session = Depends(getDb)):
    ipKey = login_block.guardKey(request)
    block = login_block.activeBlock(db, ipKey)
    # 실패 횟수를 세는 동안 같은 계정의 다른 로그인 시도를 기다리게 한다 (병렬 시도로 잠금 우회 방지)
    user = db.query(User).filter(User.email == body.email.strip().lower()).with_for_update().first()
    isAdmin = user is not None and user.role == "admin"
    adminLocked = isAdmin and user.locked_until is not None and asKst(user.locked_until) > now()
    valid = verifyPassword(user.password_hash if user else DUMMY_HASH, body.password) and user is not None
    if adminLocked or not valid:
        if isAdmin and not adminLocked:
            countAdminFailure(db, user)
        if ipKey:
            block = login_block.recordFailure(db, ipKey)
        failure = login_block.blockedError(db, block) if block else ApiError(401, "INVALID_CREDENTIALS", INVALID_MESSAGE)
        db.commit()
        raise failure
    if block and not isAdmin:
        raise login_block.blockedError(db, block)
    user.failed_logins = 0
    user.locked_until = None
    db.commit()
    token = createSession(db, user)
    response.set_cookie(COOKIE_NAME, token, httponly=True, samesite="lax", secure=COOKIE_SECURE, path="/")
    if user.role == "admin":
        redirect = "/password/change" if user.must_change_password else "/admin/postings"
    else:
        redirect = safeNext(body.next) or "/jobs"
    return {"user_id": user.id, "role": user.role, "password_change_required": user.must_change_password, "redirect": redirect}


@router.post("/auth/logout", status_code=204)
def logout(request: Request, response: Response, db: Session = Depends(getDb)):
    dropSession(db, request.cookies.get(COOKIE_NAME))
    response.delete_cookie(COOKIE_NAME, path="/")


@router.get("/auth/me")
def me(user: User = Depends(currentUser)):
    return userView(user)


@router.post("/auth/password-change", status_code=204)
def passwordChange(body: PasswordChangeRequest, request: Request, user: User = Depends(currentUser), db: Session = Depends(getDb)):
    if not verifyPassword(user.password_hash, body.current_password):
        raise ApiError(400, "WRONG_PASSWORD", "현재 비밀번호가 올바르지 않습니다.")
    if body.current_password == body.new_password:
        raise ApiError(400, "SAME_AS_OLD", "지금과 다른 비밀번호를 입력해 주세요.")
    policyError(body.new_password, user.email)
    user.password_hash = hashPassword(body.new_password)
    user.must_change_password = False
    # 다른 기기의 로그인은 끊는다 (지금 쓰는 세션만 남김)
    current = tokenHash(request.cookies.get(COOKIE_NAME) or "")
    db.query(LoginSession).filter(LoginSession.user_id == user.id, LoginSession.token_hash != current).delete()
    db.commit()


RESET_TTL_SEC = 30 * 60
RESET_WAIT_SEC = 60  # 같은 주소로 1분에 한 통만 (메일 폭탄 방지)


def sendResetLink(email: str) -> None:
    """응답을 보낸 뒤에 돈다. 그래서 가입 여부에 따라 응답 시간이 달라지지 않는다."""
    redis = admission.redisClient()
    if not redis.set(f"pw_reset_wait:{tokenHash(email)}", "1", nx=True, ex=RESET_WAIT_SEC):
        return
    with dbModule.SessionLocal() as db:
        user = db.query(User).filter(User.email == email).first()
        if user is None:
            return
        userId = user.id
    token = secrets.token_urlsafe(32)
    previous = redis.get(f"pw_reset_user:{userId}")
    if previous:
        redis.delete(f"pw_reset:{previous.decode()}")  # 새 링크를 보내면 이전 링크는 못 쓴다
    redis.set(f"pw_reset:{tokenHash(token)}", userId, ex=RESET_TTL_SEC)
    redis.set(f"pw_reset_user:{userId}", tokenHash(token), ex=RESET_TTL_SEC)
    worker.queueResetMail(email, f"{ENV.publicOrigin}/password/reset?token={token}")


@router.post("/auth/password-reset", status_code=202)
def passwordReset(body: PasswordResetRequest, background: BackgroundTasks):
    """결과와 상관없이 202. 가입 여부를 드러내지 않는다 (S-C03 ①)."""
    background.add_task(sendResetLink, body.email.strip().lower())
    return {"status": "accepted"}


def expiredToken() -> ApiError:
    return ApiError(400, "TOKEN_EXPIRED", "링크가 만료되었습니다(30분). 다시 요청해 주세요.")


@router.post("/auth/password-reset/confirm", status_code=204)
def passwordResetConfirm(body: PasswordResetConfirm, db: Session = Depends(getDb)):
    redis = admission.redisClient()
    key = f"pw_reset:{tokenHash(body.token)}"
    userId = redis.get(key)
    user = db.get(User, userId.decode()) if userId else None
    if user is None:
        raise expiredToken()
    policyError(body.new_password, user.email)  # 규칙에 안 맞으면 토큰을 남겨 다시 입력할 수 있게 한다
    if not redis.delete(key):  # 한 번만 쓴다 (동시에 두 번 눌러도 한쪽만 통과)
        raise expiredToken()
    redis.delete(f"pw_reset_user:{user.id}")
    user.password_hash = hashPassword(body.new_password)
    db.query(LoginSession).filter(LoginSession.user_id == user.id).delete()  # 모든 기기 로그아웃
    db.add(AuditLog(actor_id=user.id, action="password.reset", target=user.id))
    db.commit()


@router.post("/me/withdraw", status_code=204)
async def withdrawMe(body: WithdrawRequest, response: Response, user: User = Depends(requireApplicant), db: Session = Depends(getDb)):
    """탈퇴: 진행 중 응시 취소, 응시 데이터·계정 즉시 삭제 (API 명세서 3장). 같은 이메일로 다시 가입할 수 있다."""
    if not verifyPassword(user.password_hash, body.password):
        raise ApiError(400, "WRONG_PASSWORD", "비밀번호가 올바르지 않습니다.")
    if body.confirm_text.strip() != "탈퇴":
        raise ApiError(400, "CONFIRM_TEXT", "확인란에 '탈퇴'를 입력해 주세요.")
    await withdrawal.withdrawAccount(db, user)
    response.delete_cookie(COOKIE_NAME, path="/")


@router.patch("/me")
def patchMe(body: MePatch, user: User = Depends(requireApplicant), db: Session = Depends(getDb)):
    if body.name is not None:
        user.name = body.name.strip()
    if body.phone is not None:
        user.phone = body.phone
    db.commit()
    return userView(user)
