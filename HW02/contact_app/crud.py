import secrets

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import models, schemas, security

DEFAULT_CATEGORIES = ["가족", "친구", "기타"]


# ---- users / sessions ----

def get_user_by_username(db: Session, username: str) -> models.User | None:
    return db.execute(
        select(models.User).where(models.User.username == username)
    ).scalar_one_or_none()


def get_user(db: Session, user_id: int) -> models.User | None:
    return db.get(models.User, user_id)


def create_user(db: Session, username: str, password: str) -> models.User:
    if get_user_by_username(db, username) is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="이미 사용 중인 아이디입니다.")

    user = models.User(username=username, password_hash=security.hash_password(password))
    db.add(user)
    db.flush()

    for name in DEFAULT_CATEGORIES:
        db.add(models.Category(user_id=user.id, name=name))

    db.commit()
    db.refresh(user)
    return user


def authenticate_user(db: Session, username: str, password: str) -> models.User | None:
    user = get_user_by_username(db, username)
    if user is None:
        return None
    if not security.verify_password(password, user.password_hash):
        return None
    return user


def get_login_session(db: Session, session_id: str) -> models.LoginSession | None:
    return db.get(models.LoginSession, session_id)


def create_login_session(db: Session, user_id: int) -> models.LoginSession:
    session = models.LoginSession(session_id=secrets.token_hex(32), user_id=user_id)
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


def delete_login_session(db: Session, session_id: str) -> None:
    session = db.get(models.LoginSession, session_id)
    if session is not None:
        db.delete(session)
        db.commit()


# ---- categories ----

def list_categories(db: Session, user_id: int) -> list[models.Category]:
    return list(
        db.execute(
            select(models.Category)
            .where(models.Category.user_id == user_id)
            .order_by(models.Category.id)
        ).scalars()
    )


def get_my_category(db: Session, user_id: int, category_id: int) -> models.Category | None:
    return db.execute(
        select(models.Category).where(
            models.Category.id == category_id, models.Category.user_id == user_id
        )
    ).scalar_one_or_none()


def _get_category_by_name(db: Session, user_id: int, name: str) -> models.Category | None:
    return db.execute(
        select(models.Category).where(
            models.Category.user_id == user_id, models.Category.name == name
        )
    ).scalar_one_or_none()


def create_category(db: Session, user_id: int, name: str) -> models.Category:
    if _get_category_by_name(db, user_id, name) is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="이미 존재하는 카테고리 이름입니다.")

    category = models.Category(user_id=user_id, name=name)
    db.add(category)
    db.commit()
    db.refresh(category)
    return category


def update_category(db: Session, category: models.Category, name: str) -> models.Category:
    existing = _get_category_by_name(db, category.user_id, name)
    if existing is not None and existing.id != category.id:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="이미 존재하는 카테고리 이름입니다.")

    category.name = name
    db.commit()
    db.refresh(category)
    return category


def count_contacts_in_category(db: Session, user_id: int, category_id: int) -> int:
    return db.execute(
        select(func.count()).select_from(models.Contact).where(
            models.Contact.user_id == user_id, models.Contact.category_id == category_id
        )
    ).scalar_one()


def delete_category(db: Session, category: models.Category) -> None:
    count = count_contacts_in_category(db, category.user_id, category.id)
    if count > 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"이 카테고리를 사용하는 연락처가 {count}건 있어 삭제할 수 없습니다.",
        )
    db.delete(category)
    db.commit()


# ---- contacts ----

def list_contacts(
    db: Session, user_id: int, name: str | None = None, category_id: int | None = None
) -> list[models.Contact]:
    stmt = select(models.Contact).where(models.Contact.user_id == user_id).order_by(models.Contact.id)
    if name:
        stmt = stmt.where(models.Contact.name.contains(name))
    if category_id is not None:
        stmt = stmt.where(models.Contact.category_id == category_id)
    return list(db.execute(stmt).scalars())


def get_my_contact(db: Session, user_id: int, contact_id: int) -> models.Contact | None:
    return db.execute(
        select(models.Contact).where(
            models.Contact.id == contact_id, models.Contact.user_id == user_id
        )
    ).scalar_one_or_none()


def _get_contact_by_phone(db: Session, user_id: int, phone: str) -> models.Contact | None:
    return db.execute(
        select(models.Contact).where(
            models.Contact.user_id == user_id, models.Contact.phone == phone
        )
    ).scalar_one_or_none()


def create_contact(db: Session, user_id: int, data: schemas.ContactCreate) -> models.Contact:
    if get_my_category(db, user_id, data.category_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="카테고리를 찾을 수 없습니다.")

    if _get_contact_by_phone(db, user_id, data.phone) is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="이미 등록된 전화번호입니다.")

    contact = models.Contact(user_id=user_id, **data.model_dump())
    db.add(contact)
    db.commit()
    db.refresh(contact)
    return contact


def update_contact(db: Session, contact: models.Contact, data: schemas.ContactUpdate) -> models.Contact:
    updates = data.model_dump(exclude_unset=True)

    if "phone" in updates and updates["phone"] != contact.phone:
        if _get_contact_by_phone(db, contact.user_id, updates["phone"]) is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="이미 등록된 전화번호입니다.")

    if "category_id" in updates:
        if get_my_category(db, contact.user_id, updates["category_id"]) is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="카테고리를 찾을 수 없습니다.")

    for key, value in updates.items():
        setattr(contact, key, value)

    db.commit()
    db.refresh(contact)
    return contact


def delete_contact(db: Session, contact: models.Contact) -> None:
    db.delete(contact)
    db.commit()
