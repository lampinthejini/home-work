"""예비 질문과 회사 정보 (2026-11-16 사용자 결정, CONFLICTS C-20).

- 엑셀 질문 DB 를 지우고 종류마다 기본 질문 10개. AI 질문은 승인 없이 예비 질문에 (0.7 이상 비슷하면 빼고, 종류마다 100개까지 — C-28)
- 관리자 예비 질문: 질문분야 · 질문(직접 고침) · 직무 · 해당 직무만 · 삭제(여러 개), 하루 동안 NEW
- 회사 정보와 회사 프로젝트(관리자가 적음, 2026-11-17 C-21 — 최근 소식은 지움), 회사 질문·공고 초안 RAG
"""

import asyncio
from datetime import timedelta

from app.domain import question_text
from app.models import AuditLog, CompanyProject, InterviewQuestion, JobPosting, Question
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
        monkeypatch.setattr(rag, "maxStoredSimilarity", lambda s, kind, v: 0.7)
        assert question_bank.saveReserve(db, "job", "배깅과 부스팅의 차이는 무엇인가요?", [0.1], "AI 생성") is None  # 0.7 이상 (C-28)
        monkeypatch.setattr(rag, "maxStoredSimilarity", lambda s, kind, v: 0.69)
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


# ---------- 회사 정보 · 회사 프로젝트 ----------

def test_adminAddsEditsAndDeletesProjects(adminClient, sessionFactory, monkeypatch):
    monkeypatch.setattr(company, "PROJECT_LIMIT", 2)
    body = adminClient.post("/admin/company/projects", json={"title": " 검색 요약 AI ", "period": "2024~2025",
                                                             "summary": "검색 결과를 AI 가 요약합니다."}).json()
    assert body["project_limit"] == 2
    assert [(p["title"], p["period"]) for p in body["projects"]] == [("검색 요약 AI", "2024~2025")]
    projectId = body["projects"][0]["id"]
    body = adminClient.patch(f"/admin/company/projects/{projectId}", json={"summary": "바뀐 내용"}).json()
    assert body["projects"][0]["summary"] == "바뀐 내용" and body["projects"][0]["title"] == "검색 요약 AI"
    assert adminClient.post("/admin/company/projects", json={"title": "   "}).status_code == 422
    assert adminClient.patch(f"/admin/company/projects/{projectId}", json={"title": " "}).status_code == 422
    assert adminClient.post("/admin/company/projects", json={"title": "둘째"}).status_code == 200
    assert adminClient.post("/admin/company/projects", json={"title": "셋째"}).status_code == 409  # 개수 한도
    assert adminClient.delete(f"/admin/company/projects/{projectId}").json()["projects"][0]["title"] == "둘째"
    assert adminClient.delete(f"/admin/company/projects/{projectId}").status_code == 404
    assert adminClient.patch(f"/admin/company/projects/{projectId}", json={"title": "x"}).status_code == 404
    with sessionFactory() as db:
        actions = [a.action for a in db.query(AuditLog).filter(AuditLog.action.like("company.project%")).order_by(AuditLog.id)]
        assert actions == ["company.project_add", "company.project_update", "company.project_add", "company.project_delete"]


def test_newsIsGone(adminClient):
    """회사 최근 소식(뉴스)은 지웠다 (2026-11-17 사용자 결정, C-21)."""
    body = adminClient.get("/admin/company").json()
    assert "news" not in body and "news_query" not in body["profile"]
    assert adminClient.post("/admin/company/news/refresh").status_code in (404, 405)
    assert not hasattr(company, "refreshNews")


def test_postingContextHasCompanyInfoAndProjects(sessionFactory):
    with sessionFactory() as db:
        assert "회사가 진행한 프로젝트" not in company.postingContext(db)  # 없으면 칸도 없다
        db.add_all([CompanyProject(title=f"프로젝트 {i}", period="2025", summary="내용 " * 200) for i in range(7)])
        db.commit()
        text = company.postingContext(db)
    assert "직무 소개:" in text and "회사가 진행한 프로젝트:" in text
    lines = [line for line in text.splitlines() if line.startswith("- 프로젝트")]
    assert len(lines) == company.POSTING_PROJECT_COUNT
    assert lines[0].startswith("- 프로젝트 0 (2025): ") and len(lines[0]) < company.PROJECT_TEXT_CHARS + 30


def test_adminEditsCompanyAndPostingsFollowName(adminClient, sessionFactory):
    with sessionFactory() as db:
        db.add(JobPosting(status="draft", title="공고", contact_email="r@example.com"))
        db.commit()
    body = adminClient.get("/admin/company").json()
    assert body["profile"]["name"] == "AIIT" and "업무 혁신(AX)" in body["profile"]["ai_ax_role"] and body["projects"] == []
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


def test_postingIgnoresCompanyNameFromRequest(adminClient):
    """회사 이름은 회사 정보 하나에서만 온다 (C-20, API 명세서 v1.5 '보내도 쓰지 않음')."""
    res = adminClient.post("/admin/postings", json={"title": "AI/AX 엔지니어", "company_name": "다른 회사"})
    assert res.status_code == 201 and res.json()["company_name"] == "AIIT"
    postingId = res.json()["posting_id"]
    res = adminClient.patch(f"/admin/postings/{postingId}", json={"company_name": "다른 회사"})
    assert res.status_code == 200 and res.json()["company_name"] == "AIIT"


def test_companyQuestionPromptGetsCompanyInfoAndProjects(sessionFactory, world):  # noqa: F811
    fake = world()
    with sessionFactory() as db:
        db.add(CompanyProject(title="쇼핑 AI 에이전트", period="2025", summary="상품을 대신 찾아 주는 에이전트"))
        db.commit()
    appId = makeApplication(sessionFactory)
    asyncio.run(question_compose.compose(appId))
    assert len(composed(sessionFactory, appId)) == 10
    companyPrompt = next(p for p in fake.prompts if p.startswith("[만들 질문] 회사"))
    assert "회사 이름: AIIT" in companyPrompt and "- 쇼핑 AI 에이전트 (2025): 상품을 대신 찾아 주는 에이전트" in companyPrompt
    assert "최근 소식" not in companyPrompt
    jobPrompt = next(p for p in fake.prompts if p.startswith("[만들 질문] 직무"))
    assert "<회사>" not in jobPrompt  # 회사 정보는 회사 질문에만
