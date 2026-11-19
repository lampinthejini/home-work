"""질문 10개 RAG 구성 (TRD 7-4, 사용자 결정 U5): RAG 로 먼저 만들고, 못 만들면 예비 질문 (C-20: 예시도 예비 질문).

임베딩·pgvector·LLM 은 가짜로 바꾼다. 질문 글의 뜻은 '키워드 → 축' 숫자 목록으로 흉내 낸다.
"""

import asyncio
import math
from datetime import timedelta

import pytest

from app.models import Application, InterviewQuestion, JobPosting, Question, User
from app.services import company, llm, question_compose, rag, tech_blog
from app.settings_store import setSetting
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
    def __init__(self, sessionFactory, copyExamples=False, ungrounded=False, embedDown=False, exampleSimilarity=0.8):
        self.sessionFactory = sessionFactory
        self.exampleSimilarity = exampleSimilarity
        self.copyExamples, self.ungrounded, self.embedDown = copyExamples, ungrounded, embedDown
        self.prompts: list[str] = []
        self.keyPointPrompts: list[str] = []
        self.reviewPrompts: list[str] = []
        self.reviewAnswer = None  # 다시 보기 답을 정하는 함수 (없으면 모두 통과)
        self.counter = 0

    async def embed(self, texts, timeoutSec=10):
        if self.embedDown:
            raise rag.EmbedUnavailable("down")
        return [fakeVector(t) for t in texts]

    async def health(self, timeoutSec=3):
        return not self.embedDown

    def similar(self, db, slotKind, vector, count, excludeIds, jobCode=None):
        rows = (db.query(Question).filter(Question.kind == rag.EXAMPLE_KIND[slotKind], Question.source == "reserve")
                .filter(Question.id.notin_(excludeIds or {-1})).order_by(Question.id).limit(count).all())
        return [rag.Example(q.id, q.text, self.exampleSimilarity, fakeVector(q.text)) for q in rows]

    def vectorsFor(self, db, ids):
        return {q.id: fakeVector(q.text) for q in db.query(Question).filter(Question.id.in_(ids))}

    def maxStoredSimilarity(self, db, kind, vector):
        return rag.maxSimilarity(vector, [fakeVector(q.text) for q in db.query(Question).filter(Question.kind == kind)])

    def storeVector(self, db, questionId, vector):
        pass

    async def structured(self, schema, system, user, timeoutSec, maxTokens=400, temperature=0.4, lane="rt"):
        if schema is question_compose.KeyPointsOut:  # 직무 질문 핵심 요소 (M3) — 질문 만들기 호출 수에 넣지 않는다
            self.keyPointPrompts.append(user)
            return schema(points=["핵심 요소 하나", "핵심 요소 둘"])
        if schema is question_compose.QuestionReview:  # 만든 질문 다시 보기 — 질문 만들기 호출 수에 넣지 않는다
            self.reviewPrompts.append(user)
            return self.reviewAnswer(user) if self.reviewAnswer else schema(natural=True, accurate=True)
        assert schema is question_compose.RagQuestion
        self.prompts.append(user)
        self.counter += 1
        marker = "그대로 베끼지 말 것]\n"
        examples = user.split(marker)[1].split("\n\n")[0].splitlines() if marker in user else []
        if self.copyExamples and examples:
            return schema(question=examples[0][2:], task_count=1)
        if "[만들 질문] 이력서 기반" in user:
            evidence = "사내 문서 검색 정확도를 12% 올림" if not self.ungrounded else "추천 시스템을 혼자 만들었음"
            text = ("RAG 챗봇에서 검색 정확도를 올린 방법을 설명해 주세요?" if self.counter % 2
                    else "RAG 챗봇을 만들 때 본인이 맡은 역할은 무엇이었나요?")
            return schema(question=text, evidence=evidence, task_count=1)
        kind = user.split("[만들 질문] ")[1].split(" ")[0]
        # 말끝까지 다르게 (같은 직무 말끝은 same_ending 으로 다시 만든다, 2026-11-18)
        return schema(question=f"{kind} 관점에서 새로 만든 질문은 {self.counter}번째인가요?", task_count=1)


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
        monkeypatch.setattr(company, "relatedProjects", lambda db, vector, count: company.listProjects(db)[:count])
        monkeypatch.setattr(tech_blog, "relatedPosts", lambda db, vector, count, excludeIds=frozenset():
                            [p for p in tech_blog.listPosts(db) if p.id not in excludeIds][:count])

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
                "job": [f"모델 과적합을 막는 방법 {i}은 무엇인가요?" for i in range(8)],
                "resume": ["프로젝트에서 맡은 역할을 설명해 주세요.", "프로젝트에서 어려웠던 점은 무엇인가요?"]}
        for kind, texts in bank.items():
            for i, text in enumerate(texts):
                db.add(Question(source="reserve", kind=kind, text=text, category="기본", duplicate_group=f"{kind}-{i}"))
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


def test_copyingExampleFallsBackToReserve(sessionFactory, world):
    fake = world(copyExamples=True)
    appId = makeApplication(sessionFactory)
    asyncio.run(question_compose.compose(appId))
    rows = composed(sessionFactory, appId)
    job = next(r for r in rows if r.qtype == "job")
    assert (job.source, job.substituted, job.regen_count, job.substitute_reason) == ("reserve", True, 3, "copied_example")
    assert len({r.text for r in rows}) == 10
    # 자리마다 3번까지 다시 만들기. 예시가 3개 미만인 자리는 베낀 예시를 다 빼고 나면 주제만으로 만들어 통과할 수 있다
    # (몇 자리인지는 예비 질문 고르는 순서 — 지원 건 번호 해시 — 에 따라 달라진다)
    assert fake.counter <= 30
    assert all(r.regen_count == 3 for r in rows if r.source == "reserve" and r.substitute_reason == "copied_example")


