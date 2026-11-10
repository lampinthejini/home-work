"""질문 10개 RAG 구성 (TRD 7-4, 사용자 결정 U5): RAG 로 먼저 만들고, 못 만들면 질문은행 → 예비 질문.

임베딩·pgvector·LLM 은 가짜로 바꾼다. 질문 글의 뜻은 '키워드 → 축' 숫자 목록으로 흉내 낸다.
"""

import asyncio
import math
from datetime import timedelta

import pytest

from app.models import Application, InterviewQuestion, JobPosting, Question, User
from app.services import llm, question_compose, rag
from app.timeutil import now

RESUME = {
    "projects": [{"name": "RAG 챗봇", "period": "2025", "description": "사내 문서 검색 정확도를 12% 올림", "skills": ["LangChain"]}],
    "skills": ["Python", "PyTorch"],
}
KEYWORDS = ["갈등", "지원", "프로젝트", "모델", "데이터", "협업", "문화", "검색"]


def fakeVector(text: str) -> list[float]:
    """키워드가 들어 있으면 그 축에 값을 둔다. 길이 1로 맞춘 1024차원."""
    v = [0.0] * rag.EMBED_DIM
    for i, word in enumerate(KEYWORDS):
        if word in text:
            v[i] = 1.0
    v[100 + sum(map(ord, text)) % 900] = 0.3  # 글마다 조금씩 다르게
    norm = math.sqrt(sum(x * x for x in v))
    return [x / norm for x in v]


class FakeWorld:
    def __init__(self, sessionFactory, copyExamples=False, ungrounded=False, embedDown=False):
        self.sessionFactory = sessionFactory
        self.copyExamples, self.ungrounded, self.embedDown = copyExamples, ungrounded, embedDown
        self.prompts: list[str] = []
        self.counter = 0

    async def embed(self, texts, timeoutSec=10):
        if self.embedDown:
            raise rag.EmbedUnavailable("down")
        return [fakeVector(t) for t in texts]

    async def health(self, timeoutSec=3):
        return not self.embedDown

    def similar(self, db, slotKind, vector, count, excludeIds):
        rows = (db.query(Question).filter(Question.kind == rag.EXAMPLE_KIND[slotKind], Question.source == "excel")
                .filter(Question.id.notin_(excludeIds or {-1})).order_by(Question.id).limit(count).all())
        return [rag.Example(q.id, q.text, 0.8, fakeVector(q.text)) for q in rows]

    def vectorsFor(self, db, ids):
        return {q.id: fakeVector(q.text) for q in db.query(Question).filter(Question.id.in_(ids))}

    def maxStoredSimilarity(self, db, kind, vector):
        return rag.maxSimilarity(vector, [fakeVector(q.text) for q in db.query(Question).filter(Question.kind == kind)])

    def storeVector(self, db, questionId, vector):
        pass

    async def structured(self, schema, system, user, timeoutSec, maxTokens=400, temperature=0.4, lane="rt"):
        assert schema is question_compose.RagQuestion
        self.prompts.append(user)
        self.counter += 1
        examples = user.split("그대로 베끼지 말 것]\n")[1].split("\n\n")[0].splitlines()
        if self.copyExamples:
            return schema(question=examples[0][2:], task_count=1)
        if "[만들 질문] 이력서 기반" in user:
            evidence = "사내 문서 검색 정확도를 12% 올림" if not self.ungrounded else "추천 시스템을 혼자 만들었음"
            text = ("RAG 챗봇에서 검색 정확도를 올린 방법을 설명해 주세요?" if self.counter % 2
                    else "RAG 챗봇을 만들 때 본인이 맡은 역할은 무엇이었나요?")
            return schema(question=text, evidence=evidence, task_count=1)
        kind = user.split("[만들 질문] ")[1].split(" ")[0]
        return schema(question=f"{kind} 관점에서 새로 만든 질문 {self.counter}번에 답해 주시겠어요?", task_count=1)


