from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from .. import crud, models, schemas
from ..database import get_db
from .auth import get_current_user

router = APIRouter(prefix="/categories", tags=["categories"])


@router.get("", response_model=list[schemas.CategoryResponse])
def read_categories(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return crud.list_categories(db, current_user.id)


@router.post("", response_model=schemas.CategoryResponse, status_code=status.HTTP_201_CREATED)
def create(
    data: schemas.CategoryCreate,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return crud.create_category(db, current_user.id, data.name)


@router.patch("/{category_id}", response_model=schemas.CategoryResponse)
def update(
    category_id: int,
    data: schemas.CategoryCreate,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    category = crud.get_my_category(db, current_user.id, category_id)
    if category is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="카테고리를 찾을 수 없습니다.")
    return crud.update_category(db, category, data.name)


@router.delete("/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete(
    category_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    category = crud.get_my_category(db, current_user.id, category_id)
    if category is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="카테고리를 찾을 수 없습니다.")
    crud.delete_category(db, category)
