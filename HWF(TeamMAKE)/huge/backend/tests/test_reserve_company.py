"""예비 질문과 회사 정보 (2026-11-16 사용자 결정, CONFLICTS C-20).

- 엑셀 질문 DB 를 지우고 종류마다 기본 질문 10개. AI 질문은 승인 없이 예비 질문에 (0.8 이상 비슷하면 빼고, 종류마다 100개까지)
- 관리자 예비 질문: 질문분야 · 질문(직접 고침) · 직무 · 해당 직무만 · 삭제(여러 개), 하루 동안 NEW
- 회사 정보와 최근 소식(앱 시작 때 새로 찾기, 제목·링크·제거), 회사 질문 RAG
"""

import asyncio
from datetime import datetime, timedelta

from app.domain import question_text
from app.models import AuditLog, CompanyNews, InterviewQuestion, JobPosting, Question
from app.services import company, question_bank, question_compose, rag
from app.timeutil import now
from tests.test_question_rag import composed, makeApplication, world  # noqa: F401 — world 는 pytest fixture

# ---------- 기본 예비 질문 ----------

def test_seedQuestionsTenPerKindAndPassTextCheck():
    for kind in question_bank.RESERVE_KINDS:
        texts = question_bank.RESERVE_QUESTIONS[kind]
        assert len(texts) == 10, kind
        assert len({question_bank.normalizeText(t) for t in texts}) == 10, kind
        for text in texts:
            assert question_text.textProblem(text) is None, text
            assert question_bank.excludedReason(text) is None, text


def test_seedOnlyWhenEmptyAndJobQuestionsAreJobOnly(sessionFactory):
    with sessionFactory() as db:
        assert question_bank.seedReserve(db) == 40
        assert question_bank.seedReserve(db) == 0  # 지운 기본 질문이 시작할 때마다 되살아나지 않게
        jobCodes = {q.kind: q.job_code for q in db.query(Question)}
    assert jobCodes == {"personality": None, "company": None, "resume": None, "job": "AI_AX"}


def test_resetDeletesEverythingAndKeepsInterviewRecords(sessionFactory):
    appId = makeApplication(sessionFactory)
    with sessionFactory() as db:
        old = Question(source="excel", kind="job", text="엑셀 질문", status="active", sheet="s", row_no=1)
        db.add_all([old, Question(source="generated", kind="company", text="검토 대기 질문", status="pending")])
        db.flush()
        db.add(InterviewQuestion(application_id=appId, seq=1, qtype="job", text="엑셀 질문", source_question_id=old.id, source="excel"))
        db.commit()
        result = question_bank.resetQuestions(db)
        assert result["seeded"] == 40 and result["deleted"] >= 2
        assert {q.source for q in db.query(Question)} == {"reserve"} and db.query(Question).count() == 40
        kept = db.query(InterviewQuestion).filter_by(application_id=appId).one()
        assert (kept.text, kept.source_question_id) == ("엑셀 질문", None)
        assert db.query(AuditLog).filter_by(action="question.reset").count() == 1


def test_saveReserveRules(sessionFactory, monkeypatch):
    with sessionFactory() as db:
        assert question_bank.saveReserve(db, "company", "AIIT에서 해 보고 싶은 일은 무엇인가요?", None, "AI 생성")
        assert question_bank.saveReserve(db, "company", "AIIT에서  해 보고 싶은 일은 무엇인가요", None, "AI 생성") is None  # 같은 글
        assert question_bank.saveReserve(db, "company", "네이버에 지원한 이유는 무엇인가요?", None, "AI 생성") is None  # 다른 회사

        monkeypatch.setattr(rag, "supported", lambda s: True)
        monkeypatch.setattr(rag, "storeVector", lambda s, qid, v: None)
        monkeypatch.setattr(rag, "maxStoredSimilarity", lambda s, kind, v: 0.8)
        assert question_bank.saveReserve(db, "job", "배깅과 부스팅의 차이는 무엇인가요?", [0.1], "AI 생성") is None  # 0.8 이상
        monkeypatch.setattr(rag, "maxStoredSimilarity", lambda s, kind, v: 0.79)
        assert question_bank.saveReserve(db, "job", "배깅과 부스팅의 차이는 무엇인가요?", [0.1], "AI 생성", "AI_AX")

        monkeypatch.setattr(question_bank, "RESERVE_LIMIT_PER_KIND", 1)
        assert question_bank.saveReserve(db, "job", "드롭아웃은 왜 쓰나요?", [0.1], "AI 생성") is None  # 종류별 상한


# ---------- 관리자 예비 질문 화면 ----------

def addReserve(sessionFactory, kind, text, jobCode=None, createdAt=None) -> int:
    with sessionFactory() as db:
        q = question_bank.newReserve(kind, text, "AI 생성", jobCode)
        if createdAt:
            q.created_at = createdAt
        db.add(q)
        db.commit()
        return q.id


