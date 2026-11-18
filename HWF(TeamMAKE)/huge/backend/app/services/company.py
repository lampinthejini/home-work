"""회사 정보와 회사 프로젝트 (2026-11-16 사용자 결정 CONFLICTS C-20, 2026-11-17 C-21 로 바뀜).

- 회사 정보: 가상 회사 AIIT(네이버를 모티프로 함)의 기본 정보·회사 소개·경영 이념·인재상·직무 소개·AI/AX 가 하는 일·사내 기술 스택.
  관리자가 고칠 수 있다. 처음 값은 company_defaults.py (회사 소개서 PDF, C-22).
- 회사 기술 블로그: tech_blog.py (C-22).
- 회사 프로젝트: 회사가 진행한 프로젝트(이름·기간·내용)를 관리자가 적는다. 코드에 넣어 두지 않는다 (사용자 결정 2026-11-17).
  예전의 '최근 소식'(뉴스 자동 찾기)은 지웠다.
- 회사 질문 RAG: 회사 정보는 늘 넣고, 프로젝트는 찾을 글과 가장 비슷한 것 몇 개만 넣는다 (pgvector, SQLite 에서는 먼저 적은 순).
- AI 공고 초안: 회사 정보(직무 소개 포함)와 그 공고와 가까운 프로젝트 몇 개를 넣는다.
임베딩이 실패해도 저장·면접·게시에는 영향이 없다 (비어 있는 임베딩은 앱을 켤 때 다시 채운다).
"""

import logging
import re

from sqlalchemy import text
from sqlalchemy.orm import Session

from ..models import AuditLog, CompanyProfile, CompanyProject, JobPosting
from . import rag
from .company_defaults import DEFAULT_PROFILE

log = logging.getLogger("huge.company")

PROJECT_LIMIT = 30
CONTEXT_PROJECT_COUNT = 2  # 회사 질문 하나에 넣는 프로젝트 수
POSTING_PROJECT_COUNT = 2  # AI 공고 초안에 넣는 프로젝트 수
CONTEXT_TEXT_CHARS = 280  # 회사 질문에 회사 정보 칸마다 넣는 글자 수 (실측 2026-11-17: 350자·프로젝트 3개면 프롬프트 3,200토큰)
POSTING_TEXT_CHARS = 180  # 공고 초안에 칸마다 넣는 글자 수 (칸이 더 많다. 실측 2026-11-17: 초안 프롬프트 약 2,700토큰 + 출력 최대 1,500)
PROJECT_TEXT_CHARS = 220  # 프로젝트 하나의 내용을 프롬프트에 넣는 글자 수
PROFILE_FIELDS = ("name", "basics", "intro", "mission", "talent", "jobs_intro", "ai_ax_role", "tech_stack",
                  "tech_feed_url", "tech_source_name")
PROJECT_FIELDS = ("title", "period", "summary")

def getProfile(db: Session) -> CompanyProfile:
    """회사 정보 한 줄. 없으면 기본값으로 만들고, 회사명이 빈 공고에 회사 이름을 넣는다."""
    profile = db.get(CompanyProfile, 1)
    if profile is None:
        profile = CompanyProfile(id=1, **DEFAULT_PROFILE)
        db.add(profile)
        db.query(JobPosting).filter(JobPosting.company_name == "").update({"company_name": profile.name})
        db.commit()
    return profile


def profileView(profile: CompanyProfile) -> dict:
    return {**{f: getattr(profile, f) for f in PROFILE_FIELDS},
            "tech_refreshed_at": profile.tech_refreshed_at.isoformat() if profile.tech_refreshed_at else None}


def updateProfile(db: Session, actorId: str, values: dict) -> CompanyProfile:
    """회사 정보를 고친다. 이름이 바뀌면 모든 공고의 회사명도 바꾼다 (한 기업 전용)."""
    profile = getProfile(db)
    changed = [f for f in PROFILE_FIELDS if f in values and values[f] is not None and values[f] != getattr(profile, f)]
    for field in changed:
        setattr(profile, field, values[field])
    if "name" in changed:
        db.query(JobPosting).update({"company_name": profile.name})
    db.add(AuditLog(actor_id=actorId, action="company.update", target="company_profile", detail={"fields": changed}))
    db.commit()
    return profile