def test_copiedExampleIsNotShownAgainInRetry(sessionFactory, world):
    """베낀 예시는 그 자리의 다음 시도에서 빼서, 같은 예시를 다시 베끼지 못하게 한다."""
    fake = world(copyExamples=True)
    asyncio.run(question_compose.compose(makeApplication(sessionFactory)))
    jobPrompts = [p for p in fake.prompts if p.startswith("[만들 질문] 직무")][:3]  # 첫 직무 자리의 세 번 시도
    shown = [p.split("그대로 베끼지 말 것]\n")[1].split("\n\n")[0].splitlines() for p in jobPrompts]
    assert len(shown[0]) == 3 and len(shown[1]) == 2 and len(shown[2]) == 1
    assert shown[0][0] not in shown[1] and shown[1][0] not in shown[2]


def test_slotWithExamplesUsedUpIsMadeFromTopic(sessionFactory, world):
    """예시를 다 베껴 빼고 나면 예시 없이 주제만으로 만든다 (예비 질문으로 바로 가지 않는다)."""
    fake = world(copyExamples=True)
    appId = makeApplication(sessionFactory)
    with sessionFactory() as db:
        setSetting(db, "question_regen_limit", 4)  # 예시 3개를 다 베껴 뺀 뒤 한 번 더
    asyncio.run(question_compose.compose(appId))
    job = next(r for r in composed(sessionFactory, appId) if r.qtype == "job")
    assert (job.source, job.regen_count) == ("generated", 3)
    assert any("[비슷한 예비 질문 없음" in p for p in fake.prompts if p.startswith("[만들 질문] 직무"))


def test_startTimeoutKeepsGeneratedAndFillsOnlyTheRest(sessionFactory, world, monkeypatch):
    """TRD 7-4 ⑥: 시작 뒤 기다림이 넘으면 진행 중인 시도를 끊고, 못 만든 자리만 예비 질문. 만든 질문은 버리지 않는다."""
    fake = world()
    original = fake.structured

    async def slowAfterThree(schema, system, user, timeoutSec, maxTokens=400, temperature=0.4, lane="rt"):
        if fake.counter >= 3:
            fake.counter += 1
            await asyncio.sleep(3600)  # 끊지 않으면 끝나지 않는 LLM 호출
        return await original(schema, system, user, timeoutSec, maxTokens, temperature, lane)

    monkeypatch.setattr(llm, "structured", slowAfterThree)
    appId = makeApplication(sessionFactory)

    async def run():
        question_compose.runningTasks[appId] = asyncio.create_task(question_compose.compose(appId))  # conftest 가 scheduleCompose 를 막아 둠
        await asyncio.wait_for(question_compose.ensureComposed(appId, waitSec=0.5), timeout=10)

    asyncio.run(run())
    rows = composed(sessionFactory, appId)
    assert len(rows) == 10
    assert [r.source for r in rows[:3]] == ["generated"] * 3
    assert all(r.source == "reserve" and r.substitute_reason == "budget" for r in rows[3:])
    with sessionFactory() as db:
        assert db.get(Application, appId).questions_status == "ready"
    assert appId not in question_compose.runningTasks and appId not in question_compose.hurryEvents


def test_startTimeoutDuringSlowAudioKeepsSavedQuestions(sessionFactory, world, monkeypatch):
    """질문은 다 만들었는데 음성 만들기가 오래 걸리면, 저장된 질문으로 시작한다 (음성 없는 질문은 자막만, INT-01)."""
    world()

    async def slowAudio(db, app):
        await asyncio.sleep(3600)
    monkeypatch.setattr(question_compose, "synthesizeAll", slowAudio)
    monkeypatch.setattr(question_compose, "HURRY_WAIT_SEC", 0.2)
    appId = makeApplication(sessionFactory)

    async def run():
        question_compose.runningTasks[appId] = asyncio.create_task(question_compose.compose(appId))  # conftest 가 scheduleCompose 를 막아 둠
        await asyncio.sleep(0.3)  # 질문 10개는 이미 저장, 음성 만드는 중
        await asyncio.wait_for(question_compose.ensureComposed(appId, waitSec=0.2), timeout=10)

    asyncio.run(run())
    rows = composed(sessionFactory, appId)
    assert len(rows) == 10 and {r.source for r in rows} == {"generated"}
    with sessionFactory() as db:
        assert db.get(Application, appId).questions_status == "ready"


def test_composeLogsCarryApplicationId(sessionFactory, world, caplog):
    """여러 지원자 질문이 동시에 만들어져도 로그 줄마다 어느 지원 건인지 알 수 있다."""
    world(copyExamples=True)
    appId = makeApplication(sessionFactory)
    with caplog.at_level("INFO", logger="huge.compose"):
        asyncio.run(question_compose.compose(appId))
    lines = [r.getMessage() for r in caplog.records if r.name == "huge.compose"]
    assert lines and all(f"app={appId}" in line for line in lines)
    assert any(line.startswith("compose start") for line in lines)
    done = next(line for line in lines if line.startswith("composed questions"))
    assert "generated=" in done and "reserve=" in done and "sec=" in done


def test_resumeQuestionNotInResumeUsesReserve(sessionFactory, world):
    world(ungrounded=True)
    appId = makeApplication(sessionFactory)
    asyncio.run(question_compose.compose(appId))
    resume = [r for r in composed(sessionFactory, appId) if r.qtype == "resume"]
    assert resume[0].source == "reserve" and resume[0].substitute_reason == "resume_not_grounded"


