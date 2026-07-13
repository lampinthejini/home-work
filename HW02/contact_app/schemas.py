from typing import Optional

from pydantic import BaseModel, Field, model_validator


class SignupRequest(BaseModel):
    username: str = Field(pattern=r"^[a-z0-9]{4,20}$")
    password: str = Field(min_length=4, max_length=20)
    password_confirm: str

    @model_validator(mode="after")
    def check_passwords_match(self):
        if self.password != self.password_confirm:
            raise ValueError("비밀번호와 비밀번호 확인이 일치하지 않습니다.")
        return self


class LoginRequest(BaseModel):
    username: str
    password: str


class ContactCreate(BaseModel):
    name: str = Field(min_length=1, max_length=5)
    phone: str = Field(pattern=r"^010\d{8}$")
    addr: str = ""
    category_id: int


class ContactUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=5)
    phone: Optional[str] = Field(default=None, pattern=r"^010\d{8}$")
    addr: Optional[str] = None
    category_id: Optional[int] = None


class ContactResponse(BaseModel):
    id: int
    name: str
    phone: str
    addr: str
    category_id: int
    category_name: str

    model_config = {"from_attributes": True}


class ContactListResponse(BaseModel):
    total: int
    items: list[ContactResponse]


class CategoryCreate(BaseModel):
    name: str = Field(min_length=1, max_length=10)


class CategoryResponse(BaseModel):
    id: int
    name: str

    model_config = {"from_attributes": True}