def test_adminListShowsColumnsAndNewForOneDay(adminClient, sessionFactory):
    fresh = addReserve(sessionFactory, "job", "리랭킹이 필요한 이유는 무엇인가요?", "AI_AX")
    old = addReserve(sessionFactory, "personality", "실수를 바로잡은 방법은 무엇인가요?", createdAt=now() - timedelta(days=1, minutes=1))
    body = adminClient.get("/admin/questions").json()
    items = {i["id"]: i for i in body["items"]}
    assert body["counts"] == {"personality": 1, "company": 0, "resume": 0, "job": 1} and body["limit"] == 100
    assert (items[fresh]["kind"], items[fresh]["job_name"], items[fresh]["job_only"], items[fresh]["is_new"]) == ("job", "AI/AX 엔지니어", True, True)
    assert (items[old]["job_only"], items[old]["is_new"]) == (False, False)
    assert [i["id"] for i in adminClient.get("/admin/questions?kind=job").json()["items"]] == [fresh]


def test_adminEditsTextAndJobOnly(adminClient, sessionFactory):
    qid = addReserve(sessionFactory, "company", "AIIT에 지원한 계기는 무엇인가요?")
    other = addReserve(sessionFactory, "company", "AIIT에서 이루고 싶은 목표는 무엇인가요?")
    res = adminClient.patch(f"/admin/questions/{qid}", json={"text": "  AIIT에 지원하게 된   계기는 무엇인가요? ", "job_only": True})
    assert res.status_code == 200
    assert (res.json()["text"], res.json()["job_only"]) == ("AIIT에 지원하게 된 계기는 무엇인가요?", True)
    assert adminClient.patch(f"/admin/questions/{qid}", json={"job_only": False}).json()["job_only"] is False
    assert adminClient.patch(f"/admin/questions/{other}", json={"text": "AIIT에 지원하게 된 계기는 무엇인가요?"}).status_code == 409
    assert adminClient.patch(f"/admin/questions/{qid}", json={"text": "짧음"}).status_code == 400
    with sessionFactory() as db:
        q = db.get(Question, qid)
        assert q.duplicate_group == question_bank.normalizeText("AIIT에 지원하게 된 계기는 무엇인가요?")[:128]
        assert db.query(AuditLog).filter_by(action="question.edit").count() == 2


def test_adminDeletesCheckedQuestions(adminClient, sessionFactory):
    ids = [addReserve(sessionFactory, "job", f"질문 {i}번의 원리는 무엇인가요?") for i in range(3)]
    with sessionFactory() as db:
        notReserve = Question(source="excel", kind="job", text="엑셀", status="active")
        db.add(notReserve)
        db.commit()
        notReserveId = notReserve.id
    assert adminClient.post("/admin/questions/delete", json={"ids": ids[:2] + [notReserveId]}).json() == {"deleted": 2}
    assert [i["id"] for i in adminClient.get("/admin/questions").json()["items"]] == [ids[2]]
    assert adminClient.patch(f"/admin/questions/{notReserveId}", json={"job_only": True}).status_code == 404


def test_applicantCannotUseReserveOrCompanyAdmin(client):
    assert client.get("/admin/questions").status_code in (401, 403)
    assert client.get("/admin/company").status_code in (401, 403)


# ---------- 회사 정보 · 최근 소식 ----------

RSS = """<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel>
<item><title>네이버, 쇼핑 AI 에이전트 공개 - 전자신문</title><link>https://news.example.com/a</link>
<pubDate>{recent}</pubDate><source url="https://etnews.com">전자신문</source></item>
<item><title>네이버, 쇼핑 AI 에이전트 공개 - 한국경제</title><link>https://news.example.com/b</link>
<pubDate>{recent}</pubDate><source url="https://hankyung.com">한국경제</source></item>
<item><title>오래된 소식</title><link>https://news.example.com/old</link><pubDate>{old}</pubDate></item>
<item><title>링크가 이상함</title><link>javascript:alert(1)</link><pubDate>{recent}</pubDate></item>
</channel></rss>"""


def rssText() -> str:
    fmt = "%a, %d %b %Y %H:%M:%S GMT"
    return RSS.format(recent=(datetime.utcnow() - timedelta(days=3)).strftime(fmt), old=(datetime.utcnow() - timedelta(days=200)).strftime(fmt))


def test_parseRssAndPickRecent():
    items = company.parseRss(rssText())
    assert [i["url"] for i in items] == ["https://news.example.com/a", "https://news.example.com/b", "https://news.example.com/old"]
    assert (items[0]["title"], items[0]["publisher"]) == ("네이버, 쇼핑 AI 에이전트 공개", "전자신문")
    picked = company.pickSpread([items])
    assert [i["url"] for i in picked] == ["https://news.example.com/a"]  # 6개월 지난 것·같은 제목은 뺀다


