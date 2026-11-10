"""질문 적용 범위와 공고 기반 질문 후보 (2026-11-10 사용자 결정, CONFLICTS C-17).

- 회사 질문은 그 공고에서만(posting_id), 직무 질문은 같은 직무에서만(job_code), 인성 질문은 공통(둘 다 비움).
- 공고를 게시하면 그 공고로 직무·회사 질문 후보를 만들어 '검토 대기'로 넣는다. 관리자가 승인해야 쓴다.
"""

import asyncio
import json
from datetime import timedelta

from app.models import Application, AuditLog, JobPosting, Question, User
from app.services import llm, posting_questions, question_compose, rag
from app.timeutil import now
from tests.test_question_rag import RESUME, fakeVector


def addPosting(db, title="AI/AX 엔지니어 (신입)", jobCode="AI_AX") -> JobPosting:
    posting = JobPosting(status="published", title=title, job_code=jobCode, close_at=now() + timedelta(days=3),
                         company_intro="LLM과 RAG 기반의 검색 및 추천 서비스를 만드는 팀입니다.",
                         duties="- LLM 기반 서비스를 설계하고 개발합니다.\n- RAG 기반 검색 시스템을 구현합니다.",
                         requirements="- Python을 활용한 개발 경험을 갖춘 분", preferred="", contact_email="recruit@example.com")
    db.add(posting)
    db.flush()
    return posting


def addQuestion(db, kind, text, postingId=None, jobCode=None, status="active", source="generated") -> Question:
    q = Question(source=source, kind=kind, category="AI 생성", text=text, status=status, duplicate_group=text[:128],
                 posting_id=postingId, job_code=jobCode)
    db.add(q)
    db.flush()
    return q


def test_bankCandidatesRespectScope(sessionFactory):
    with sessionFactory() as db:
        mine, other = addPosting(db), addPosting(db, title="백엔드 개발자", jobCode="BACKEND")
        user = User(email="kim@example.com", password_hash="x", name="김지원", role="applicant")
        db.add(user)
        db.flush()
        app = Application(user_id=user.id, posting_id=mine.id, attempt_status="ready", resume_snapshot=RESUME)
        db.add(app)
        own = addQuestion(db, "company", "우리 회사의 검색 서비스에 관심을 갖게 된 계기는 무엇인가요?", postingId=mine.id)
        foreign = addQuestion(db, "company", "우리 회사의 결제 서비스에 관심을 갖게 된 계기는 무엇인가요?", postingId=other.id)
        common = addQuestion(db, "company", "입사 후 이루고 싶은 목표는 무엇인가요?")
        sameJob = addQuestion(db, "job", "리랭킹이 필요한 이유는 무엇인가요?", jobCode="AI_AX")
        otherJob = addQuestion(db, "job", "트랜잭션 격리 수준의 차이는 무엇인가요?", jobCode="BACKEND")
        db.commit()
        company = {q.id for q in question_compose.candidates(db, app, "company", set(), set())}
        job = {q.id for q in question_compose.candidates(db, app, "job", set(), set())}
    assert own.id in company and common.id in company and foreign.id not in company
    assert sameJob.id in job and otherJob.id not in job


def test_savedPendingQuestionsGetScope(sessionFactory, monkeypatch):
    """면접 때 AI 가 만든 질문을 검토 대기로 넣을 때도 범위를 붙인다 (실측: 다른 공고의 회사 질문이 범위 없이 active 였다)."""
    monkeypatch.setattr(rag, "supported", lambda db: False)
    with sessionFactory() as db:
        posting = addPosting(db)
        user = User(email="kim@example.com", password_hash="x", name="김지원", role="applicant")
        db.add(user)
        db.flush()
        app = Application(user_id=user.id, posting_id=posting.id, attempt_status="ready", resume_snapshot={})
        db.add(app)
        db.commit()
        chosen = [{"source": "generated", "qtype": kind, "text": text, "vector": None} for kind, text in (
            ("company", "우리 회사의 검색 서비스에서 가장 해 보고 싶은 일은 무엇인가요?"),
            ("job", "청크 크기는 무엇을 기준으로 정하나요?"),
            ("personality", "의견이 다른 팀원을 어떻게 설득하셨나요?"))]
        question_compose.savePending(db, app, chosen)
        saved = {q.kind: q for q in db.query(Question).filter_by(status="pending")}
    assert (saved["company"].posting_id, saved["company"].job_code) == (posting.id, None)
    assert (saved["job"].posting_id, saved["job"].job_code) == (None, "AI_AX")
    assert (saved["personality"].posting_id, saved["personality"].job_code) == (None, None)


class FakePostingLlm:
    def __init__(self, bad=False):
        self.prompts, self.bad, self.count = [], bad, 0

    async def structured(self, schema, system, user, timeoutSec, maxTokens=400, temperature=0.4, lane="rt"):
        self.prompts.append(user)
        self.count += 1
        if self.bad:
            return schema(question="역할을 했고, 그 이유는 무엇인가요?", task_count=1)  # 여러 개 묻기 → 버린다
        kind = user.split("[만들 질문] ")[1].split(" ")[0]
        topic = user.split("이번 질문의 기술 주제: ")[1][:6] if "기술 주제" in user else "회사"
        return schema(question=f"{kind} {topic} 질문 {self.count}번은 무엇인가요?", task_count=1)


def withFakes(sessionFactory, monkeypatch, fake):
    monkeypatch.setattr(posting_questions, "SessionLocal", sessionFactory)
    monkeypatch.setattr(llm, "structured", fake.structured)
    monkeypatch.setattr(rag, "supported", lambda db: True)

    async def embed(texts, timeoutSec=10):
        return [fakeVector(t) for t in texts]
    monkeypatch.setattr(rag, "embed", embed)
    monkeypatch.setattr(rag, "similar", lambda db, kind, vector, count, ex: [])
    monkeypatch.setattr(rag, "maxStoredSimilarity", lambda db, kind, vector: 0.0)
    monkeypatch.setattr(rag, "storeVector", lambda db, questionId, vector: None)