# ---------- 회사 프로젝트 ----------

def projectView(p: CompanyProject) -> dict:
    return {"id": p.id, "title": p.title, "period": p.period, "summary": p.summary}


def listProjects(db: Session) -> list[CompanyProject]:
    return db.query(CompanyProject).order_by(CompanyProject.id).all()


def addProject(db: Session, actorId: str, values: dict) -> CompanyProject | None:
    """프로젝트를 더한다. PROJECT_LIMIT 개가 차 있으면 None."""
    if db.query(CompanyProject).count() >= PROJECT_LIMIT:
        return None
    project = CompanyProject(**{f: values.get(f, "") for f in PROJECT_FIELDS})
    db.add(project)
    db.flush()
    db.add(AuditLog(actor_id=actorId, action="company.project_add", target=str(project.id), detail={}))
    db.commit()
    return project


def updateProject(db: Session, actorId: str, projectId: int, values: dict) -> CompanyProject | None:
    project = db.get(CompanyProject, projectId)
    if project is None:
        return None
    changed = [f for f in PROJECT_FIELDS if f in values and values[f] is not None and values[f] != getattr(project, f)]
    for field in changed:
        setattr(project, field, values[field])
    if changed and rag.supported(db):
        db.execute(text("UPDATE company_projects SET embedding = NULL WHERE id = :id"), {"id": project.id})
    db.add(AuditLog(actor_id=actorId, action="company.project_update", target=str(projectId), detail={"fields": changed}))
    db.commit()
    return project


def deleteProject(db: Session, actorId: str, projectId: int) -> bool:
    project = db.get(CompanyProject, projectId)
    if project is None:
        return False
    db.delete(project)
    db.add(AuditLog(actor_id=actorId, action="company.project_delete", target=str(projectId), detail={}))
    db.commit()
    return True


def projectLine(p: CompanyProject, chars: int = PROJECT_TEXT_CHARS) -> str:
    head = p.title + (f" ({p.period})" if p.period else "")
    return f"- {head}: {p.summary[:chars]}" if p.summary else f"- {head}"


async def embedMissingProjects(db: Session, timeoutSec: float = 60) -> int:
    """임베딩이 빈 프로젝트를 채운다 (저장 직후, 앱을 켤 때). 실패하면 다음에 다시."""
    if not rag.supported(db):
        return 0
    ids = [r.id for r in db.execute(text("SELECT id FROM company_projects WHERE embedding IS NULL")).all()]
    projects = [db.get(CompanyProject, i) for i in ids]
    if not projects:
        return 0
    try:
        vectors = await rag.embed([projectLine(p) for p in projects], timeoutSec=timeoutSec)
    except rag.EmbedUnavailable as exc:
        log.warning("company project embed failed: %s", exc)
        return 0
    for project, vector in zip(projects, vectors, strict=True):
        db.execute(text("UPDATE company_projects SET embedding = CAST(:v AS vector) WHERE id = :id"),
                   {"v": rag.toLiteral(vector), "id": project.id})
    db.commit()
    return len(projects)


def relatedProjects(db: Session, vector: list[float] | None, count: int) -> list[CompanyProject]:
    """찾을 글과 가장 비슷한 프로젝트 count 개 (RAG). 벡터가 없거나 SQLite 면 먼저 적은 순."""
    if vector is not None and rag.supported(db):
        rows = db.execute(text(
            "SELECT id FROM company_projects WHERE embedding IS NOT NULL "
            "ORDER BY embedding <=> CAST(:v AS vector) LIMIT :n"), {"v": rag.toLiteral(vector), "n": count}).all()
        if rows:
            return [db.get(CompanyProject, r.id) for r in rows]
    return listProjects(db)[:count]


# ---------- 질문·공고에 넣는 회사 정보 ----------