@pytest.fixture()
def world(sessionFactory, monkeypatch):
    def setup(**kwargs):
        fake = FakeWorld(sessionFactory, **kwargs)
        monkeypatch.setattr(question_compose, "SessionLocal", sessionFactory)
        monkeypatch.setattr(rag, "supported", lambda db: True)
        monkeypatch.setattr(rag, "indexedCount", lambda db: 100)
        monkeypatch.setattr(rag, "health", fake.health)
        monkeypatch.setattr(rag, "embed", fake.embed)
        monkeypatch.setattr(rag, "similar", fake.similar)
        monkeypatch.setattr(rag, "vectorsFor", fake.vectorsFor)
        monkeypatch.setattr(rag, "maxStoredSimilarity", fake.maxStoredSimilarity)
        monkeypatch.setattr(rag, "storeVector", fake.storeVector)
        monkeypatch.setattr(llm, "structured", fake.structured)

        async def noAudio(db, app):
            return None
        monkeypatch.setattr(question_compose, "synthesizeAll", noAudio)
        return fake
    return setup


def makeApplication(sessionFactory) -> str:
    with sessionFactory() as db:
        user = User(email="kim@example.com", password_hash="x", name="김지원", role="applicant")
        posting = JobPosting(status="published", title="AI/AX 엔지니어", close_at=now() + timedelta(days=3),
                             company_intro="제조 현장의 데이터를 AI 로 바꾸는 회사입니다", duties="사내 LLM·RAG 서비스 개발",
                             requirements="Python", preferred="LangChain 경험", contact_email="recruit@example.com")
        db.add_all([user, posting])
        db.flush()
        bank = {"personality": ["갈등을 해결한 경험을 말해 주세요.", "협업에서 맡은 역할은 무엇이었나요?", "실패에서 배운 점은 무엇인가요?"],
                "company": ["우리 회사에 지원한 이유는 무엇인가요?", "우리 회사 문화에 어떻게 기여할 수 있나요?", "입사 후 목표는 무엇인가요?"],
                "job": [f"모델 과적합을 막는 방법 {i}은 무엇인가요?" for i in range(8)]}
        for kind, texts in bank.items():
            for i, text in enumerate(texts):
                db.add(Question(source="excel", kind=kind, text=text, sheet=kind, row_no=i, duplicate_group=f"{kind}-{i}"))
        for kind in ("personality", "company", "job", "resume"):
            db.add(Question(source="reserve", kind=kind, text=f"예비 {kind} 질문입니다. 경험을 말해 주세요.", duplicate_group=f"r-{kind}"))
        app = Application(user_id=user.id, posting_id=posting.id, attempt_status="ready", resume_snapshot=RESUME)
        db.add(app)
        db.commit()
        return app.id


def composed(sessionFactory, appId) -> list[InterviewQuestion]:
    with sessionFactory() as db:
        return db.query(InterviewQuestion).filter_by(application_id=appId).order_by(InterviewQuestion.seq).all()


def test_ragGeneratesEverySlotWithExamplesResumeAndCompany(sessionFactory, world):
    fake = world()
    appId = makeApplication(sessionFactory)
    asyncio.run(question_compose.compose(appId))
    rows = composed(sessionFactory, appId)
    assert len(rows) == 10 and [r.qtype for r in rows] == question_compose.SLOT_ORDER
    assert {r.source for r in rows} == {"generated"} and not any(r.substituted for r in rows)
    prompt = next(p for p in fake.prompts if p.startswith("[만들 질문] 직무"))
    assert "모델 과적합을 막는 방법" in prompt  # 기존 질문 (RAG 예시)
    resumePart = prompt.split("<이력서>\n")[1].split("\n</이력서>")[0]
    assert "LangChain" in resumePart and "RAG 챗봇" not in resumePart  # 직무 질문엔 이력서 기술만 (프로젝트는 이력서 질문에서)
    resumePrompt = next(p for p in fake.prompts if p.startswith("[만들 질문] 이력서 기반"))
    assert "RAG 챗봇" in resumePrompt  # 이력서
    assert "제조 현장의 데이터" in prompt  # 회사의 상황
    # 앞 자리에서 본 예시는 다음 자리에서 빼고, 다 쓰면 다시 쓴다 → 직무 4자리 모두 예시가 있다
    jobExamples = [p.split("그대로 베끼지 말 것]\n")[1].split("\n\n")[0] for p in fake.prompts if p.startswith("[만들 질문] 직무")]
    assert len(jobExamples) == 4 and all(jobExamples) and jobExamples[0] != jobExamples[1]


