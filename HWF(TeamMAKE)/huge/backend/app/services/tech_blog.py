"""회사 기술 블로그 최신 글 (2026-11-17 사용자 결정, CONFLICTS C-22).

- 사용자 결정: 모티프 회사(네이버)의 기술 블로그 D2(https://d2.naver.com)의 최신 글을 우리 회사의 최신 기술로 쓴다.
  회사 정보의 tech_feed_url(Atom/RSS) 을 앱을 켤 때와 관리자 [새로 가져오기] 때 읽는다.
- 글 제목과 본문 앞부분(태그를 뺀 SUMMARY_CHARS 자)만 둔다. 화면과 질문에 쓸 때 tech_source_name 에 적은 말
  (예: '네이버, NAVER')을 회사 이름으로 바꾼다. 원래 글은 바꾸지 않고 링크는 원문으로 간다.
- 기술 글만 쓴다: D2 의 'news' 분류(외부 소식 모음, 예: FE News)는 뺀다.
- 보이는 글은 POST_LIMIT 개까지(최신 순). 관리자가 [제거]한 글은 hidden_at 을 남겨 다시 들어오지 않는다.
- 회사 질문 RAG: 찾을 글과 가장 비슷한 CONTEXT_POST_COUNT 개를 넣는다 (pgvector, SQLite 에서는 최신 순).
실패해도 면접·게시에는 영향이 없다 (있던 글을 그대로 두고 기록만 남긴다).
"""

import html
import logging
import re
import xml.etree.ElementTree as ET
from datetime import datetime
from email.utils import parsedate_to_datetime

import httpx
from sqlalchemy import text
from sqlalchemy.orm import Session

from ..db import SessionLocal
from ..models import AuditLog, CompanyProfile, CompanyTechPost
from ..timeutil import now
from . import company, rag

log = logging.getLogger("huge.tech_blog")

POST_LIMIT = 20
CONTEXT_POST_COUNT = 1  # 질문 하나에 넣는 글 수. 한 면접 안에서는 질문마다 다른 글 (2026-11-17 사용자 요청: 한 글로 쏠림)
SUMMARY_CHARS = 400  # 저장하는 본문 앞부분
PROMPT_SUMMARY_CHARS = 120  # 질문 프롬프트에 넣는 본문 앞부분
FETCH_TIMEOUT_SEC = 20
FEED_MAX_BYTES = 5_000_000
SKIP_CATEGORIES = {"news"}
ATOM = "{http://www.w3.org/2005/Atom}"
# D2 발표 공개 글의 머리말. 모든 글에 같아 요약에서 뺀다
BOILERPLATE = re.compile(r"^.{0,80}?발표되었던 세션을 공개합니다\.?\s*(발표 내용\s*)?")


def plainText(markup: str) -> str:
    body = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", markup or "", flags=re.S | re.I)
    body = html.unescape(re.sub(r"<[^>]+>", " ", body))
    body = re.sub(r"[​\s]+", " ", body).strip()
    return BOILERPLATE.sub("", body).strip()