def test_embedServerDownUsesReserveWithoutLlm(sessionFactory, world):
    fake = world(embedDown=True)
    appId = makeApplication(sessionFactory)
    asyncio.run(question_compose.compose(appId))
    rows = composed(sessionFactory, appId)
    assert fake.counter == 0
    assert {r.source for r in rows} == {"reserve"}
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
        first = db.query(Question).filter_by(kind="personality", source="reserve").order_by(Question.id).first()
        chosen = [{"text": "다른 글", "vector": fakeVector(first.text)}]  # 뜻이 같은 질문을 이미 골랐다
        ctx = {"usedGroups": set(), "usedIds": set()}
        picked = question_compose.bankFallback(db, app, "personality", chosen, ctx)
        assert picked is not None and picked.id != first.id


@pytest.mark.parametrize(("similarity", "lastText", "regenCount"), [
    (0.95, "인성 질문 셋째은 무엇인가요?", 1),  # 면접 안 중복 기준(0.9) 이상 → 다시 만든다
    (0.75, "인성 질문 셋째은 무엇인가요?", 1),  # 같은 종류끼리 0.7 이상도 다시 만든다 (2026-11-18 사용자 결정)
    (0.65, "인성 질문 둘째은 무엇인가요?", 0),  # 0.7 아래는 그대로 쓴다
])
def test_generatedQuestionSimilarToChosenIsRegenerated(sessionFactory, world, monkeypatch, similarity, lastText, regenCount):
    fake = world()
    base = [0.0] * rag.EMBED_DIM
    base[900] = 1.0
    near = [0.0] * rag.EMBED_DIM
    near[900], near[901] = similarity, math.sqrt(1 - similarity ** 2)
    vectors = {"인성 질문 첫째은 무엇인가요?": base, "인성 질문 둘째은 무엇인가요?": near}
    realEmbed, realStructured = fake.embed, fake.structured
    personalityTexts = iter(["인성 질문 첫째은 무엇인가요?", "인성 질문 둘째은 무엇인가요?", "인성 질문 셋째은 무엇인가요?"])

    async def embed(texts, timeoutSec=10):
        return [vectors.get(t) or (await realEmbed([t]))[0] for t in texts]

    async def structured(schema, system, user, timeoutSec, maxTokens=400, temperature=0.4, lane="rt"):
        if user.startswith("[만들 질문] 인성"):
            return schema(question=next(personalityTexts), task_count=1)
        return await realStructured(schema, system, user, timeoutSec, maxTokens, temperature, lane)

    monkeypatch.setattr(rag, "embed", embed)
    monkeypatch.setattr(llm, "structured", structured)
    appId = makeApplication(sessionFactory)
    asyncio.run(question_compose.compose(appId))
    rows = composed(sessionFactory, appId)
    assert len(rows) == 10
    # 인성 2번째 자리(9번). 같은 종류 기준(SAME_KIND_SIMILARITY 0.7)과 면접 안 중복 기준(0.9)을 함께 본다
    assert (rows[-2].text, rows[-2].source, rows[-2].regen_count) == (lastText, "generated", regenCount)


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
        qid = db.query(Question).filter_by(source="reserve").first().id
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


def savedQuestions(sessionFactory) -> list[Question]:
    with sessionFactory() as db:
        return db.query(Question).filter_by(category=question_compose.GENERATED_CATEGORY).order_by(Question.id).all()


def test_generatedQuestionsSavedToReserveExceptResume(sessionFactory, world):
    world()
    appId = makeApplication(sessionFactory)
    asyncio.run(question_compose.compose(appId))
    saved = savedQuestions(sessionFactory)
    assert len(saved) == 8  # 10자리 중 이력서 기반 2개는 넣지 않는다
    assert {q.kind for q in saved} == {"personality", "company", "job"}
    assert all(q.source == "reserve" and q.status == "active" and q.duplicate_group for q in saved)  # 승인 없이 바로 (C-20)
    assert {q.kind: q.job_code for q in saved} == {"personality": None, "company": None, "job": "AI_AX"}  # 직무 질문만 '해당 직무만'
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
    texts = [q.text for q in savedQuestions(sessionFactory)]
    assert len(texts) == len(set(texts))  # 같은 질문은 두 번 넣지 않는다


@pytest.mark.parametrize(("stored", "saved"), [(0.8, False), (0.79, True)])
def test_saveGeneratedSkipsQuestionSimilarToReserve(sessionFactory, world, monkeypatch, stored, saved):
    world()
    monkeypatch.setattr(rag, "maxStoredSimilarity", lambda db, kind, vector: stored)
    appId = makeApplication(sessionFactory)
    text = "우리 회사에서 해 보고 싶은 일은 무엇인가요?"
    with sessionFactory() as db:
        app = db.get(Application, appId)
        question_compose.saveGenerated(db, app, [{"source": "generated", "qtype": "company", "text": text, "vector": fakeVector(text)}])
    assert bool(savedQuestions(sessionFactory)) is saved


def test_personalGeneratedQuestionNotSaved(sessionFactory):
    appId = makeApplication(sessionFactory)
    with sessionFactory() as db:
        app = db.get(Application, appId)
        terms = question_compose.personalTerms(app)
        assert question_compose.isPersonal("RAG 챗봇에서 배운 점을 말해 주세요.", terms, app)
        assert question_compose.isPersonal("김지원 님이 팀에서 맡은 역할은 무엇인가요?", terms, app)
        assert question_compose.isPersonal("사내 문서 검색 정확도를 12% 올린 방법을 설명해 주세요.", terms, app)  # 이력서 문구
        assert not question_compose.isPersonal("데이터 불균형을 다루는 방법을 설명해 주세요.", terms, app)


