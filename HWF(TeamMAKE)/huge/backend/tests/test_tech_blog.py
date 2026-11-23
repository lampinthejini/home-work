"""회사 기술 블로그 최신 글과 회사 정보 새 칸 (2026-11-17 사용자 결정, CONFLICTS C-22)."""

import asyncio
from datetime import timedelta

from app.models import AuditLog, CompanyTechPost
from app.services import company, slot_material, tech_blog
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


def test_companyPiecesHaveTechPostAsCompanyAndNoStack(sessionFactory):
    """회사 자리 자료 칸 (C-31): 기술 글은 우리 회사 이름으로, 기술 스택은 회사 자리에 넣지 않는다 (직무 자리 칸)."""
    with sessionFactory() as db:
        db.add(CompanyTechPost(title="네이버 GPU 노드를 VM으로 격리하기", url="https://d2.naver.com/helloworld/9",
                               summary="NAVER 의 Kubernetes GPU 노드", published_at=now()))
        db.commit()
        pieces = slot_material.companyPieces(db)
    assert "AIIT GPU 노드를 VM으로 격리하기: AIIT 의 Kubernetes GPU 노드" in [p.text for p in pieces if p.field == "post"]
    assert not any("네이버" in p.text or "NAVER" in p.text for p in pieces)
    assert {"intro", "mission", "post"} <= {p.field for p in pieces} and not {"tech_stack", "talent"} & {p.field for p in pieces}


def test_companyQuestionsDoNotGetTalentLines(sessionFactory):
    """2026-11-22 사용자: 회사 질문에서는 인재상을 묻지 말자 (인성 질문이 묻는다). '일하는 방식' 은 회사 소개 칸에 남긴다."""
    with sessionFactory() as db:
        pieces = slot_material.companyPieces(db)
        context = company.questionContext(db, None)
    talent = ("사용자의 문제에서 시작하는 사람", "측정하고 판단하는 사람", "모르는 것을 모른다고", "함께 더 나아지는 사람")
    assert not any(t in p.text for p in pieces for t in talent) and not any(t in context for t in talent)
    workWay = [p for p in pieces if p.label == "일하는 방식"]
    assert workWay and all(p.field == "intro" for p in workWay) and "일하는 방식:" in context


def test_eachCompanyQuestionGetsDifferentPost(sessionFactory):
    """질문마다 다른 기술 글 (2026-11-17 사용자 요청: 한 글로 쏠림) — 쓴 항목은 같은 면접에서 다시 고르지 않는다 (C-31)."""
    with sessionFactory() as db:
        for i in range(3):
            db.add(CompanyTechPost(title=f"기술 글 {i}", url=f"https://d2.naver.com/helloworld/{i}", summary="", published_at=now()))
        db.commit()
        pieces = [p for p in slot_material.companyPieces(db) if p.field == "post"]
    picker = slot_material.MaterialPicker(pieces, [])
    first = picker.pick("company", ["post"], 0)
    picker.markUsed(first)
    second = picker.pick("company", ["post"], 0)
    assert first.text != second.text


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