# 프롬프트에 넣는 칸 (라벨, 칸). 회사 질문과 공고 초안이 쓰는 칸이 다르다.
# llm-rt 는 요청 하나에 4,096 토큰이라(8,192 를 2개가 나눠 씀) 칸마다 앞부분만 넣는다.
QUESTION_FIELDS = (("기본 정보", "basics"), ("회사 소개", "intro"), ("경영 이념", "mission"), ("인재상과 일하는 방식", "talent"),
                   ("AI/AX 가 하는 일", "ai_ax_role"))
POSTING_FIELDS = (("기본 정보", "basics"), ("회사 소개", "intro"), ("직무 소개", "jobs_intro"), ("AI/AX 가 하는 일", "ai_ax_role"),
                  ("인재상과 일하는 방식", "talent"), ("사내 기술 스택", "tech_stack"))


def profileText(profile: CompanyProfile, fields=QUESTION_FIELDS, chars: int = CONTEXT_TEXT_CHARS) -> str:
    parts = [f"회사 이름: {profile.name}"] + [f"{label}: {(getattr(profile, key) or '')[:chars]}" for label, key in fields]
    return "\n".join(p for p in parts if not p.endswith(": "))


# 회사 정보에 따옴표로 적힌 고유 이름 (예: 'AIIT-X', '마루 1') — 직무 질문에 넣지 않는다 (2026-11-18 실측)
QUOTED_NAME = re.compile(r"['‘’\"“”]([^'‘’\"“”\n]{2,20})['‘’\"“”]")


def properTerms(db: Session) -> list[str]:
    """지원자는 모를 회사 고유 이름: 회사 이름(이름으로 시작하는 'AIIT-X' 같은 이름도 걸림)과 회사 정보 안 따옴표 이름."""
    profile = getProfile(db)
    body = "\n".join(getattr(profile, key) or "" for key in PROFILE_FIELDS if key not in ("name", "tech_feed_url"))
    return list(dict.fromkeys([profile.name, *QUOTED_NAME.findall(body)]))


def withProjects(base: str, projects: list[CompanyProject]) -> str:
    return base + ("\n회사가 진행한 프로젝트:\n" + "\n".join(projectLine(p) for p in projects) if projects else "")


def pickPosts(db: Session, vector: list[float] | None, used: set[int] | None = None) -> list:
    """가까운 기술 글. used 에 든 글(같은 면접의 앞 질문이 쓴 글)은 빼고, 다 썼으면 처음부터 다시 쓴다."""
    from . import tech_blog

    used = set() if used is None else used
    posts = tech_blog.relatedPosts(db, vector, tech_blog.CONTEXT_POST_COUNT, used)
    if not posts and used:
        used.clear()
        posts = tech_blog.relatedPosts(db, vector, tech_blog.CONTEXT_POST_COUNT, used)
    used.update(p.id for p in posts)
    return posts


def techLines(db: Session, vector: list[float] | None, used: set[int] | None = None) -> str:
    """질문 프롬프트에 넣는 기술 글 줄 (회사 질문·직무 질문 공통, 2026-11-17 사용자: 직무 질문에도 쓸 수 있음)."""
    from . import tech_blog

    profile = getProfile(db)
    return "\n".join(tech_blog.promptLine(p, profile) for p in pickPosts(db, vector, used))


def questionContext(db: Session, vector: list[float] | None, usedPosts: set[int] | None = None) -> str:
    """회사 질문에 넣는 회사 정보 + 관련 프로젝트 + 관련 기술 글 (usedPosts 에 든 글은 뺀다)."""
    profile = getProfile(db)
    context = withProjects(profileText(profile), relatedProjects(db, vector, CONTEXT_PROJECT_COUNT))
    lines = techLines(db, vector, usedPosts)
    return context + ("\n회사가 요즘 다루는 기술 (지원자는 모를 수 있음):\n" + lines if lines else "")


def postingContext(db: Session, vector: list[float] | None = None, projectCount: int = POSTING_PROJECT_COUNT) -> str:
    """AI 공고 초안에 넣는 회사 정보 (직무 소개·인재상·기술 스택 포함) + 그 공고와 가까운 프로젝트."""
    projects = relatedProjects(db, vector, projectCount) if projectCount else []
    return withProjects(profileText(getProfile(db), POSTING_FIELDS, POSTING_TEXT_CHARS), projects)