def test_copyingExampleFallsBackToQuestionBank(sessionFactory, world):
    fake = world(copyExamples=True)
    appId = makeApplication(sessionFactory)
    asyncio.run(question_compose.compose(appId))
    rows = composed(sessionFactory, appId)
    job = next(r for r in rows if r.qtype == "job")
    assert (job.source, job.substituted, job.regen_count, job.substitute_reason) == ("excel", True, 3, "copied_example")
    assert len({r.text for r in rows}) == 10
    assert fake.counter == 30  # 자리마다 3번까지 다시 만들기


def test_resumeQuestionNotInResumeUsesReserve(sessionFactory, world):
    world(ungrounded=True)
    appId = makeApplication(sessionFactory)
    asyncio.run(question_compose.compose(appId))
    resume = [r for r in composed(sessionFactory, appId) if r.qtype == "resume"]
    assert resume[0].source == "reserve" and resume[0].substitute_reason == "resume_not_grounded"


def test_embedServerDownUsesQuestionBankWithoutLlm(sessionFactory, world):
    fake = world(embedDown=True)
    appId = makeApplication(sessionFactory)
    asyncio.run(question_compose.compose(appId))
    rows = composed(sessionFactory, appId)
    assert fake.counter == 0
    assert {r.source for r in rows if r.qtype != "resume"} == {"excel"}
    assert all(r.substituted and r.substitute_reason == "rag_unavailable" for r in rows)


def test_noTimeLeftSkipsGeneration(sessionFactory, world):
    fake = world()
    appId = makeApplication(sessionFactory)
    asyncio.run(question_compose.compose(appId, budgetSec=0))
    assert fake.counter == 0 and len(composed(sessionFactory, appId)) == 10


def test_bankFallbackSkipsQuestionTooSimilarToChosen(sessionFactory, world):
    world()
    appId = makeApplication(sessionFactory)
    with sessionFactory() as db:
        app = db.get(Application, appId)
        first = db.query(Question).filter_by(kind="personality", source="excel").order_by(Question.id).first()
        chosen = [{"text": "다른 글", "vector": fakeVector(first.text)}]  # 뜻이 같은 질문을 이미 골랐다
        ctx = {"usedGroups": set(), "usedIds": set()}
        picked = question_compose.bankFallback(db, app, "personality", chosen, ctx)
        assert picked is not None and picked.id != first.id


