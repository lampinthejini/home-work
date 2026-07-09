from typing import Optional

from fastapi import APIRouter, Cookie, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from .. import crud, models, schemas
from ..database import get_db

router = APIRouter(prefix="/auth", tags=["auth"])


def get_current_user(
    session_id: Optional[str] = Cookie(default=None),
    db: Session = Depends(get_db),
) -> models.User:
    if session_id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="로그인이 필요합니다.")

    session = crud.get_login_session(db, session_id)
    if session is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="로그인이 필요합니다.")

    user = crud.get_user(db, session.user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="로그인이 필요합니다.")

    return user


@router.post("/signup", status_code=status.HTTP_201_CREATED)
def signup(data: schemas.SignupRequest, db: Session = Depends(get_db)):
    user = crud.create_user(db, data.username, data.password)
    return {"id": user.id, "username": user.username}


@router.post("/login")
def login(data: schemas.LoginRequest, response: Response, db: Session = Depends(get_db)):
    user = crud.authenticate_user(db, data.username, data.password)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="아이디 또는 비밀번호가 올바르지 않습니다.",
        )

    session = crud.create_login_session(db, user.id)
    response.set_cookie(
        key="session_id",
        value=session.session_id,
        httponly=True,
        secure=False,
        samesite="lax",
    )
    return {"message": "로그인 성공"}


@router.post("/logout")
def logout(
    response: Response,
    session_id: Optional[str] = Cookie(default=None),
    db: Session = Depends(get_db),
):
    if session_id is not None:
        crud.delete_login_session(db, session_id)
    response.delete_cookie("session_id")
    return {"message": "로그아웃 되었습니다"}


@router.get("/me")
def me(current_user: models.User = Depends(get_current_user)):
    return {"id": current_user.id, "username": current_user.username}
