"""직무 관련 최근 소식 — 면접 질문 만들기 전에 잠깐 찾아 쓰는 임시 자료 (2026-11-16 사용자 결정, CONFLICTS C-20).

- 질문을 만들기 전에 직무 검색어 여러 개로 최근 JOB_NEWS_DAYS 일 뉴스를 동시에 찾는다 (Google 뉴스 RSS).
- 전체 JOB_NEWS_TIMEOUT_SEC 초 안에 끝난 검색 결과만 쓴다 (늦은 검색은 취소). 직무와 상관없는 제목은 바로 뺀다.
- 최대 JOB_NEWS_LIMIT 개를 고르고 제목을 임베딩해, 직무 질문 자리마다 찾을 글과 가까운 PER_SLOT 개를 프롬프트에 넣는다.
- DB 에 저장하지 않는다. 질문 만들기가 끝나면 메모리에서 지운다 (question_compose.compose).
실측(2026-11-16, api 컨테이너): 검색어 5개 동시 0.76초, 검색어마다 23~100개.
"""

import asyncio
import logging
import re
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import timedelta
from email.utils import parsedate_to_datetime

import httpx

from ..timeutil import now
from . import rag

log = logging.getLogger("huge.job_news")

JOB_NEWS_LIMIT = 10
JOB_NEWS_TIMEOUT_SEC = 30
JOB_NEWS_DAYS = 30
PER_SLOT = 2
EMBED_TIMEOUT_SEC = 10
NEWS_TIMEOUT_SEC = 15
NEWS_URL = "https://news.google.com/rss/search"

# 직무별 검색어와 '상관있는 제목' 규칙. 운영 직무는 AI/AX 하나 (PRD 2-4)
JOB_NEWS_QUERIES = {"AI_AX": ("생성형 AI", "AI 에이전트", "LLM", "AI 전환 AX", "RAG 검색")}
JOB_NEWS_RELEVANT = {
    "AI_AX": re.compile(r"(?<![A-Za-z])(AI|LLM|RAG|AX|GPT|MLOps)(?![a-z])|인공지능|에이전트|생성형|머신러닝|딥러닝|언어\s*모델|파운데이션"),
}


@dataclass
class JobNews:
    title: str
    vector: list[float] | None = None


def parseRss(xmlText: str) -> list[dict]:
    """Google 뉴스 RSS → [{title, url, publisher, published_at}]. 제목 끝의 ' - 언론사'는 따로 뗀다.
    (회사 최근 소식이 쓰던 것을 2026-11-17 회사 소식을 지우며 여기로 옮김, CONFLICTS C-21)"""
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


async def fetchQuery(query: str) -> list[dict]:
    params = {"q": f"{query} when:{JOB_NEWS_DAYS}d", "hl": "ko", "gl": "KR", "ceid": "KR:ko"}
    async with httpx.AsyncClient(timeout=NEWS_TIMEOUT_SEC, follow_redirects=True) as http:
        res = await http.get(NEWS_URL, params=params)
    res.raise_for_status()
    return parseRss(res.text)


def pickRelevant(groups: list[list[dict]], pattern: re.Pattern, limit: int = JOB_NEWS_LIMIT) -> list[str]:
    """직무와 상관있는 최근 제목만, 검색어마다 돌아가며 최신 순으로 limit 개 (한 검색어로 쏠리지 않게)."""
    since = now() - timedelta(days=JOB_NEWS_DAYS)
    seen: set[str] = set()
    queues = []
    for items in groups:
        fresh = sorted((i for i in items if i["published_at"] and i["published_at"] >= since and pattern.search(i["title"])),
                       key=lambda i: i["published_at"], reverse=True)
        queues.append([i["title"] for i in fresh])
    picked: list[str] = []
    while len(picked) < limit and any(queues):
        for queue in queues:
            while queue:
                title = queue.pop(0)
                key = re.sub(r"\W+", "", title)
                if key not in seen:
                    seen.add(key)
                    picked.append(title)
                    break
            if len(picked) >= limit:
                break
    return picked


async def collect(jobCode: str, timeoutSec: float = JOB_NEWS_TIMEOUT_SEC) -> list[JobNews]:
    """검색 → (시간 안에 끝난 것만) → 상관없는 것 빼기 → 임베딩. 실패하거나 없으면 빈 목록 (질문 만들기는 그대로 간다)."""
    queries = JOB_NEWS_QUERIES.get(jobCode)
    if not queries or timeoutSec <= 0:
        return []
    started = time.monotonic()
    tasks = [asyncio.create_task(fetchQuery(q)) for q in queries]
    done, pending = await asyncio.wait(tasks, timeout=timeoutSec)
    for task in pending:
        task.cancel()  # 시간 안에 못 끝난 검색은 버리고 찾은 결과만 쓴다
    groups, failed = [], 0
    for task in done:
        if task.exception() is None:
            groups.append(task.result())
        else:
            failed += 1
            if not isinstance(task.exception(), (httpx.HTTPError, ET.ParseError)):
                log.warning("job news search error: %s", type(task.exception()).__name__)
    titles = pickRelevant(groups, JOB_NEWS_RELEVANT[jobCode])
    news = [JobNews(t) for t in titles]
    left = timeoutSec - (time.monotonic() - started)
    if news and left > 1:
        try:
            for item, vector in zip(news, await rag.embed(titles, timeoutSec=min(EMBED_TIMEOUT_SEC, left)), strict=True):
                item.vector = vector
        except rag.EmbedUnavailable as exc:
            log.info("job news embed skipped: %s", exc)
    log.info("job news %s: %d searches done, %d timed out, %d failed, %d relevant kept, %.1fs",
             jobCode, len(done), len(pending), failed, len(news), time.monotonic() - started)
    return news


def forSlot(news: list[JobNews], vector: list[float] | None, slotIndex: int, count: int = PER_SLOT) -> list[str]:
    """이 자리의 찾을 글과 가까운 소식 count 개. 벡터가 없으면 자리마다 돌아가며 고른다."""
    if not news:
        return []
    if vector is not None and all(n.vector for n in news):
        ranked = sorted(news, key=lambda n: rag.cosine(vector, n.vector), reverse=True)
        return [n.title for n in ranked[:count]]
    start = (slotIndex * count) % len(news)
    return [news[(start + i) % len(news)].title for i in range(min(count, len(news)))]
