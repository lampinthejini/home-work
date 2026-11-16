"""관리자 회사 정보 (2026-11-16 사용자 결정, CONFLICTS C-20).

회사 정보(기본 정보·회사 소개·직무 소개·AI/AX 가 하는 일)를 보고 고치고, 회사 최근 소식(제목·링크)을 보고 [제거]한다.
최근 소식은 앱을 켤 때 새로 찾고, [새로 찾기]로 지금 찾을 수도 있다.
"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..db import getDb
from ..deps import requireAdmin
from ..errors import notFound
from ..models import User
from ..services import company

router = APIRouter(prefix="/admin/company")

TEXT_MAX = 3000


def companyView(db: Session) -> dict:
    return {"profile": company.profileView(company.getProfile(db)),
            "news": [company.newsView(n) for n in company.listNews(db)], "news_limit": company.NEWS_LIMIT}


@router.get("")
def getCompany(db: Session = Depends(getDb), _admin: User = Depends(requireAdmin)):
    return companyView(db)


class ProfileIn(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    basics: str | None = Field(default=None, max_length=TEXT_MAX)
    intro: str | None = Field(default=None, max_length=TEXT_MAX)
    jobs_intro: str | None = Field(default=None, max_length=TEXT_MAX)
    ai_ax_role: str | None = Field(default=None, max_length=TEXT_MAX)
    news_query: str | None = Field(default=None, min_length=1, max_length=100)


@router.put("")
def updateCompany(body: ProfileIn, db: Session = Depends(getDb), admin: User = Depends(requireAdmin)):
    values = {k: v.strip() for k, v in body.model_dump().items() if v is not None}
    company.updateProfile(db, admin.id, values)
    return companyView(db)


@router.post("/news/refresh")
async def refreshNews(db: Session = Depends(getDb), admin: User = Depends(requireAdmin)):
    result = await company.refreshNews(admin.id)
    db.expire_all()
    return {**companyView(db), "refresh": result}


@router.post("/news/{newsId}/hide")
def hideNews(newsId: int, db: Session = Depends(getDb), admin: User = Depends(requireAdmin)):
    if not company.hideNews(db, admin.id, newsId):
        raise notFound()
    return companyView(db)