@pytest.mark.parametrize(("similarity", "lastText", "regenCount"), [
    (0.95, "회사 질문 셋째은 무엇인가요?", 1),  # 면접 안 중복 기준(0.9) 이상 → 다시 만든다
    (0.85, "회사 질문 둘째은 무엇인가요?", 0),  # 0.8~0.9 는 면접에서 물어도 된다 (질문 관리에만 넣지 않는다)
])
def test_generatedQuestionSimilarToChosenIsRegenerated(sessionFactory, world, monkeypatch, similarity, lastText, regenCount):
    fake = world()
    base = [0.0] * rag.EMBED_DIM
    base[900] = 1.0
    near = [0.0] * rag.EMBED_DIM
    near[900], near[901] = similarity, math.sqrt(1 - similarity ** 2)
    vectors = {"회사 질문 첫째은 무엇인가요?": base, "회사 질문 둘째은 무엇인가요?": near}
    realEmbed, realStructured = fake.embed, fake.structured
    companyTexts = iter(["회사 질문 첫째은 무엇인가요?", "회사 질문 둘째은 무엇인가요?", "회사 질문 셋째은 무엇인가요?"])

    async def embed(texts, timeoutSec=10):
        return [vectors.get(t) or (await realEmbed([t]))[0] for t in texts]

    async def structured(schema, system, user, timeoutSec, maxTokens=400, temperature=0.4, lane="rt"):
        if user.startswith("[만들 질문] 회사"):
            return schema(question=next(companyTexts), task_count=1)
        return await realStructured(schema, system, user, timeoutSec, maxTokens, temperature, lane)

    monkeypatch.setattr(rag, "embed", embed)
    monkeypatch.setattr(llm, "structured", structured)
    appId = makeApplication(sessionFactory)
    asyncio.run(question_compose.compose(appId))
    rows = composed(sessionFactory, appId)
    assert len(rows) == 10
    assert (rows[-1].text, rows[-1].source, rows[-1].regen_count) == (lastText, "generated", regenCount)


def test_answerFormatWordsInQuestionAreRejected():
    out = question_compose.RagQuestion(question="RAG 에서 청크 크기를 정하는 기준을 90초 내에 한 문장으로 설명해 주세요?", task_count=1)
    assert question_compose.checkGenerated("job", out, "") == "meta_phrase"
    ok = question_compose.RagQuestion(question="RAG 에서 청크 크기를 정하는 기준은 무엇인가요?", task_count=1)
    assert question_compose.checkGenerated("job", ok, "") is None


def test_numberedSentenceCountIsRejected():
    """실측(2026-11-10 시뮬레이션): '1문장으로 설명해 주세요'가 검사를 통과했다. 숫자·'하나의'·'두 문장' 표기도 막는다."""
    for text in ("검색 결과를 재구성할 때 가장 중요한 요소를 1문장으로 설명해 주세요?", "그 이유를 1 문장으로 말씀해 주세요?",
                 "그 이유를 하나의 문장으로 말씀해 주세요?", "그 이유를 두 문장으로 말씀해 주세요?", "그 이유를 2문장 이내로 말씀해 주세요?"):
        out = question_compose.RagQuestion(question=text, task_count=1)
        assert question_compose.checkGenerated("job", out, "") == "meta_phrase", text
    ok = question_compose.RagQuestion(question="문장 임베딩 모델을 고를 때 무엇을 기준으로 삼나요?", task_count=1)
    assert question_compose.checkGenerated("job", ok, "") is None


def test_jobTopicsInterleavePostingLinesThenSkills():
    posting = JobPosting(duties="LLM 서비스 개발\nRAG 파이프라인 구축", requirements="Python 개발 경험\n머신러닝 기본 지식", preferred="벡터 DB 경험")
    assert question_compose.jobTopics(posting, {"skills": ["PyTorch", "Python 개발 경험"]}) == [
        "LLM 서비스 개발", "Python 개발 경험", "벡터 DB 경험", "RAG 파이프라인 구축", "머신러닝 기본 지식", "PyTorch"]


def test_resumeEvidenceWithJsonTailStillGrounded():
    resume = "프로젝트: RAG 챗봇 (2024) LangChain 으로 검색 정확도를 12% 올렸다 [Python, FastAPI]"
    out = question_compose.RagQuestion(question="RAG 챗봇에서 검색 정확도를 올린 방법은 무엇인가요?",
                                       evidence="LangChain 으로 검색 정확도를 12% 올렸다 [Python, FastAPI]'}", task_count=1)
    assert question_compose.checkGenerated("resume", out, resume) is None
    out.evidence = "추천 시스템을 혼자 만들었다"
    assert question_compose.checkGenerated("resume", out, resume) == "resume_not_grounded"