def parseDate(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        pass
    try:
        return parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None


def parseFeed(xmlText: str) -> list[dict]:
    """Atom 또는 RSS → [{title, url, summary, published_at}]. https 링크만, 'news' 분류는 뺀다."""
    root = ET.fromstring(xmlText)
    items = []
    for entry in root.iter(f"{ATOM}entry"):
        categories = {c.get("term", "").strip().lower() for c in entry.findall(f"{ATOM}category")}
        link = next((a.get("href", "") for a in entry.findall(f"{ATOM}link") if a.get("rel", "alternate") == "alternate"), "")
        content = entry.findtext(f"{ATOM}content") or entry.findtext(f"{ATOM}summary") or ""
        items.append({"title": (entry.findtext(f"{ATOM}title") or "").strip(), "url": link.strip(), "categories": categories,
                      "summary": plainText(content), "published_at": parseDate(entry.findtext(f"{ATOM}published")
                                                                               or entry.findtext(f"{ATOM}updated"))})
    for item in root.iter("item"):
        items.append({"title": (item.findtext("title") or "").strip(), "url": (item.findtext("link") or "").strip(),
                      "categories": {(c.text or "").strip().lower() for c in item.findall("category")},
                      "summary": plainText(item.findtext("description") or ""), "published_at": parseDate(item.findtext("pubDate"))})
    picked = []
    for item in items:
        if not item["title"] or not item["url"].startswith("https://") or item["categories"] & SKIP_CATEGORIES:
            continue
        picked.append({"title": item["title"][:300], "url": item["url"][:1000], "summary": item["summary"][:SUMMARY_CHARS],
                       "published_at": item["published_at"]})
    return picked


async def fetchFeed(url: str) -> list[dict]:
    async with httpx.AsyncClient(timeout=FETCH_TIMEOUT_SEC, follow_redirects=True) as http:
        res = await http.get(url, headers={"user-agent": "huge-interview/1.0"})
    res.raise_for_status()
    if len(res.content) > FEED_MAX_BYTES:
        raise ValueError("feed too large")
    return parseFeed(res.text)


# ---------- 저장 ----------

def visiblePosts(db: Session):
    return db.query(CompanyTechPost).filter(CompanyTechPost.hidden_at.is_(None))


def listPosts(db: Session) -> list[CompanyTechPost]:
    return visiblePosts(db).order_by(CompanyTechPost.published_at.desc().nullslast(), CompanyTechPost.id.desc()).all()


def storePosts(db: Session, items: list[dict]) -> list[CompanyTechPost]:
    """없던 글만 넣고, 보이는 글이 POST_LIMIT 개를 넘으면 오래된 것부터 지운다. 제거한 글은 다시 넣지 않으려고 남긴다."""
    known = {u for (u,) in db.query(CompanyTechPost.url)}
    added = []
    for item in items:
        if item["url"] in known:
            continue
        known.add(item["url"])
        post = CompanyTechPost(**item)
        db.add(post)
        added.append(post)
    db.flush()
    for old in listPosts(db)[POST_LIMIT:]:
        db.delete(old)
    db.flush()
    return [p for p in added if p in db]


def hidePost(db: Session, actorId: str, postId: int) -> bool:
    post = db.get(CompanyTechPost, postId)
    if post is None or post.hidden_at is not None:
        return False
    post.hidden_at = now()
    db.add(AuditLog(actor_id=actorId, action="company.tech_hide", target=str(postId), detail={}))
    db.commit()
    return True


async def refreshPosts(actorId: str | None = None) -> dict:
    """기술 블로그 새로 가져오기 (앱 시작 때, 관리자 [새로 가져오기]). 실패하면 있던 글을 그대로 둔다."""
    with SessionLocal() as db:
        profile = company.getProfile(db)
        url = (profile.tech_feed_url or "").strip()
        if not url:
            return {"ok": False, "added": 0, "total": visiblePosts(db).count()}
        try:
            items = await fetchFeed(url)
        except (httpx.HTTPError, ET.ParseError, ValueError) as exc:
            log.warning("tech blog refresh failed: %s", type(exc).__name__)
            return {"ok": False, "added": 0, "total": visiblePosts(db).count()}
        added = storePosts(db, items)
        profile.tech_refreshed_at = now()
        db.add(AuditLog(actor_id=actorId, action="company.tech_refresh", target="company_tech_posts",
                        detail={"found": len(items), "added": len(added)}))
        db.commit()
        await embedMissing(db)
        return {"ok": True, "added": len(added), "total": visiblePosts(db).count()}


async def embedMissing(db: Session, timeoutSec: float = 60) -> int:
    if not rag.supported(db):
        return 0
    ids = [r.id for r in db.execute(text("SELECT id FROM company_tech_posts WHERE embedding IS NULL AND hidden_at IS NULL")).all()]
    posts = [db.get(CompanyTechPost, i) for i in ids]
    if not posts:
        return 0
    profile = company.getProfile(db)
    try:
        vectors = await rag.embed([promptLine(p, profile) for p in posts], timeoutSec=timeoutSec)
    except rag.EmbedUnavailable as exc:
        log.warning("tech blog embed failed: %s", exc)
        return 0
    for post, vector in zip(posts, vectors, strict=True):
        db.execute(text("UPDATE company_tech_posts SET embedding = CAST(:v AS vector) WHERE id = :id"),
                   {"v": rag.toLiteral(vector), "id": post.id})
    db.commit()
    return len(posts)


# ---------- 화면·질문에 쓰기 ----------

def asCompany(value: str, profile: CompanyProfile) -> str:
    """모티프 회사 이름(tech_source_name, 쉼표로 여러 개)을 우리 회사 이름으로 바꾼다."""
    for name in sorted((n.strip() for n in (profile.tech_source_name or "").split(",")), key=len, reverse=True):
        if name and name != profile.name:
            value = re.sub(re.escape(name), profile.name, value, flags=re.IGNORECASE)
    return value


def postView(p: CompanyTechPost, profile: CompanyProfile) -> dict:
    return {"id": p.id, "title": asCompany(p.title, profile), "url": p.url, "summary": asCompany(p.summary, profile),
            "published_at": p.published_at.isoformat() if p.published_at else None}


def promptLine(p: CompanyTechPost, profile: CompanyProfile) -> str:
    summary = asCompany(p.summary[:PROMPT_SUMMARY_CHARS], profile)
    return f"- {asCompany(p.title, profile)}" + (f": {summary}" if summary else "")


def relatedPosts(db: Session, vector: list[float] | None, count: int, excludeIds=frozenset()) -> list[CompanyTechPost]:
    """찾을 글과 가장 비슷한 글 count 개 (RAG). excludeIds 는 뺀다. 벡터가 없거나 SQLite 면 최신 순."""
    if vector is not None and rag.supported(db):
        rows = db.execute(text(
            "SELECT id FROM company_tech_posts WHERE hidden_at IS NULL AND embedding IS NOT NULL AND id <> ALL(:ex) "
            "ORDER BY embedding <=> CAST(:v AS vector) LIMIT :n"),
            {"v": rag.toLiteral(vector), "n": count, "ex": list(excludeIds)}).all()
        if rows:
            return [db.get(CompanyTechPost, r.id) for r in rows]
    return [p for p in listPosts(db) if p.id not in excludeIds][:count]
