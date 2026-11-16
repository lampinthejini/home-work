"""회사 정보와 최근 소식 (2026-11-16 사용자 결정, CONFLICTS C-20).

- 회사 정보: 가상 회사 AIIT(네이버를 모티프로 함)의 기본 정보·회사 소개·직무 소개·AI/AX 가 하는 일. 관리자가 고칠 수 있다.
- 최근 소식: 앱을 켤 때 검색어(기본 '네이버')로 최근 6개월 뉴스를 Google 뉴스 RSS 에서 찾아 최대 NEWS_LIMIT 개를 둔다.
  한 번에 찾으면 그날 기사만 나와서(실측 2026-11-16: 30개 모두 당일) 한 달씩 6번 찾아 달마다 몇 개씩 고른다.
  제목에 검색어나 회사 이름이 없는 기사는 회사 소식이 아니라고 보고 뺀다 (aboutCompany).
  사용자 결정으로 모티프 회사의 뉴스를 AIIT 소식으로 쓴다 — 질문에 넣을 때는 검색어를 회사 이름으로 바꾼다.
  관리자가 [제거]한 소식은 hidden_at 을 남겨 다음에 다시 들어오지 않는다.
- 회사 질문 RAG: 회사 정보는 늘 넣고, 최근 소식은 찾을 글과 가장 비슷한 것 몇 개만 넣는다 (pgvector, SQLite 에서는 최신 순).
실패해도 면접·게시에는 영향이 없다 (기록만 남긴다).
"""

import asyncio
import logging
import re
import xml.etree.ElementTree as ET
from datetime import date, timedelta
from email.utils import parsedate_to_datetime

import httpx
from sqlalchemy import text
from sqlalchemy.orm import Session

from ..db import SessionLocal
from ..models import AuditLog, CompanyNews, CompanyProfile, JobPosting
from ..timeutil import now
from . import rag

log = logging.getLogger("huge.company")

NEWS_LIMIT = 30
NEWS_MONTHS_DAYS = 183  # 최근 6개월
NEWS_WINDOWS = 6  # 한 달씩 나눠 찾는다
NEWS_TIMEOUT_SEC = 15
NEWS_URL = "https://news.google.com/rss/search"
CONTEXT_NEWS_COUNT = 3  # 회사 질문 하나에 넣는 소식 수
CONTEXT_TEXT_CHARS = 400  # 회사 정보 칸마다 프롬프트에 넣는 글자 수
PROFILE_FIELDS = ("name", "basics", "intro", "jobs_intro", "ai_ax_role", "news_query")

# 처음 켤 때 넣는 회사 정보. 네이버를 모티프로 한 가상 회사라 숫자·연혁은 지어낸 것이다
DEFAULT_PROFILE = {
    "name": "AIIT",
    "basics": (
        "회사명: AIIT 주식회사\n"
        "설립: 2001년\n"
        "본사: 경기도 성남시 분당구 (사옥 'AIIT 그린타워')\n"
        "임직원: 약 4,500명\n"
        "주요 서비스: AIIT 검색, AIIT 쇼핑, AIIT 페이, AIIT 웹툰, AIIT 클라우드, AIIT 지도\n"
        "핵심 가치: 사용자 중심 · 기술로 연결 · 함께 성장"
    ),
    "intro": (
        "AIIT는 국내 최대 검색 포털에서 출발해 커머스·핀테크·콘텐츠·클라우드로 사업을 넓힌 인터넷 플랫폼 기업입니다. "
        "하루 수천만 명이 쓰는 검색과 쇼핑, 결제, 웹툰 서비스를 운영하며, 자체 초거대 언어 모델 'AIIT-X'를 바탕으로 "
        "모든 서비스에 AI를 붙이고 있습니다. 작은 조직이 스스로 목표를 정하고 빠르게 실험하는 문화를 중요하게 여깁니다."
    ),
    "jobs_intro": (
        "- 서비스 개발: 검색·쇼핑·페이·웹툰 서비스의 백엔드와 프론트엔드를 만듭니다.\n"
        "- 데이터·검색: 검색 품질, 추천, 광고 랭킹을 데이터로 개선합니다.\n"
        "- AI/AX 엔지니어: 초거대 언어 모델과 AI 기술을 서비스와 사내 업무에 적용합니다.\n"
        "- 클라우드·인프라: AIIT 클라우드와 데이터센터, GPU 학습 환경을 운영합니다.\n"
        "- 서비스 기획·디자인: 사용자 경험을 설계하고 새 서비스를 기획합니다."
    ),
    "ai_ax_role": (
        "- AIIT-X 기반 검색 요약, 쇼핑 AI 에이전트, 고객 상담 챗봇 같은 생성형 AI 서비스를 만듭니다.\n"
        "- RAG와 사내 문서 검색으로 임직원의 반복 업무를 줄이는 업무 혁신(AX)을 이끕니다.\n"
        "- 모델 파인튜닝·경량화와 MLOps로 AI 모델을 안정적으로 배포하고 운영합니다.\n"
        "- 데이터 파이프라인을 만들고, AI 결과의 품질과 안전성(편향·개인정보)을 점검합니다.\n"
        "- 현업 부서와 함께 AI로 바꿀 업무를 찾고 효과를 측정합니다."
    ),
    "news_query": "네이버",
}


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
            "news_refreshed_at": profile.news_refreshed_at.isoformat() if profile.news_refreshed_at else None}


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


