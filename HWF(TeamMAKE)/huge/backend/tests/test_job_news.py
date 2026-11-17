"""직무 관련 최근 소식(임시 자료)과 회사 소식 거르기 (2026-11-16 사용자 결정, CONFLICTS C-20).

- 질문 만들기 전 30초 안에 끝난 검색만 쓰고, 직무와 상관없는 제목은 빼고, 최대 10개. DB 에 남기지 않는다.
- 회사 최근 소식은 제목에 검색어나 회사 이름이 없으면 뺀다.
"""

import asyncio
from datetime import timedelta

from app.services import job_news, question_compose, rag
from app.timeutil import now
from tests.test_question_rag import composed, fakeVector, makeApplication, world  # noqa: F401 — world 는 pytest fixture


def item(title, days=1):
    return {"title": title, "url": f"https://n.example.com/{title}", "publisher": "", "published_at": now() - timedelta(days=days)}


def test_pickRelevantDropsUnrelatedOldAndDuplicates():
    pattern = job_news.JOB_NEWS_RELEVANT["AI_AX"]
    groups = [[item("생성형 AI 플랫폼 가동"), item("오늘의 날씨"), item("생성형 AI 플랫폼 가동"), item("LLM 보안 사고", days=40)],
              [item("AI 에이전트 위험 경고"), item("RAG 검색 정확도 높이는 법"), item("SAIL 요트 대회")]]
    assert job_news.pickRelevant(groups, pattern) == ["생성형 AI 플랫폼 가동", "AI 에이전트 위험 경고", "RAG 검색 정확도 높이는 법"]
    many = [[item(f"AI 소식 {g}-{i}") for i in range(10)] for g in range(5)]
    picked = job_news.pickRelevant(many, pattern)
    assert len(picked) == job_news.JOB_NEWS_LIMIT and {p.split(" ")[2][0] for p in picked} == {"0", "1", "2", "3", "4"}  # 검색어마다 고루


def test_collectUsesOnlySearchesFinishedInTime(monkeypatch):
    async def fetch(query):
        if query == "LLM":
            await asyncio.sleep(5)  # 시간 안에 못 끝남 → 버린다
            return [item("LLM 늦은 소식")]
        if query == "RAG 검색":
            raise job_news.httpx.ConnectError("down")
        return [item(f"{query} 소식")]

    async def embed(texts, timeoutSec=10):
        return [fakeVector(t) for t in texts]
    monkeypatch.setattr(job_news, "fetchQuery", fetch)
    monkeypatch.setattr(rag, "embed", embed)
    news = asyncio.run(job_news.collect("AI_AX", timeoutSec=0.5))
    assert sorted(n.title for n in news) == ["AI 에이전트 소식", "AI 전환 AX 소식", "생성형 AI 소식"]
    assert not any(n.vector for n in news)  # 시간을 다 써서 임베딩도 건너뛰고 바로 질문 만들기로 간다
    assert asyncio.run(job_news.collect("BACKEND")) == []  # 검색어가 없는 직무


def test_collectWithoutEmbedStillReturnsTitles(monkeypatch):
    async def fetch(query):
        return [item(f"{query} 소식")]

    async def down(texts, timeoutSec=10):
        raise rag.EmbedUnavailable("down")
    monkeypatch.setattr(job_news, "fetchQuery", fetch)
    monkeypatch.setattr(rag, "embed", down)
    news = asyncio.run(job_news.collect("AI_AX"))
    assert len(news) == 5 and not any(n.vector for n in news)
    assert job_news.forSlot(news, None, 0) == [news[0].title, news[1].title]
    assert job_news.forSlot(news, None, 1) == [news[2].title, news[3].title]  # 자리마다 돌아가며


def test_forSlotPicksClosestToSlotQuery():
    news = [job_news.JobNews("모델 소식", fakeVector("모델")), job_news.JobNews("검색 소식", fakeVector("검색")),
            job_news.JobNews("데이터 소식", fakeVector("데이터"))]
    assert job_news.forSlot(news, fakeVector("검색 품질"), 0, count=1) == ["검색 소식"]
    assert job_news.forSlot([], fakeVector("검색"), 0) == []


def test_jobNewsGoIntoJobPromptsOnlyAndAreCleared(sessionFactory, world, monkeypatch):  # noqa: F811
    fake = world()
    collected = []

    async def collect(jobCode, timeoutSec=30):
        assert jobCode == "AI_AX" and 0 < timeoutSec <= job_news.JOB_NEWS_TIMEOUT_SEC
        news = [job_news.JobNews("현대제철, 생성형 AI 플랫폼 가동", fakeVector("모델 데이터"))]
        collected.append(news)
        return news
    monkeypatch.setattr(job_news, "collect", collect)
    appId = makeApplication(sessionFactory)
    asyncio.run(question_compose.compose(appId))
    assert len(composed(sessionFactory, appId)) == 10
    jobPrompts = [p for p in fake.prompts if p.startswith("[만들 질문] 직무")]
    assert jobPrompts and all("<소식>\n- 현대제철, 생성형 AI 플랫폼 가동\n</소식>" in p for p in jobPrompts)
    assert all("소식에 나온 회사 이름은 질문에 넣지 않는다" in p for p in jobPrompts)
    assert not any("<소식>" in p for p in fake.prompts if not p.startswith("[만들 질문] 직무"))
    assert collected[0] == []  # 다 만들면 메모리에서 지운다


def test_jobNewsSkippedWhenRagIsOff(sessionFactory, world, monkeypatch):  # noqa: F811
    world(embedDown=True)
    called = []

    async def collect(jobCode, timeoutSec=30):
        called.append(jobCode)
        return []
    monkeypatch.setattr(job_news, "collect", collect)
    appId = makeApplication(sessionFactory)
    asyncio.run(question_compose.compose(appId))
    assert called == []  # 질문을 만들지 않을 때는 찾지도 않는다



def test_parseRssSplitsPublisherAndSkipsBadLinks():
    xml = ("<?xml version='1.0' encoding='UTF-8'?><rss version='2.0'><channel>"
           "<item><title>AI 에이전트 공개 - 전자신문</title><link>https://news.example.com/a</link>"
           "<pubDate>Mon, 16 Nov 2026 01:00:00 GMT</pubDate><source url='https://etnews.com'>전자신문</source></item>"
           "<item><title>링크가 이상함</title><link>javascript:alert(1)</link></item>"
           "<item><title>날짜 없음</title><link>https://news.example.com/b</link></item>"
           "</channel></rss>")
    items = job_news.parseRss(xml)
    assert [(i["title"], i["publisher"]) for i in items] == [("AI 에이전트 공개", "전자신문"), ("날짜 없음", "")]
    assert items[0]["published_at"].year == 2026 and items[1]["published_at"] is None