def test_generatedQuestionUsedAsFallbackRightAway(sessionFactory):
    """예비 질문에 들어간 AI 질문은 승인 없이 대신 낼 질문으로 쓴다 (C-20)."""
    appId = makeApplication(sessionFactory)
    with sessionFactory() as db:
        app = db.get(Application, appId)
        question_compose.saveGenerated(db, app, [{"source": "generated", "qtype": "company", "text": "AIIT에서 해 보고 싶은 일은 무엇인가요?",
                                                  "vector": None}])
        saved = db.query(Question).filter_by(category=question_compose.GENERATED_CATEGORY).one()
        assert saved.id in [c.id for c in question_compose.candidates(db, app, "company", set(), set())]


def test_reserveLimitPerKind(sessionFactory, monkeypatch):
    from app.services import question_bank

    monkeypatch.setattr(question_bank, "RESERVE_LIMIT_PER_KIND", 4)
    appId = makeApplication(sessionFactory)  # 회사 질문 예비 4개 (기본 3 + 예비 1)
    with sessionFactory() as db:
        app = db.get(Application, appId)
        question_compose.saveGenerated(db, app, [{"source": "generated", "qtype": "company", "text": "AIIT의 일하는 방식 중 끌리는 점은 무엇인가요?",
                                                  "vector": None}])
        assert db.query(Question).filter_by(category=question_compose.GENERATED_CATEGORY).count() == 0


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


def test_atMostTwoTasksPerQuestion():
    """TRD 7-4 ④: 요구하는 일 2개 이하 (11-10 의 '한 가지만' 규칙은 2026-11-16 사용자 결정으로 되돌림)."""
    two = question_compose.RagQuestion(question="RAG 에서 청크 크기를 정할 때 무엇을 기준으로 삼고, 왜 그렇게 하나요?", task_count=2)
    assert question_compose.checkGenerated("job", two, "") is None
    three = question_compose.RagQuestion(question="RAG 에서 청크 크기를 정할 때 무엇을 기준으로 삼나요?", task_count=3)
    assert question_compose.checkGenerated("job", three, "") == "too_many_tasks"


def test_retryShowsPreviousQuestionToFix(sessionFactory, world, monkeypatch):
    """실측: 같은 잘못된 질문을 6번 되풀이했다. 다시 만들 때 이전 질문을 보여 주고 고치게 한다."""
    fake = world()
    calls = []

    async def badFirst(schema, system, user, timeoutSec, maxTokens=400, temperature=0.4, lane="rt"):
        calls.append(user)
        if len(calls) == 1:
            return schema(question="협업 중 맡은 역할을 간단히 말씀해 주세요?", task_count=1)
        return await fake.structured(schema, system, user, timeoutSec, maxTokens, temperature, lane)

    monkeypatch.setattr(llm, "structured", badFirst)
    asyncio.run(question_compose.compose(makeApplication(sessionFactory)))
    assert "협업 중 맡은 역할을 간단히 말씀해 주세요?" in calls[1] and "답변 방식 지시" in calls[1]


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


# ---------- 예시 최소 유사도 (2026-11-16 사용자 결정) ----------

def test_closeExamplesDropsFarOnes():
    examples = [rag.Example(1, "가까움", 0.62, []), rag.Example(2, "경계", rag.EXAMPLE_MIN_SIMILARITY, []), rag.Example(3, "멂", 0.47, [])]
    assert [e.id for e in rag.closeExamples(examples)] == [1, 2]


def test_farExamplesAreNotShownAndQuestionIsMadeFromTopic(sessionFactory, world):
    """가장 가까운 예비 질문도 먼 경우: 예시 없이 주제만으로 만든다 (예전에는 AI 를 부르지 않고 바로 예비 질문)."""
    fake = world(exampleSimilarity=0.47)
    appId = makeApplication(sessionFactory)
    asyncio.run(question_compose.compose(appId))
    rows = composed(sessionFactory, appId)
    assert len(rows) == 10 and {r.source for r in rows if r.qtype != "resume"} == {"generated"}
    assert not any(r.substituted for r in rows if r.qtype != "resume")
    jobPrompts = [p for p in fake.prompts if p.startswith("[만들 질문] 직무")]
    assert len(jobPrompts) == 4 and all("[비슷한 예비 질문 없음" in p and "모델 과적합을 막는 방법" not in p for p in jobPrompts)
    assert all("이번 질문의 기술 주제:" in p for p in jobPrompts)  # 무엇을 물을지는 주제가 정한다


def test_jobTopicsSkipHeadingAndAttitudeLines():
    """실측 공고(2026-11-16): '주요 업무:'·'자격 요건:' 제목 줄과 협업·학습 능력 같은 태도 줄이 직무 주제가 됐다."""
    posting = JobPosting(
        duties="\n주요 업무:\n- LLM 기반 서비스를 설계하고 개발합니다.\n[담당 업무]\n- RAG 기반 검색 시스템을 구현합니다.",
        requirements="자격 요건:\n- Python을 활용한 개발 경험을 갖춘 분\n- 문제 해결 능력과 학습 능력을 갖춘 분\n"
                     "- 협업과 소통을 통해 팀과 함께 일할 수 있는 분\n- Git으로 협업한 경험이 있는 분",
        preferred="우대 사항\n- 벡터 DB 운영 경험이 있는 분")
    assert question_compose.jobTopics(posting, {"skills": ["PyTorch", "커뮤니케이션"]}) == [
        "LLM 기반 서비스를 설계하고 개발합니다.", "Python을 활용한 개발", "벡터 DB 운영",
        "RAG 기반 검색 시스템을 구현합니다.", "Git으로 협업한", "PyTorch"]



