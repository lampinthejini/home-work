"""관리자 회사 정보 (2026-11-16 사용자 결정 CONFLICTS C-20, 2026-11-17 C-21).

회사 정보(기본 정보·회사 소개·경영 이념·인재상·직무 소개·AI/AX 가 하는 일·기술 스택)를 보고 고치고,
회사가 진행한 프로젝트를 적고 고치고 지우고, 회사 기술 블로그 글을 새로 가져오거나 [제거]한다 (C-22).
회사 질문과 AI 공고 초안이 이 내용을 쓴다.
"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..db import getDb
from ..deps import requireAdmin
from ..errors import ApiError, notFound
from ..models import User
from ..services import company, tech_blog

router = APIRouter(prefix="/admin/company")

TEXT_MAX = 3000
PROJECT_SUMMARY_MAX = 1000
EMBED_ON_SAVE_SEC = 10  # 저장 직후 임베딩. 못 하면 앱을 켤 때 채운다


def noTitle() -> ApiError:
    return ApiError(422, "VALIDATION_ERROR", "프로젝트 이름을 적어 주세요.")


def companyView(db: Session) -> dict:
    profile = company.getProfile(db)
    return {"profile": company.profileView(profile),
            "projects": [company.projectView(p) for p in company.listProjects(db)], "project_limit": company.PROJECT_LIMIT,
            "tech_posts": [tech_blog.postView(p, profile) for p in tech_blog.listPosts(db)], "tech_post_limit": tech_blog.POST_LIMIT}


def stripped(body: BaseModel) -> dict:
    return {k: v.strip() for k, v in body.model_dump().items() if v is not None}


@router.get("")
def getCompany(db: Session = Depends(getDb), _admin: User = Depends(requireAdmin)):
    return companyView(db)


class ProfileIn(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    basics: str | None = Field(default=None, max_length=TEXT_MAX)
    intro: str | None = Field(default=None, max_length=TEXT_MAX)
    jobs_intro: str | None = Field(default=None, max_length=TEXT_MAX)
    ai_ax_role: str | None = Field(default=None, max_length=TEXT_MAX)
    mission: str | None = Field(default=None, max_length=TEXT_MAX)
    talent: str | None = Field(default=None, max_length=TEXT_MAX)
    tech_stack: str | None = Field(default=None, max_length=TEXT_MAX)
    tech_feed_url: str | None = Field(default=None, max_length=500, pattern=r"^(https://\S+)?$")  # 비우면 가져오지 않음
    tech_source_name: str | None = Field(default=None, max_length=100)


@router.put("")
def updateCompany(body: ProfileIn, db: Session = Depends(getDb), admin: User = Depends(requireAdmin)):
    company.updateProfile(db, admin.id, stripped(body))
    return companyView(db)


class ProjectIn(BaseModel):
    title: str = Field(min_length=1, max_length=100)
    period: str = Field(default="", max_length=50)
    summary: str = Field(default="", max_length=PROJECT_SUMMARY_MAX)


class ProjectPatch(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=100)
    period: str | None = Field(default=None, max_length=50)
    summary: str | None = Field(default=None, max_length=PROJECT_SUMMARY_MAX)


@router.post("/tech/refresh")
async def refreshTech(db: Session = Depends(getDb), admin: User = Depends(requireAdmin)):
    result = await tech_blog.refreshPosts(admin.id)
    db.expire_all()
    return {**companyView(db), "refresh": result}


@router.post("/tech/{postId}/hide")
def hideTech(postId: int, db: Session = Depends(getDb), admin: User = Depends(requireAdmin)):
    if not tech_blog.hidePost(db, admin.id, postId):
        raise notFound()
    return companyView(db)


@router.post("/projects")
async def addProject(body: ProjectIn, db: Session = Depends(getDb), admin: User = Depends(requireAdmin)):
    values = stripped(body)
    if not values["title"]:
        raise noTitle()
    if company.addProject(db, admin.id, values) is None:
        raise ApiError(409, "PROJECT_LIMIT", f"프로젝트는 {company.PROJECT_LIMIT}개까지 적을 수 있습니다.")
    await company.embedMissingProjects(db, EMBED_ON_SAVE_SEC)
    return companyView(db)


@router.patch("/projects/{projectId}")
async def updateProject(projectId: int, body: ProjectPatch, db: Session = Depends(getDb), admin: User = Depends(requireAdmin)):
    values = stripped(body)
    if values.get("title") == "":
        raise noTitle()
    if company.updateProject(db, admin.id, projectId, values) is None:
        raise notFound()
    await company.embedMissingProjects(db, EMBED_ON_SAVE_SEC)
    return companyView(db)


@router.delete("/projects/{projectId}")
def deleteProject(projectId: int, db: Session = Depends(getDb), admin: User = Depends(requireAdmin)):
    if not company.deleteProject(db, admin.id, projectId):
        raise notFound()
    return companyView(db)