def test_foreignScriptRejected():
    out = question_compose.RagQuestion(question="평가 지표 중 하나를 举げ고 그 이유를 설명해 주세요?", task_count=1)
    assert question_compose.checkGenerated("job", out, "") == "foreign_script"


def test_concurrentUsageCountDoesNotConflict(sessionFactory):
    appId = makeApplication(sessionFactory)
    with sessionFactory() as db:
        app = db.get(Application, appId)
        qid = db.query(Question).filter_by(source="excel").first().id
        question_compose.countUsage(db, app.posting_id, [qid])
        question_compose.countUsage(db, app.posting_id, [qid])  # 이미 있는 행 → 충돌 없이 +1
        from app.models import QuestionUsage
        assert db.get(QuestionUsage, (app.posting_id, qid)).use_count == 2


def test_embedDownMidwaySendsRestToBankQuickly(sessionFactory, world, monkeypatch):
    fake = world()
    calls = {"n": 0}
    realEmbed = fake.embed

    async def flaky(texts, timeoutSec=10):
        calls["n"] += 1
        if calls["n"] > 2:
            raise rag.EmbedUnavailable("down")
        return await realEmbed(texts)
    monkeypatch.setattr(rag, "embed", flaky)
    appId = makeApplication(sessionFactory)
    asyncio.run(question_compose.compose(appId))
    rows = composed(sessionFactory, appId)
    assert rows[0].source == "generated" and calls["n"] == 3  # 한 번 실패한 뒤로는 임베딩을 다시 부르지 않음
    assert all(r.substituted for r in rows[1:])


def pendingQuestions(sessionFactory) -> list[Question]:
    with sessionFactory() as db:
        return db.query(Question).filter_by(source="generated").order_by(Question.id).all()


def test_generatedQuestionsSavedForReviewExceptResume(sessionFactory, world):
    world()
    appId = makeApplication(sessionFactory)
    asyncio.run(question_compose.compose(appId))
    saved = pendingQuestions(sessionFactory)
    assert len(saved) == 8  # 10자리 중 이력서 기반 2개는 넣지 않는다
    assert {q.kind for q in saved} == {"personality", "company", "job"}
    assert all(q.status == "pending" and q.duplicate_group for q in saved)
    with sessionFactory() as db:
        first = db.get(Application, appId)
        other = User(email="other@example.com", password_hash="x", name="이지원", role="applicant")  # 공고마다 한 사람 1건
        db.add(other)
        db.flush()
        second = Application(user_id=other.id, posting_id=first.posting_id, attempt_status="ready", resume_snapshot=RESUME)
        db.add(second)
        db.commit()
        secondId = second.id
    asyncio.run(question_compose.compose(secondId))
    texts = [q.text for q in pendingQuestions(sessionFactory)]
    assert len(texts) == len(set(texts))  # 같은 질문은 두 번 넣지 않는다


@pytest.mark.parametrize(("stored", "saved"), [(0.85, False), (0.75, True)])
def test_savePendingSkipsQuestionSimilarToStored(sessionFactory, world, monkeypatch, stored, saved):
    world()
    monkeypatch.setattr(rag, "maxStoredSimilarity", lambda db, kind, vector: stored)
    appId = makeApplication(sessionFactory)
    text = "우리 회사에서 해 보고 싶은 일은 무엇인가요?"
    with sessionFactory() as db:
        app = db.get(Application, appId)
        question_compose.savePending(db, app, [{"source": "generated", "qtype": "company", "text": text, "vector": fakeVector(text)}])
    assert bool(pendingQuestions(sessionFactory)) is saved