def test_qualificationTailIsDroppedFromJobTopic():
    """실측 2026-11-18: 'AI 기술에 대한 기본 이해를 가진 분'을 그대로 주제로 주니 "…가진 분께서, …"로 물음 → 기술 내용만 남긴다."""
    assert question_compose.topicCore("AI 기술에 대한 기본 이해를 가진 분") == "AI 기술"
    assert question_compose.topicCore("Python으로 개발 경험을 가진 분") == "Python으로 개발"
    assert question_compose.topicCore("RAG 파이프라인을 구축합니다.") == "RAG 파이프라인을 구축합니다."
    assert question_compose.topicCore("경험을 가진 분") == "경험을 가진 분"  # 다 떼면 빈 글이라 그대로


def test_jobQuestionMayUseCompanyName():
    """2026-11-18 사용자 결정: 내부용이라 직무 질문에 회사 이름·회사 모델 이름이 들어가도 막지 않는다."""
    out = question_compose.RagQuestion(question="AIIT-X 기반 서비스에서 응답 일관성을 지키는 원리는 무엇인가요?", task_count=1)
    assert question_compose.checkGenerated("job", out, "") is None


def test_companySlotsTakeDifferentAngles(sessionFactory, world):
    """실측 2026-11-18: 면접의 회사 질문 2개가 모두 '사용자 중심'으로 쏠림 → 자리마다 지원 동기·회사 이해·조직 문화 중 다른 초점."""
    fake = world()
    appId = makeApplication(sessionFactory)
    asyncio.run(question_compose.compose(appId))
    prompts = [p for p in fake.prompts if p.startswith("[만들 질문] 회사")]
    angles = [a for p in prompts for a in question_compose.COMPANY_ANGLES if f"초점: {a} —" in p]
    assert len(prompts) == 2 and len(angles) == 2 and angles[0] != angles[1]


def test_personalitySlotsTakeDifferentAngles(sessionFactory, world):
    """실측 2026-11-18: 면접의 인성 질문 2개가 모두 '협업 중 의견이 다를 때'로 쏠림 → 자리마다 협업·책임감·성장 중 다른 초점."""
    fake = world()
    appId = makeApplication(sessionFactory)
    asyncio.run(question_compose.compose(appId))
    prompts = [p for p in fake.prompts if p.startswith("[만들 질문] 인성")]
    angles = [a for p in prompts for a in question_compose.PERSONALITY_ANGLES if f"초점: {a} —" in p]
    assert len(prompts) == 2 and len(angles) == 2 and angles[0] != angles[1]


def test_similarCompanyQuestionIsRemade(sessionFactory, world):
    """실측 2026-11-18: 회사 질문 2개가 모두 '사용자 중심 … 하고 싶은 이유는'(유사도 0.75). 말끝은 같아도 되지만 내용이 비슷하면 다시 만든다."""
    fake = world()
    texts = iter(["우리 회사의 문화와 협업, 데이터 활용 방식에서 가장 끌리는 점은 무엇인가요?",
                  "우리 회사의 문화와 협업 방식에서 가장 끌리는 점은 무엇인가요?",  # 앞 질문과 0.79
                  "입사하면 가장 먼저 해 보고 싶은 일은 무엇인가요?"])
    base = fake.structured

    async def structured(schema, system, user, timeoutSec, **kwargs):
        if user.startswith("[만들 질문] 회사"):
            fake.prompts.append(user)
            return schema(question=next(texts), task_count=1)
        return await base(schema, system, user, timeoutSec, **kwargs)
    llm.structured = structured
    appId = makeApplication(sessionFactory)
    asyncio.run(question_compose.compose(appId))
    company = [q for q in composed(sessionFactory, appId) if q.qtype == "company"]
    assert [q.text for q in company] == ["우리 회사의 문화와 협업, 데이터 활용 방식에서 가장 끌리는 점은 무엇인가요?",
                                         "입사하면 가장 먼저 해 보고 싶은 일은 무엇인가요?"]
    assert company[1].regen_count == 1 and not company[1].substituted
    assert any("앞 회사 질문과 내용이 비슷함" in p for p in fake.prompts)


def test_resumeQuestionWithSameEndingAsEarlierIsRejected():
    """실측 2026-11-18: 이력서 질문 2개가 '…Airflow를 활용한 이유는 무엇인가요?' · '…Kubernetes를 활용한 이유는 무엇인가요?'."""
    resume = "프로젝트: 추천 모델 재학습 파이프라인 (2023) 주간 재학습과 A/B 검증을 자동화"
    first = "추천 모델 재학습 파이프라인에서 Airflow를 활용한 이유는 무엇인가요?"
    out = question_compose.RagQuestion(question="추천 모델 재학습 파이프라인에서 Kubernetes를 활용한 이유는 무엇인가요?",
                                       evidence="주간 재학습과 A/B 검증을 자동화", task_count=1)
    anchors = ["재학습 파이프라인"]
    assert question_compose.checkGenerated("resume", out, resume, anchors, [first]) == "same_ending"
    out.question = "추천 모델 재학습 파이프라인에서 A/B 검증을 자동화할 때 가장 어려웠던 점은 무엇이었나요?"
    assert question_compose.checkGenerated("resume", out, resume, anchors, [first]) is None