def test_pickSpreadTakesEachMonthThenFills():
    """한 번에 찾으면 그날 기사만 나온다(실측) → 달마다 고르고, 모자란 달은 다른 달 기사로 채운다."""
    def item(month, i):
        return {"title": f"{month}월 소식 {i}", "url": f"https://n.example.com/{month}/{i}", "publisher": "",
                "published_at": now() - timedelta(days=30 * month + i)}
    groups = [[item(0, i) for i in range(20)], [item(1, i) for i in range(2)]] + [[item(m, i) for i in range(5)] for m in range(2, 6)]
    picked = company.pickSpread(groups, limit=30)
    months = [int(p["title"].split("월")[0]) for p in picked]
    assert len(picked) == 30 and months.count(1) == 2 and all(months.count(m) == 5 for m in range(2, 6)) and months.count(0) == 8
    windows = company.monthWindows(now().date())
    assert len(windows) == 6 and windows[0][1] > now().date() and windows[-1][0] <= now().date() - timedelta(days=180)


def test_refreshKeepsRemovedNewsOutAndLimit(adminClient, sessionFactory, monkeypatch):
    monkeypatch.setattr(company, "SessionLocal", sessionFactory)

    async def fakeFetch(query, after, before):
        assert query == "네이버"
        return company.parseRss(rssText())
    monkeypatch.setattr(company, "fetchNews", fakeFetch)
    body = adminClient.post("/admin/company/news/refresh").json()
    assert body["refresh"] == {"ok": True, "added": 1, "total": 1}
    newsId = body["news"][0]["id"]
    assert body["news"][0]["url"] == "https://news.example.com/a"
    assert adminClient.post(f"/admin/company/news/{newsId}/hide").json()["news"] == []
    assert adminClient.post("/admin/company/news/refresh").json()["refresh"]["added"] == 0  # 제거한 소식은 다시 안 들어온다
    assert adminClient.post(f"/admin/company/news/{newsId}/hide").status_code == 404

    with sessionFactory() as db:
        db.add_all([CompanyNews(title=f"소식 {i}", url=f"https://n.example.com/{i}", published_at=now() - timedelta(hours=i))
                    for i in range(company.NEWS_LIMIT + 5)])
        db.flush()
        company.storeNews(db, [])
        db.commit()
        assert company.visibleNews(db).count() == company.NEWS_LIMIT
        assert company.listNews(db)[0].title == "소식 0"


def test_refreshFailureKeepsNews(sessionFactory, monkeypatch):
    import httpx
    monkeypatch.setattr(company, "SessionLocal", sessionFactory)

    async def down(query, after, before):
        raise httpx.ConnectError("offline")
    monkeypatch.setattr(company, "fetchNews", down)
    assert asyncio.run(company.refreshNews())["ok"] is False


def test_adminEditsCompanyAndPostingsFollowName(adminClient, sessionFactory):
    with sessionFactory() as db:
        db.add(JobPosting(status="draft", title="공고", contact_email="r@example.com"))
        db.commit()
    body = adminClient.get("/admin/company").json()
    assert body["profile"]["name"] == "AIIT" and "업무 혁신(AX)" in body["profile"]["ai_ax_role"] and body["news_limit"] == 30
    with sessionFactory() as db:
        assert {p.company_name for p in db.query(JobPosting)} == {"AIIT"}  # 회사명이 빈 공고에 채운다
    res = adminClient.put("/admin/company", json={"name": "AIIT 코리아", "intro": "새 소개입니다."})
    assert (res.json()["profile"]["name"], res.json()["profile"]["intro"]) == ("AIIT 코리아", "새 소개입니다.")
    assert adminClient.put("/admin/company", json={"name": ""}).status_code in (400, 422)
    with sessionFactory() as db:
        assert {p.company_name for p in db.query(JobPosting)} == {"AIIT 코리아"}
        assert db.query(AuditLog).filter_by(action="company.update").one().detail["fields"] == ["name", "intro"]


def test_newDraftPostingUsesCompanyName(adminClient):
    res = adminClient.post("/admin/postings", json={"title": "AI/AX 엔지니어"})
    assert res.status_code == 201 and res.json()["company_name"] == "AIIT"


def test_companyQuestionPromptGetsCompanyInfoAndNews(sessionFactory, world):  # noqa: F811
    fake = world()
    with sessionFactory() as db:
        db.add(CompanyNews(title="네이버, 쇼핑 AI 에이전트 공개", url="https://news.example.com/a", published_at=now()))
        db.commit()
    appId = makeApplication(sessionFactory)
    asyncio.run(question_compose.compose(appId))
    assert len(composed(sessionFactory, appId)) == 10
    companyPrompt = next(p for p in fake.prompts if p.startswith("[만들 질문] 회사"))
    assert "회사 이름: AIIT" in companyPrompt and "AIIT, 쇼핑 AI 에이전트 공개" in companyPrompt  # 검색어를 회사 이름으로
    assert "네이버" not in companyPrompt
    jobPrompt = next(p for p in fake.prompts if p.startswith("[만들 질문] 직무"))
    assert "<회사>" not in jobPrompt  # 회사 정보는 회사 질문에만