def test_personalGeneratedQuestionNotSaved(sessionFactory):
    appId = makeApplication(sessionFactory)
    with sessionFactory() as db:
        app = db.get(Application, appId)
        terms = question_compose.personalTerms(app)
        assert question_compose.isPersonal("RAG 챗봇에서 배운 점을 말해 주세요.", terms, app)
        assert question_compose.isPersonal("김지원 님이 팀에서 맡은 역할은 무엇인가요?", terms, app)
        assert question_compose.isPersonal("사내 문서 검색 정확도를 12% 올린 방법을 설명해 주세요.", terms, app)  # 이력서 문구
        assert not question_compose.isPersonal("데이터 불균형을 다루는 방법을 설명해 주세요.", terms, app)


def test_pendingQuestionNotUsedUntilApproved(sessionFactory, adminClient):
    appId = makeApplication(sessionFactory)
    with sessionFactory() as db:
        q = Question(source="generated", kind="company", text="우리 회사에서 해 보고 싶은 일은 무엇인가요?", status="pending",
                     duplicate_group="g-new")
        db.add(q)
        db.commit()
        qid = q.id
        app = db.get(Application, appId)
        assert qid not in [c.id for c in question_compose.candidates(db, app, "company", set(), set())]
    listed = adminClient.get("/admin/questions?status=pending").json()
    assert [i["id"] for i in listed["items"]] == [qid] and listed["counts"]["pending"] == 1
    assert adminClient.post(f"/admin/questions/{qid}/approve").json()["status"] == "active"
    with sessionFactory() as db:
        app = db.get(Application, appId)
        assert qid in [c.id for c in question_compose.candidates(db, app, "company", set(), set())]
    assert adminClient.post(f"/admin/questions/{qid}/reject").json()["status"] == "rejected"
    with sessionFactory() as db:
        from app.models import AuditLog
        assert [a.action for a in db.query(AuditLog).filter(AuditLog.action.like("question.%"))] == ["question.approve", "question.reject"]
        excelId = db.query(Question).filter_by(source="excel").first().id
    assert adminClient.post(f"/admin/questions/{excelId}/reject").status_code == 404  # 엑셀 질문은 여기서 바꾸지 않는다


def test_applicantCannotReviewQuestions(client):
    assert client.get("/admin/questions").status_code in (401, 403)


# ---------- 2026-11-10 시뮬레이션에서 나온 문제 (사용자 결정) ----------

FULL_RESUME = {
    "projects": [{"name": "공장 불량 검출 카메라", "period": "2024", "description": "YOLO 모델을 젯슨에 올려 검출 지연을 40ms 로 줄임", "skills": ["PyTorch"]}],
    "career": [{"company": "다라전자", "role": "임베디드 개발", "description": "C++ 로 카메라 펌웨어 개발"}],
    "education": [{"school": "마바대학교", "major": "통계학", "degree": "학사"}],
    "skills": ["C++", "PyTorch", "pandas"],
}


def test_resumeTextHasNoBracketsThatLookLikeJson():
    """실측: 줄 끝 '[PyTorch]' 를 근거로 옮기던 4B 모델이 ']' 뒤에 '}·✅✅…' 를 이어 써서 근거 검사에 떨어졌다."""
    text = question_compose.resumeText(FULL_RESUME)
    assert "[" not in text and "]" not in text and "사용 기술: PyTorch" in text