def test_jobQuestionWithSameEndingAsEarlierIsRejected():
    """실측 2026-11-18: 직무 질문 6개 중 5개가 '…핵심 기준은 무엇인가요?'로 끝남 → 앞 직무 질문과 말끝이 같으면 다시 만든다."""
    earlier = ["RAG 검색에서 정보의 정확성과 관련된 핵심 기준은 무엇인가요?"]
    same = question_compose.RagQuestion(question="모델 경량화 뒤 배포할 때 고려할 중요한 기준은 무엇인가요?", task_count=1)
    assert question_compose.checkGenerated("job", same, "", sameKind=earlier) == "same_ending"
    other = question_compose.RagQuestion(question="모델 경량화에서 양자화와 지식 증류의 차이는 무엇인가요?", task_count=1)
    assert question_compose.checkGenerated("job", other, "", sameKind=earlier) is None


def test_jobSlotsGetDifferentForms():
    """직무 자리마다 꼴 하나를 정해 준다 (꼴 예 여러 개를 한꺼번에 주면 '기준은 무엇인가요'로 쏠림)."""
    prompts = [question_compose.ragPrompt("job", "회사", "", [], [], None, "RAG", jobForm=question_compose.jobFormFor(i))
               for i in range(len(question_compose.JOB_FORMS))]
    assert all(f"이번 질문은 되도록 이 꼴로 쓴다: {form}" in p for form, p in zip(question_compose.JOB_FORMS, prompts, strict=True))
    assert len(set(question_compose.JOB_FORMS)) == len(question_compose.JOB_FORMS) >= 4
    assert not any("기준은 무엇인가요" in form for form in question_compose.JOB_FORMS)


# ---------- 긴 자기소개서: 자리마다 가까운 문단 (2026-11-18 사용자 결정) ----------

FILLER = "학교 수업에서 배운 내용을 정리했습니다. " * 12  # 약 270자, 키워드 없음
TEAM_PARA = "동아리 팀장으로 협업 중 생긴 의견 차이를 회의로 조율해 일정을 지켰습니다."
LONG_COVER = "\n".join([FILLER, FILLER, FILLER, FILLER, TEAM_PARA])


def test_coverIndexPicksClosestParagraphsInOriginalOrder():
    index = question_compose.CoverIndex(LONG_COVER)
    assert len(LONG_COVER) > question_compose.COVER_CHARS and len(index.chunks) >= 3
    index.vectors = [fakeVector(c) for c in index.chunks]
    picked = index.pick(fakeVector("인성 면접 질문. 협업과 의견 조율"))
    assert TEAM_PARA in picked and len(picked) <= question_compose.COVER_CHARS + len(index.chunks)
    assert LONG_COVER[:question_compose.COVER_CHARS] != picked  # 앞 800자만 쓰지 않는다


def test_coverIndexShortTextOrNoVectorsKeepsOldBehaviour():
    assert question_compose.CoverIndex("짧은 자기소개").pick(None) == "짧은 자기소개"
    index = question_compose.CoverIndex(LONG_COVER)  # 임베딩 전(또는 실패) → 앞 COVER_CHARS 자
    assert not index.needsPick and index.pick(fakeVector("협업")) == LONG_COVER[:question_compose.COVER_CHARS]


def test_multilineCoverStaysOneExperienceLine():
    # 줄바꿈이 있는 자기소개서도 '자기소개:' 한 줄 — 둘째 줄부터 경험 줄에서 빠지던 것을 막는다
    text = question_compose.experienceText({"cover_letter": "첫 줄입니다.\n둘째 줄 경험입니다."})
    assert text == "자기소개: 첫 줄입니다. 둘째 줄 경험입니다."


def test_longCoverParagraphReachesPersonalitySlot(sessionFactory, world, monkeypatch):
    # 인성 자리 초점은 지원 id 로 정해져(무작위) 협업 초점이 빠질 수 있다 → 협업 초점으로 고정
    monkeypatch.setattr(question_compose, "PERSONALITY_ANGLES", ("협업과 의견 조율",))
    fake = world()
    appId = makeApplication(sessionFactory)
    with sessionFactory() as db:
        app = db.get(Application, appId)
        app.resume_snapshot = {**RESUME, "cover_letter": LONG_COVER}
        db.commit()
    asyncio.run(question_compose.compose(appId, budgetSec=120))
    teamSlots = [p for p in fake.prompts if "[만들 질문] 인성" in p and "협업과 의견 조율" in p]
    assert teamSlots and all(TEAM_PARA in p for p in teamSlots)  # 뒤쪽 문단인데도 들어간다
    assert all(LONG_COVER[question_compose.COVER_CHARS:] not in p for p in fake.prompts)  # 전체를 넣지는 않는다


def test_resumeEvidenceFromLateCoverParagraphIsGrounded():
    out = question_compose.RagQuestion(
        question="동아리에서 의견 차이를 어떻게 조율하셨나요?", evidence="의견 차이를 회의로 조율해 일정을 지켰습니다", task_count=1)
    ground = question_compose.experienceText({**RESUME, "cover_letter": LONG_COVER}, LONG_COVER)
    assert question_compose.checkGenerated("resume", out, ground, []) in (None, "resume_not_anchored")
    assert question_compose.checkGenerated("resume", out, question_compose.experienceText({**RESUME, "cover_letter": LONG_COVER}), []) \
        == "resume_not_grounded"  # 앞 800자만으로는 근거가 안 보였다