def test_publishGeneratesScopedPendingCandidates(sessionFactory, monkeypatch):
    fake = FakePostingLlm()
    withFakes(sessionFactory, monkeypatch, fake)
    with sessionFactory() as db:
        postingId = addPosting(db).id
        db.commit()
    result = asyncio.run(posting_questions.generateForPosting(postingId))
    with sessionFactory() as db:
        rows = db.query(Question).filter_by(status="pending").all()
        audit = db.query(AuditLog).filter_by(action="question.posting_candidates").one()
    job = [q for q in rows if q.kind == "job"]
    company = [q for q in rows if q.kind == "company"]
    assert len(job) == 3 and len(company) == posting_questions.COMPANY_COUNT  # 업무 2줄 + 자격 1줄 = 주제 3개
    assert all(q.job_code == "AI_AX" and q.posting_id is None for q in job)
    assert all(q.posting_id == postingId and q.job_code is None for q in company)
    assert all(q.source == "generated" and q.category == posting_questions.CATEGORY for q in rows)
    assert result == {"saved": len(rows), "skipped": 0} and audit.detail["saved"] == len(rows)
    assert "<이력서>\n(없음)" in fake.prompts[0]  # 공고만 보고 만든다 (지원자 정보 없음)


def test_badOrDuplicateCandidatesAreNotSaved(sessionFactory, monkeypatch):
    withFakes(sessionFactory, monkeypatch, FakePostingLlm(bad=True))
    with sessionFactory() as db:
        postingId = addPosting(db).id
        db.commit()
    assert asyncio.run(posting_questions.generateForPosting(postingId))["saved"] == 0
    withFakes(sessionFactory, monkeypatch, FakePostingLlm())
    monkeypatch.setattr(rag, "maxStoredSimilarity", lambda db, kind, vector: 0.85)  # 질문은행과 겹침(0.8 이상)
    assert asyncio.run(posting_questions.generateForPosting(postingId))["saved"] == 0


def test_generationFailureNeverRaises(sessionFactory, monkeypatch):
    async def down(*args, **kwargs):
        raise llm.LlmError("down")
    withFakes(sessionFactory, monkeypatch, FakePostingLlm())
    monkeypatch.setattr(llm, "structured", down)
    with sessionFactory() as db:
        postingId = addPosting(db).id
        db.commit()
    assert asyncio.run(posting_questions.generateForPosting(postingId))["saved"] == 0


def test_publishSchedulesCandidates(adminClient, sessionFactory, monkeypatch):
    from tests.conftest import publishedPosting
    scheduled = []
    monkeypatch.setattr(posting_questions, "schedule", scheduled.append)
    postingId = publishedPosting(adminClient)
    assert scheduled == [postingId]


def test_adminListShowsScopeAndCategory(adminClient, sessionFactory):
    with sessionFactory() as db:
        posting = addPosting(db)
        addQuestion(db, "company", "우리 회사의 검색 서비스에 관심을 갖게 된 계기는 무엇인가요?", postingId=posting.id, status="pending")
        addQuestion(db, "job", "리랭킹이 필요한 이유는 무엇인가요?", jobCode="AI_AX", status="pending")
        db.commit()
    items = {i["kind"]: i for i in adminClient.get("/admin/questions").json()["items"]}
    assert items["company"]["scope"] == {"type": "posting", "posting_id": posting.id, "label": "AI/AX 엔지니어 (신입)"}
    assert items["job"]["scope"] == {"type": "job", "job_code": "AI_AX", "label": "AI/AX 엔지니어"}
    assert items["job"]["category"] == "AI 생성"


def test_loadWebCandidates(sessionFactory, tmp_path, monkeypatch):
    """인터넷 참고 후보 파일: 질문은행과 겹치지 않는 것만 검토 대기로 넣는다. 두 번 돌려도 다시 넣지 않는다."""
    monkeypatch.setattr(rag, "supported", lambda db: False)
    path = tmp_path / "web.json"
    path.write_text(json.dumps({"questions": [
        {"kind": "job", "topic": "RAG", "source": "kalyanks-rag", "text": "리랭킹이 필요한 이유는 무엇인가요?", "check": {"verdict": "new"}},
        {"kind": "company", "topic": "동기", "source": "posting", "text": "우리 회사의 검색 서비스에 관심을 갖게 된 계기는 무엇인가요?",
         "check": {"verdict": "new"}},
        {"kind": "personality", "topic": "피드백", "source": "haijob", "text": "피드백을 받고 바꾼 점을 말씀해 주세요.", "check": {"verdict": "new"}},
        {"kind": "job", "topic": "ML", "source": "minova", "text": "배깅과 부스팅의 차이는 무엇인가요?", "check": {"verdict": "bank_duplicate"}},
    ]}, ensure_ascii=False), encoding="utf-8")
    with sessionFactory() as db:
        posting = addPosting(db)
        db.commit()
        assert posting_questions.loadWebCandidates(db, str(path), posting.id) == 3
        assert posting_questions.loadWebCandidates(db, str(path), posting.id) == 0
        rows = {q.kind: q for q in db.query(Question).filter_by(status="pending")}
    assert rows["job"].job_code == "AI_AX" and rows["job"].posting_id is None
    assert rows["company"].posting_id == posting.id
    assert rows["personality"].posting_id is None and rows["personality"].job_code is None
    assert all(q.category == posting_questions.WEB_CATEGORY for q in rows.values())