def test_resumeEvidenceMustComeFromExperienceNotSkills():
    """기술 이름만 맞는 근거(실측: 신입에게 'pandas 프로젝트')는 받지 않는다. 경력·프로젝트·자기소개 줄에서만."""
    experience = question_compose.experienceText(FULL_RESUME)
    assert "다라전자" in experience and "공장 불량 검출 카메라" in experience and "pandas" not in experience and "마바대학교" not in experience
    anchors = question_compose.experienceAnchors(FULL_RESUME)
    ok = question_compose.RagQuestion(question="공장 불량 검출 카메라 프로젝트에서 검출 지연을 줄일 때 가장 먼저 확인한 것은 무엇이었나요?",
                                      evidence="YOLO 모델을 젯슨에 올려 검출 지연을 40ms 로 줄임 — 사용 기술: PyTorch'} ✅✅✅ 📌 Note", task_count=1)
    assert question_compose.checkGenerated("resume", ok, experience, anchors) is None  # 앞부분이 이력서와 같으면 뒤 찌꺼기는 무시
    skillOnly = ok.model_copy(update={"evidence": "C++, PyTorch, pandas"})
    assert question_compose.checkGenerated("resume", skillOnly, experience, anchors) == "resume_not_grounded"
    tooShort = ok.model_copy(update={"evidence": "젯슨"})
    assert question_compose.checkGenerated("resume", tooShort, experience, anchors) == "resume_not_grounded"


def test_resumeQuestionMustNameTheExperience():
    """질문이 이력서의 프로젝트·회사 이름을 짚어야 한다 (공고 업무를 섞어 지어낸 경험을 막는다)."""
    experience, anchors = question_compose.experienceText(FULL_RESUME), question_compose.experienceAnchors(FULL_RESUME)
    out = question_compose.RagQuestion(question="비전 검사 데이터 파이프라인을 설계할 때 본인의 역할은 무엇이었나요?",
                                       evidence="YOLO 모델을 젯슨에 올려 검출 지연을 40ms 로 줄임", task_count=1)
    assert question_compose.checkGenerated("resume", out, experience, anchors) == "resume_not_anchored"


def test_resumeWithoutExperienceSkipsLlmForResumeSlots(sessionFactory, world):
    """경력·프로젝트·자기소개가 없으면 이력서 자리는 AI 를 부르지 않고 예비 질문으로 (지어낼 거리가 없다)."""
    fake = world()
    appId = makeApplication(sessionFactory)
    with sessionFactory() as db:
        app = db.get(Application, appId)
        app.resume_snapshot = {"education": [{"school": "마바대학교", "major": "통계학"}], "skills": ["Python", "pandas"]}
        db.commit()
    asyncio.run(question_compose.compose(appId))
    resume = [r for r in composed(sessionFactory, appId) if r.qtype == "resume"]
    assert [(r.source, r.substitute_reason) for r in resume] == [("reserve", "no_resume_experience")] * 2
    assert not any(p.startswith("[만들 질문] 이력서 기반") for p in fake.prompts)


def test_resumePromptLeavesOutPostingText(sessionFactory, world):
    """이력서 질문에는 공고 글을 넣지 않는다 (실측: 공고의 '비전 검사'를 섞어 없는 경험을 지어냄)."""
    fake = world()
    asyncio.run(question_compose.compose(makeApplication(sessionFactory)))
    resumePrompt = next(p for p in fake.prompts if p.startswith("[만들 질문] 이력서 기반"))
    assert "<공고>" not in resumePrompt and "제조 현장의 데이터" not in resumePrompt and "RAG 챗봇" in resumePrompt


@pytest.mark.parametrize("text", [
    "LangChain으로 RAG 시스템을 구축한 경험이 있으신가요?",
    "비전 검사 모델 성능을 유지하기 위해 어떤 메커니즘을 도입했나요?",
    "Python으로 이상치를 제거할 때 어떤 방법을 사용했는지 설명해 주세요.",
])
def test_jobQuestionMustAskKnowledgeNotExperience(text):
    """직무 질문은 겪은 일이 아니라 지식(개념·기준·방법)을 묻는다 (신입에게 없는 경험을 전제하지 않게)."""
    out = question_compose.RagQuestion(question=text, task_count=1)
    assert question_compose.checkGenerated("job", out, "") == "job_asks_experience"
    ok = question_compose.RagQuestion(question="RAG 에서 청크 크기를 정할 때 무엇을 기준으로 삼나요?", task_count=1)
    assert question_compose.checkGenerated("job", ok, "") is None