def test_coverEmbeddingTimeIsNotTakenFromComposeBudget(sessionFactory, world, monkeypatch):
    fake = world()
    slowEmbed = fake.embed

    async def embed(texts, timeoutSec=10):
        if len(texts) > 2:  # 자기소개서 문단 임베딩만 느리게 (실측 5,000자 약 10초)
            await asyncio.sleep(4)  # 예산(3초)보다 길다 — 예산에서 뺐다면 모든 자리가 'budget' 이 된다
        return await slowEmbed(texts, timeoutSec)
    monkeypatch.setattr(rag, "embed", embed)
    appId = makeApplication(sessionFactory)
    with sessionFactory() as db:
        db.get(Application, appId).resume_snapshot = {**RESUME, "cover_letter": LONG_COVER}
        db.commit()
    asyncio.run(question_compose.compose(appId, budgetSec=3))  # 전체 시험 실행 중 느려도 남는 여유 (1.2초는 가끔 모자랐음)
    assert not any(q.substitute_reason == "budget" for q in composed(sessionFactory, appId))


def test_jobQuestionsGetKeyPointsForScoring(sessionFactory, world):
    # M3: 직무 질문(만든 것·예비 질문 모두)에 핵심 요소 2~3개를 붙여 저장한다. 다른 종류는 없음
    fake = world()
    appId = makeApplication(sessionFactory)
    asyncio.run(question_compose.compose(appId, budgetSec=120))
    rows = composed(sessionFactory, appId)
    assert [r.key_points for r in rows if r.qtype == "job"] == [["핵심 요소 하나", "핵심 요소 둘"]] * 4
    assert all(r.key_points is None for r in rows if r.qtype != "job")
    assert len(fake.keyPointPrompts) == 4 and all("질문: " in p for p in fake.keyPointPrompts)


def test_keyPointFailureLeavesEmpty(monkeypatch):
    async def broken(*args, **kwargs):
        raise question_compose.llm.LlmError("timeout")
    monkeypatch.setattr(question_compose.llm, "structured", broken)

    class Post:
        title, duties = "AI/AX 엔지니어", "RAG 개발"
    assert asyncio.run(question_compose.keyPointsFor("질문", Post())) == []


# ---------- 2026-11-18 질문 품질: 개인 말 · 분야 · 같은 종류 0.7 · '가장' · 다시 보기 ----------

def test_coverPhraseShorterThanWindowIsPersonal(sessionFactory):
    """실측 2026-11-18: E2E 자기소개서의 '도서관 좌석 예약'(같은 글자 7자)이 예비 질문으로 새어 다른 지원자에게 나갔다."""
    cover = "학교 도서관 좌석 예약이 불편하다는 학생 다섯 명의 이야기를 듣고 Python 으로 예약 알림 챗봇을 만들었습니다."
    appId = makeApplication(sessionFactory)
    with sessionFactory() as db:
        app = db.get(Application, appId)
        app.resume_snapshot = {**RESUME, "cover_letter": cover}
        terms = question_compose.personalTerms(app)
        assert question_compose.isPersonal("도서관 좌석 예약 프로젝트에서 다른 동료들과 의견이 다를 때 어떻게 조율하시나요?", terms, app)
        assert not question_compose.isPersonal("다른 동료들과 의견이 다를 때 어떻게 조율하시나요?", terms, app)
        assert not question_compose.isPersonal("맡은 프로젝트를 끝까지 이끌기 위해 어떤 방식으로 책임을 다하시나요?", terms, app)


def test_jobSkillAlreadyInPostingTopicIsNotRepeated():
    class Posting:
        duties, requirements, preferred = "LLM 기반 서비스 개발", "Python 개발 경험", ""
    topics = question_compose.jobTopics(Posting(), {"skills": ["Python", "PyTorch", "Java"]})
    assert topics == ["LLM 기반 서비스 개발", "Python 개발 경험", "PyTorch", "Java"]


def test_jobPromptNamesArea():
    form = question_compose.JOB_FORMS[1]
    prompt = question_compose.ragPrompt("job", "회사", "", [], [], None, "RAG", jobForm=form)
    assert f"이번 질문의 분야: {question_compose.JOB_AREAS[form]}" in prompt
    assert set(question_compose.JOB_AREAS) == set(question_compose.JOB_FORMS)


def test_topPhraseIsLimitedPerInterview():
    out = question_compose.RagQuestion(question="RAG 챗봇에서 가장 먼저 확인한 것은 무엇인가요?", task_count=1)
    assert question_compose.checkGenerated("personality", out, "", previous=["입사하면 가장 먼저 해 보고 싶은 일은 무엇인가요?"]) == "overused_phrase"
    assert question_compose.checkGenerated("personality", out, "", previous=["팀에서 맡은 역할은 무엇인가요?"]) is None
    other = question_compose.RagQuestion(question="이 직무에서 가장 필요한 태도는 무엇인가요?", task_count=1)
    assert question_compose.checkGenerated("personality", other, "", previous=["가장 큰 배움은?", "가장 끌리는 점은?"]) == "overused_phrase"
    assert question_compose.checkGenerated("personality", other, "", previous=["가장 큰 배움은?"]) is None
    assert "가장" not in question_compose.KIND_FORMS["resume"]