def visibleNews(db: Session):
    return db.query(CompanyNews).filter(CompanyNews.hidden_at.is_(None))


def newsView(n: CompanyNews) -> dict:
    return {"id": n.id, "title": n.title, "url": n.url, "publisher": n.publisher,
            "published_at": n.published_at.isoformat() if n.published_at else None}


def listNews(db: Session) -> list[CompanyNews]:
    return visibleNews(db).order_by(CompanyNews.published_at.desc().nullslast(), CompanyNews.id.desc()).all()


def hideNews(db: Session, actorId: str, newsId: int) -> bool:
    item = db.get(CompanyNews, newsId)
    if item is None or item.hidden_at is not None:
        return False
    item.hidden_at = now()
    db.add(AuditLog(actor_id=actorId, action="company.news_hide", target=str(newsId), detail={}))
    db.commit()
    return True


# ---------- 최근 소식 찾기 ----------

def parseRss(xmlText: str) -> list[dict]:
    """Google 뉴스 RSS → [{title, url, publisher, published_at}]. 제목 끝의 ' - 언론사'는 따로 뗀다."""
    items = []
    for item in ET.fromstring(xmlText).iter("item"):
        title = (item.findtext("title") or "").strip()
        url = (item.findtext("link") or "").strip()
        if not title or not url.startswith("https://"):
            continue
        publisher = (item.findtext("source") or "").strip()
        if publisher and title.endswith(f" - {publisher}"):
            title = title[: -len(publisher) - 3].strip()
        try:
            published = parsedate_to_datetime(item.findtext("pubDate") or "")
        except (TypeError, ValueError):
            published = None
        items.append({"title": title[:300], "url": url[:1000], "publisher": publisher[:100], "published_at": published})
    return items


def monthWindows(today: date) -> list[tuple[date, date]]:
    """오늘부터 6개월을 한 달 남짓씩 나눈 (after, before) 목록, 최근 것부터."""
    step = NEWS_MONTHS_DAYS // NEWS_WINDOWS
    return [(today - timedelta(days=step * (i + 1)), today - timedelta(days=step * i) + timedelta(days=1)) for i in range(NEWS_WINDOWS)]


async def fetchNews(query: str, after: date, before: date) -> list[dict]:
    params = {"q": f"{query} after:{after.isoformat()} before:{before.isoformat()}", "hl": "ko", "gl": "KR", "ceid": "KR:ko"}
    async with httpx.AsyncClient(timeout=NEWS_TIMEOUT_SEC, follow_redirects=True) as http:
        res = await http.get(NEWS_URL, params=params)
    res.raise_for_status()
    return parseRss(res.text)


def recentUnique(items: list[dict], seen: set[str]) -> list[dict]:
    """최근 6개월 안의 것만 최신 순으로. 날짜를 모르는 것·이미 고른 제목은 뺀다 (같은 기사가 여러 언론사로 나온 것)."""
    since = now() - timedelta(days=NEWS_MONTHS_DAYS)
    picked = []
    for item in sorted((i for i in items if i["published_at"] and i["published_at"] >= since),
                       key=lambda i: i["published_at"], reverse=True):
        key = re.sub(r"\W+", "", item["title"])
        if key not in seen:
            seen.add(key)
            picked.append(item)
    return picked


def aboutCompany(item: dict, terms: list[str]) -> bool:
    """회사 소식인가: 제목에 검색어나 회사 이름이 있어야 한다 (2026-11-16 사용자 결정).
    실측: 언론사 이름('네이버페이 머니스토리')만 검색어에 걸린 주식·건강 기사 7개가 섞였다."""
    title = item["title"].lower()
    return any(term.lower() in title for term in terms if term)


def pickSpread(groups: list[list[dict]], limit: int = NEWS_LIMIT) -> list[dict]:
    """달마다 limit/달 수 개씩 고르고, 모자라면 남은 것 중 최신 순으로 채운다."""
    seen: set[str] = set()
    groups = [recentUnique(g, seen) for g in groups]
    share = limit // max(len(groups), 1)
    picked = [item for g in groups for item in g[:share]]
    rest = sorted((item for g in groups for item in g[share:]), key=lambda i: i["published_at"], reverse=True)
    return sorted(picked + rest[:max(limit - len(picked), 0)], key=lambda i: i["published_at"], reverse=True)[:limit]