def test_onlyOneTaskPerQuestion():
    out = question_compose.RagQuestion(question="RAG 에서 청크 크기를 정할 때 무엇을 기준으로 삼나요?", task_count=2)
    assert question_compose.checkGenerated("job", out, "") == "too_many_tasks"


def test_retryShowsPreviousQuestionToFix(sessionFactory, world, monkeypatch):
    """실측: '어떤 역할을 했고, 그 이유는 무엇인가요?' 를 6번 되풀이했다. 다시 만들 때 이전 질문을 보여 주고 고치게 한다."""
    fake = world()
    calls = []

    async def compoundFirst(schema, system, user, timeoutSec, maxTokens=400, temperature=0.4, lane="rt"):
        calls.append(user)
        if len(calls) == 1:
            return schema(question="협업 중 어떤 역할을 맡았고, 그 이유는 무엇인가요?", task_count=1)
        return await fake.structured(schema, system, user, timeoutSec, maxTokens, temperature, lane)

    monkeypatch.setattr(llm, "structured", compoundFirst)
    asyncio.run(question_compose.compose(makeApplication(sessionFactory)))
    assert "협업 중 어떤 역할을 맡았고, 그 이유는 무엇인가요?" in calls[1] and "한 가지만" in calls[1]


@pytest.mark.parametrize("text", [
    "사내 LLM·RAG 서비스에서 검색 결과의 신뢰도를 평가하는 기준은 무엇이었나요?",  # 실측: 과거형 = 겪은 일
    "비전 검사 모델을 운영할 때 정확도를 높이기 위한 핵심 기준은 무엇이었나요?",
    "LangChain 체인을 어떻게 구성하셨나요?",
])
def test_pastTenseJobQuestionAsksExperience(text):
    out = question_compose.RagQuestion(question=text, task_count=1)
    assert question_compose.checkGenerated("job", out, "") == "job_asks_experience"


def test_promptGivesKindSpecificFormsNotOneTemplate():
    """실측: 예시 꼴 하나('…은 무엇을 기준으로 정하나요?')를 모든 자리가 베꼈다. 종류마다 다른 꼴을 준다."""
    prompts = {kind: question_compose.ragPrompt(kind, "회사", "이력서", [], [], None) for kind in question_compose.KIND_GUIDE}
    forms = {kind: question_compose.KIND_FORMS[kind] for kind in question_compose.KIND_GUIDE}
    assert all(forms[kind] in prompts[kind] for kind in prompts)
    assert len(set(forms.values())) == len(forms) and "무엇을 기준으로 정하나요" not in "".join(prompts.values())
    assert "기술 지식을 묻지 않는다" in prompts["personality"] and "기술 지식을 묻지 않는다" in prompts["company"]


@pytest.mark.parametrize("text", [
    "우리 회사의 제품 개발 환경에서 가장 감명받은 경험은 무엇인가요?",  # 실측 2026-11-10: 아직 입사 전인 지원자에게 회사 안 경험을 물음
    "우리 회사에서 일하며 겪은 가장 큰 어려움은 무엇인가요?",
])
def test_companyQuestionDoesNotAskInsideExperience(text):
    out = question_compose.RagQuestion(question=text, task_count=1)
    assert question_compose.checkGenerated("company", out, "") == "company_asks_inside"


def test_companyMotivationQuestionPasses():
    out = question_compose.RagQuestion(question="어떤 경험이 우리 회사에 지원하는 계기가 되었나요?", task_count=1)
    assert question_compose.checkGenerated("company", out, "") is None


def test_promptAsksNaturalEndingsAndNoInsideExperience():
    prompt = question_compose.ragPrompt("company", "직무: AI", "", [], [], None, "지원 동기")
    assert "는가요" in prompt and "입사 전" in prompt
    assert "이번 질문의 초점: 지원 동기" in prompt and "기술 주제" not in prompt