def test_reviewFixesAwkwardSentenceAndRejectsWrongPremise(sessionFactory, world):
    fake = world()

    def answer(user):
        if "교훈" in user.split("[문장]")[0]:
            return question_compose.QuestionReview(natural=False, fixed="팀 프로젝트에서 실패를 겪었을 때 어떻게 대처하셨고, 무엇을 배우셨나요?",
                                                   accurate=True, reason="앞뒤가 이어지지 않음")
        if "생성 시스템" in user.split("[문장]")[0]:
            return question_compose.QuestionReview(natural=True, accurate=False, reason="비교할 수 없는 두 개념")
        return question_compose.QuestionReview(natural=True, accurate=True, key_points=["정확한 용어 하나", "정확한 용어 둘"])
    fake.reviewAnswer = answer
    personality = iter(["팀 프로젝트에서 실패를 겪은 경험 중 가장 큰 교훈을 얻었을 때 어떻게 대처하시나요?"])
    job = iter(["LLM 서비스에서 추론 시스템과 생성 시스템의 차이는 무엇인가요?"])
    base = fake.structured

    async def structured(schema, system, user, timeoutSec, **kwargs):
        if schema is question_compose.RagQuestion and user.startswith("[만들 질문] 인성"):
            text = next(personality, None)
            if text:
                return schema(question=text, task_count=1)
        if schema is question_compose.RagQuestion and user.startswith("[만들 질문] 직무"):
            text = next(job, None)
            if text:
                return schema(question=text, task_count=1)
        return await base(schema, system, user, timeoutSec, **kwargs)
    llm.structured = structured
    appId = makeApplication(sessionFactory)
    asyncio.run(question_compose.compose(appId))
    rows = composed(sessionFactory, appId)
    assert rows[0].text == "팀 프로젝트에서 실패를 겪었을 때 어떻게 대처하셨고, 무엇을 배우셨나요?" and rows[0].regen_count == 0
    jobs = [r for r in rows if r.qtype == "job"]
    assert "생성 시스템" not in jobs[0].text and jobs[0].regen_count == 1  # 전제가 틀린 질문은 다시 만든다
    assert all(r.key_points == ["정확한 용어 하나", "정확한 용어 둘"] for r in jobs)  # 다시 보기의 핵심 요소를 쓴다
    assert fake.keyPointPrompts == []  # 따로 핵심 요소를 묻지 않는다


def test_reviewKeyPointsEchoingInstructionsOrForeignScriptAreDropped():
    review = question_compose.QuestionReview
    assert question_compose.reviewedPoints(review(natural=True, accurate=True, key_points=["인덱스 사용", "쿼리 최적화"])) == ["인덱스 사용", "쿼리 최적화"]
    echo = review(natural=True, accurate=True, key_points=["답변의 타당성은 전제와 물음이 일관성 있게 연결되어야 함"])
    assert question_compose.reviewedPoints(echo) == []  # 실측 2026-11-18
    assert question_compose.reviewedPoints(review(natural=True, accurate=True, key_points=["异步 요청 처리", "HTTP 검증"])) == []


@pytest.mark.parametrize(("text", "repeated"), [
    ("E2E 테스트 자동화를 설계할 때 Python으로 테스트 케이스를 실행하는 순서를 결정할 때 어떤 기준을 사용하시나요?", True),
    ("Python에서 데이터 처리 과정에서 오류가 생기는 원인은 무엇인가요?", True),
    ("사내 문서 RAG 챗봇 프로젝트에서 표를 문장으로 전처리한 이유는 무엇인가요?", False),
    ("배포할 때 장애 때문에 되돌린 적이 있나요?", False),
])
def test_repeatedConnectiveIsDetected(text, repeated):
    """실측 2026-11-19: 한 문장에 '~할 때'·'~에서'가 두 번."""
    assert question_compose.repeatedConnective(text) is repeated


def test_sameEndingAndRepeatedConnectivePassOnLastTry():
    """말끝이 같거나 연결 말이 겹치는 것은 큰 흠이 아니라, 마지막 시도에서는 받는다 (2026-11-19 사용자 결정)."""
    earlier = ["RAG 검색에서 정보의 정확성과 관련된 핵심 기준은 무엇인가요?"]
    same = question_compose.RagQuestion(question="모델 경량화 뒤 배포할 때 고려할 중요한 기준은 무엇인가요?", task_count=1)
    assert question_compose.checkGenerated("job", same, "", sameKind=earlier) == "same_ending"
    assert question_compose.checkGenerated("job", same, "", sameKind=earlier, lastTry=True) is None
    doubled = question_compose.RagQuestion(question="Python에서 데이터 처리 과정에서 오류가 생기는 원인은 무엇인가요?", task_count=1)
    assert question_compose.checkGenerated("job", doubled, "") == "repeated_connective"
    assert question_compose.checkGenerated("job", doubled, "", lastTry=True) is None


def test_bankFallbackPrefersReserveNotSimilarToSameKind(sessionFactory, world, monkeypatch):
    """실측 2026-11-19: 회사 질문을 예비 질문으로 바꿨더니 앞 회사 질문과 거의 같은 질문이 들어감 → 같은 종류와 0.7 이상이면 다른 예비 질문."""
    world()
    appId = makeApplication(sessionFactory)
    with sessionFactory() as db:
        app = db.get(Application, appId)
        pool = question_compose.candidates(db, app, "company", set(), set())
        first, second = pool[0], pool[1]
        near = [1.0, 0.0]
        monkeypatch.setattr(rag, "vectorsFor", lambda _db, ids: {i: ([0.75, math.sqrt(1 - 0.75 ** 2)] if i == first.id else [0.0, 1.0]) for i in ids})
        chosen = [{"text": "앞 회사 질문", "qtype": "company", "vector": near}]
        ctx = {"usedGroups": set(), "usedIds": set()}
        assert question_compose.bankFallback(db, app, "company", chosen, ctx).id == second.id
        # 모두 비슷하면 그래도 하나는 쓴다 (중복 0.9 아래)
        monkeypatch.setattr(rag, "vectorsFor", lambda _db, ids: {i: [0.75, math.sqrt(1 - 0.75 ** 2)] for i in ids})
        assert question_compose.bankFallback(db, app, "company", chosen, ctx).id == first.id
