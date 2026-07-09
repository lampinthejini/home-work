from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from .. import crud, models, schemas
from ..database import get_db
from .auth import get_current_user

router = APIRouter(prefix="/contacts", tags=["contacts"])


def _to_response(contact: models.Contact) -> schemas.ContactResponse:
    return schemas.ContactResponse(
        id=contact.id,
        name=contact.name,
        phone=contact.phone,
        addr=contact.addr,
        category_id=contact.category_id,
        category_name=contact.category.name,
    )


@router.post("", response_model=schemas.ContactResponse, status_code=status.HTTP_201_CREATED)
def create(
    data: schemas.ContactCreate,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    contact = crud.create_contact(db, current_user.id, data)
    return _to_response(contact)


@router.get("")
def read(
    name: Optional[str] = None,
    category_id: Optional[int] = None,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    contacts = crud.list_contacts(db, current_user.id, name=name, category_id=category_id)
    items = [_to_response(c) for c in contacts]
    return {"total": len(items), "items": items}


@router.patch("/{contact_id}", response_model=schemas.ContactResponse)
def update(
    contact_id: int,
    data: schemas.ContactUpdate,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    contact = crud.get_my_contact(db, current_user.id, contact_id)
    if contact is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="연락처를 찾을 수 없습니다.")
    contact = crud.update_contact(db, contact, data)
    return _to_response(contact)


@router.delete("/{contact_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete(
    contact_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    contact = crud.get_my_contact(db, current_user.id, contact_id)
    if contact is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="연락처를 찾을 수 없습니다.")
    crud.delete_contact(db, contact)
