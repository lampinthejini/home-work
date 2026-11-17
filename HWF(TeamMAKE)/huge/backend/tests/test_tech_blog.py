"""회사 기술 블로그 최신 글과 회사 정보 새 칸 (2026-11-17 사용자 결정, CONFLICTS C-22)."""

import asyncio
import re
from datetime import timedelta

from app.models import AuditLog, CompanyTechPost
from app.services import company, question_compose, tech_blog
from app.timeutil import now
from tests.test_question_rag import composed, makeApplication, world  # noqa: F401 — world 는 pytest fixture

BOILER = "네이버 사내 기술 교류 행사인 NAVER Engineering Day 10th 에서 발표되었던 세션을 공개합니다. &#8203; 발표 내용 "
ATOM = f"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>D2 Blog</title>
  <entry>
    <title>네이버 전 지면의 행동을 학습하는 추천 모델</title>
    <link rel="alternate" href="https://d2.naver.com/helloworld/1" />
    <category term="hello world" />
    <updated>2026-11-16T09:04:47Z</updated>
    <content type="html">&lt;p&gt;{BOILER}NAVER 검색·피드 데이터를 &lt;b&gt;연결&lt;/b&gt;하는 추천&lt;/p&gt;</content>
  </entry>
  <entry>
    <title>FE News 26년 11월 소식</title>
    <link rel="alternate" href="https://d2.naver.com/news/2" />
    <category term="news" />
    <updated>2026-11-04T00:00:00Z</updated>
    <content type="html">외부 소식 모음</content>
  </entry>
  <entry>
    <title>링크가 이상한 글</title>
    <link rel="alternate" href="javascript:alert(1)" />
    <category term="hello world" />
    <updated>2026-11-03T00:00:00Z</updated>
  </entry>