def storeNews(db: Session, items: list[dict]) -> list[CompanyNews]:
    """새로 찾은 소식으로 바꾼다: 이번에 찾지 못한 소식은 지우고, 없던 소식만 넣고, 6개월이 지난 것은 지운다.
    보이는 소식이 NEWS_LIMIT 개를 넘으면 오래된 것부터 지운다. 제거한 소식(hidden_at)은 다시 넣지 않으려고 남긴다."""
    if items:  # 하나도 못 찾았으면 있던 소식을 그대로 둔다
        visibleNews(db).filter(CompanyNews.url.notin_([i["url"] for i in items])).delete(synchronize_session=False)
    known = {u for (u,) in db.query(CompanyNews.url)}
    added = []
    for item in items:
        if item["url"] in known:
            continue
        news = CompanyNews(**item)
        db.add(news)
        added.append(news)
    db.flush()
    since = now() - timedelta(days=NEWS_MONTHS_DAYS)
    visibleNews(db).filter(CompanyNews.published_at < since).delete(synchronize_session=False)
    for old in listNews(db)[NEWS_LIMIT:]:
        db.delete(old)
    db.flush()
    return [n for n in added if n in db]


async def refreshNews(actorId: str | None = None) -> dict:
    """최근 소식 새로 찾기 (앱 시작 때, 관리자 [새로 찾기]). 실패하면 있던 소식을 그대로 둔다."""
    with SessionLocal() as db:
        profile = getProfile(db)
        query = profile.news_query.strip() or profile.name
        results = await asyncio.gather(*(fetchNews(query, after, before) for after, before in monthWindows(now().date())),
                                       return_exceptions=True)
        groups = [r for r in results if not isinstance(r, BaseException)]
        failed = [type(r).__name__ for r in results if isinstance(r, BaseException)]
        if failed:
            log.warning("company news refresh: %d of %d searches failed (%s)", len(failed), len(results), ", ".join(set(failed)))
        if not groups:
            return {"ok": False, "added": 0, "total": visibleNews(db).count()}
        terms = [query, profile.name]
        found = pickSpread([[i for i in g if aboutCompany(i, terms)] for g in groups])
        added = storeNews(db, found)
        profile.news_refreshed_at = now()
        db.add(AuditLog(actor_id=actorId, action="company.news_refresh", target="company_news",
                        detail={"query": query, "found": len(found), "added": len(added)}))
        db.commit()
        await embedNews(db, added)
        return {"ok": True, "added": len(added), "total": visibleNews(db).count()}


async def embedNews(db: Session, items: list[CompanyNews]) -> None:
    if not items or not rag.supported(db):
        return
    try:
        vectors = await rag.embed([promptTitle(n.title, db) for n in items], timeoutSec=60)
    except rag.EmbedUnavailable as exc:
        log.warning("company news embed failed: %s", exc)
        return
    for news, vector in zip(items, vectors, strict=True):
        db.execute(text("UPDATE company_news SET embedding = CAST(:v AS vector) WHERE id = :id"),
                   {"v": rag.toLiteral(vector), "id": news.id})
    db.commit()


# ---------- 질문·공고에 넣는 회사 정보 ----------

def promptTitle(title: str, db: Session, profile: CompanyProfile | None = None) -> str:
    """질문에 넣을 소식 제목: 검색어(모티프 회사 이름)를 우리 회사 이름으로 바꾼다 (사용자 결정 2026-11-16)."""
    profile = profile or getProfile(db)
    query = profile.news_query.strip()
    if not query or query == profile.name:
        return title
    return re.sub(re.escape(query), profile.name, title, flags=re.IGNORECASE)


def relatedNews(db: Session, vector: list[float] | None, count: int = CONTEXT_NEWS_COUNT) -> list[CompanyNews]:
    """찾을 글과 가장 비슷한 소식 count 개 (RAG). 벡터가 없거나 SQLite 면 최신 순."""
    if vector is not None and rag.supported(db):
        rows = db.execute(text(
            "SELECT id FROM company_news WHERE hidden_at IS NULL AND embedding IS NOT NULL "
            "ORDER BY embedding <=> CAST(:v AS vector) LIMIT :n"), {"v": rag.toLiteral(vector), "n": count}).all()
        if rows:
            return [db.get(CompanyNews, r.id) for r in rows]
    return listNews(db)[:count]


def profileText(profile: CompanyProfile, withJobs: bool = False) -> str:
    parts = [f"회사 이름: {profile.name}", f"기본 정보: {profile.basics[:CONTEXT_TEXT_CHARS]}",
             f"회사 소개: {profile.intro[:CONTEXT_TEXT_CHARS]}"]
    if withJobs:
        parts.append(f"직무 소개: {profile.jobs_intro[:CONTEXT_TEXT_CHARS]}")
    parts.append(f"AI/AX 가 하는 일: {profile.ai_ax_role[:CONTEXT_TEXT_CHARS]}")
    return "\n".join(p for p in parts if not p.endswith(": "))


def questionContext(db: Session, vector: list[float] | None) -> str:
    """회사 질문에 넣는 회사 정보 + 관련 최근 소식."""
    profile = getProfile(db)
    news = [f"- {promptTitle(n.title, db, profile)}" for n in relatedNews(db, vector)]
    return profileText(profile) + ("\n최근 소식:\n" + "\n".join(news) if news else "")


def postingContext(db: Session) -> str:
    """AI 공고 초안에 넣는 회사 정보 (직무 소개 포함, 소식은 넣지 않는다)."""
    return profileText(getProfile(db), withJobs=True)