</feed>"""


def test_parseFeedKeepsTechPostsAndCleansSummary():
    items = tech_blog.parseFeed(ATOM)
    assert [i["url"] for i in items] == ["https://d2.naver.com/helloworld/1"]  # news 분류·https 아닌 링크는 뺀다
    assert items[0]["summary"] == "NAVER 검색·피드 데이터를 연결 하는 추천"  # 태그·머리말을 뺀다
    assert items[0]["published_at"].year == 2026


def test_parseRss():
    rss = ("<rss><channel><item><title>글</title><link>https://blog.example.com/1</link>"
           "<description>&lt;p&gt;본문&lt;/p&gt;</description><pubDate>Mon, 16 Nov 2026 01:00:00 GMT</pubDate></item></channel></rss>")
    assert [(i["title"], i["summary"]) for i in tech_blog.parseFeed(rss)] == [("글", "본문")]


def test_namesBecomeCompanyName(sessionFactory):
    with sessionFactory() as db:
        profile = company.getProfile(db)
        assert profile.tech_source_name == "네이버, NAVER" and profile.tech_feed_url == "https://d2.naver.com/d2.atom"
        assert tech_blog.asCompany("네이버의 NAVER Engineering Day, naver 클라우드", profile) == "AIIT의 AIIT Engineering Day, AIIT 클라우드"
        profile.tech_source_name = ""
        assert tech_blog.asCompany("네이버", profile) == "네이버"


def test_refreshHideAndLimit(adminClient, sessionFactory, monkeypatch):
    monkeypatch.setattr(tech_blog, "SessionLocal", sessionFactory)

    async def fakeFetch(url):
        assert url == "https://d2.naver.com/d2.atom"
        return tech_blog.parseFeed(ATOM)
    monkeypatch.setattr(tech_blog, "fetchFeed", fakeFetch)
    body = adminClient.post("/admin/company/tech/refresh").json()
    assert body["refresh"] == {"ok": True, "added": 1, "total": 1}
    post = body["tech_posts"][0]
    assert post["title"] == "AIIT 전 지면의 행동을 학습하는 추천 모델" and post["url"] == "https://d2.naver.com/helloworld/1"
    assert body["profile"]["tech_refreshed_at"] is not None
    assert adminClient.post(f"/admin/company/tech/{post['id']}/hide").json()["tech_posts"] == []
    assert adminClient.post("/admin/company/tech/refresh").json()["refresh"]["added"] == 0  # 제거한 글은 다시 안 들어온다
    assert adminClient.post(f"/admin/company/tech/{post['id']}/hide").status_code == 404

    with sessionFactory() as db:
        db.add_all([CompanyTechPost(title=f"글 {i}", url=f"https://b.example.com/{i}", published_at=now() - timedelta(hours=i))
                    for i in range(tech_blog.POST_LIMIT + 5)])
        db.flush()
        tech_blog.storePosts(db, [])
        db.commit()
        assert tech_blog.visiblePosts(db).count() == tech_blog.POST_LIMIT
        assert tech_blog.listPosts(db)[0].title == "글 0"
        assert db.query(AuditLog).filter_by(action="company.tech_hide").count() == 1


def test_refreshFailureKeepsPosts(sessionFactory, monkeypatch):
    monkeypatch.setattr(tech_blog, "SessionLocal", sessionFactory)
    with sessionFactory() as db:
        db.add(CompanyTechPost(title="있던 글", url="https://b.example.com/x", published_at=now()))
        db.commit()
    result = asyncio.run(tech_blog.refreshPosts())  # conftest 가 인터넷을 막아 둠
    assert result == {"ok": False, "added": 0, "total": 1}


def test_adminEditsNewFieldsAndFeedMustBeHttps(adminClient):
    body = adminClient.get("/admin/company").json()
    profile = body["profile"]
    assert "측정하고 판단하는 사람" in profile["talent"] and "vLLM" in profile["tech_stack"] and "미션:" in profile["mission"]
    assert body["tech_posts"] == [] and body["tech_post_limit"] == tech_blog.POST_LIMIT
    res = adminClient.put("/admin/company", json={"talent": "새 인재상", "tech_feed_url": ""})
    assert res.json()["profile"]["talent"] == "새 인재상" and res.json()["profile"]["tech_feed_url"] == ""
    assert adminClient.put("/admin/company", json={"tech_feed_url": "http://example.com/feed"}).status_code == 422
    assert adminClient.put("/admin/company", json={"tech_feed_url": "file:///etc/passwd"}).status_code == 422


def test_companyQuestionGetsTechPostsAndNewFields(sessionFactory, world):  # noqa: F811
    fake = world()
    with sessionFactory() as db:
        db.add(CompanyTechPost(title="네이버 GPU 노드를 VM으로 격리하기", url="https://d2.naver.com/helloworld/9",
                               summary="NAVER 의 Kubernetes GPU 노드", published_at=now()))
        db.commit()
    appId = makeApplication(sessionFactory)
    asyncio.run(question_compose.compose(appId))
    assert len(composed(sessionFactory, appId)) == 10
    prompt = next(p for p in fake.prompts if p.startswith("[만들 질문] 회사"))
    assert "회사가 요즘 다루는 기술 (지원자는 모를 수 있음):\n- AIIT GPU 노드를 VM으로 격리하기: AIIT 의 Kubernetes GPU 노드" in prompt
    assert "네이버" not in prompt and "NAVER" not in prompt
    assert "경영 이념: 미션:" in prompt and "인재상과 일하는 방식: 인재상" in prompt
    assert "사내 기술 스택" not in prompt  # 기술 스택은 공고 초안에만


def test_eachCompanyQuestionGetsDifferentPost(sessionFactory, world):  # noqa: F811
    """질문마다 다른 기술 글 (2026-11-17 사용자 요청: 한 글로 쏠림)."""
    fake = world()
    with sessionFactory() as db:
        for i in range(3):
            db.add(CompanyTechPost(title=f"기술 글 {i}", url=f"https://d2.naver.com/helloworld/{i}", summary="", published_at=now()))
        db.commit()
    appId = makeApplication(sessionFactory)
    asyncio.run(question_compose.compose(appId))
    prompts = [p for p in fake.prompts if p.startswith("[만들 질문] 회사")]
    picked = [re.findall(r"- (기술 글 \d)", p.split("(지원자는 모를 수 있음):")[1].split("</회사>")[0]) for p in prompts]
    assert len(prompts) >= 2 and all(len(x) == tech_blog.CONTEXT_POST_COUNT for x in picked)
    assert picked[0] != picked[1]


def test_relatedPostsSkipsUsedThenReuses(sessionFactory):
    with sessionFactory() as db:
        for i in range(2):
            db.add(CompanyTechPost(title=f"글 {i}", url=f"https://d2.naver.com/helloworld/{i}", summary="", published_at=now()))
        db.commit()
        used: set[int] = set()
        first = company.pickPosts(db, None, used)
        second = company.pickPosts(db, None, used)
        assert first != second and len(used) == 2
        third = company.pickPosts(db, None, used)
        assert third  # 다 쓰면 처음부터 다시 쓴다


def test_postingContextHasTalentAndStack(sessionFactory):
    with sessionFactory() as db:
        text = company.postingContext(db)
    assert "직무 소개:" in text and "인재상과 일하는 방식:" in text and "사내 기술 스택:" in text
    assert "기술 블로그" not in text
