"""AI 공고 초안 (S-R02): 정해진 값은 그대로 복사, 문장은 AI, 회사명 없이 게시 가능."""

import asyncio
from datetime import timedelta

from conftest import postingBody

from app.services import llm, posting_draft
from app.timeutil import now

DRAFT_REQUEST = {
    "job_code": "AI_AX", "career_level": "experienced", "career_years": 3, "employment_type": "contract",
    "location": "서울 강남구", "headcount": 2, "open_at": (now() - timedelta(hours=1)).isoformat(),
    "close_at": (now() + timedelta(days=10)).isoformat(), "duties": ["LLM 서비스 개발", "RAG·검색"],
    "skills": ["Python", "PyTorch"], "preferred": "사내 AI 도입 경험", "company_intro": "제조 데이터를 다루는 AI 조직",
    "emphasis": "신규 조직", "coding_test": True,
}


def newEmptyDraft(adminClient) -> str:
    res = adminClient.post("/admin/postings", json={})
    assert res.status_code == 201, res.text
    return res.json()["posting_id"]


def test_draftAiCopiesFixedValuesWithoutAi(adminClient, monkeypatch):
    prompts = []
    monkeypatch.setattr(posting_draft, "start", lambda postingId, prompt, **_: prompts.append(prompt))
    postingId = newEmptyDraft(adminClient)
    res = adminClient.post(f"/admin/postings/{postingId}/draft-ai", json=DRAFT_REQUEST)
    assert res.status_code == 202
    p = adminClient.get(f"/admin/postings/{postingId}").json()
    assert (p["employment_type"], p["location"], p["headcount"], p["source"]) == ("contract", "서울 강남구", 2, "ai_draft")
    assert p["criteria"]["coding_enabled"] is True
    assert "경력 3년 이상" in prompts[0] and "LLM 서비스 개발" in prompts[0]
    assert "회사명" not in prompts[0]


def test_draftAiRejectsPreparingJobAndPastClose(adminClient, monkeypatch):
    monkeypatch.setattr(posting_draft, "start", lambda postingId, prompt, **_: None)
    postingId = newEmptyDraft(adminClient)
    assert adminClient.post(f"/admin/postings/{postingId}/draft-ai", json={**DRAFT_REQUEST, "job_code": "BACKEND"}).json()["code"] == "JOB_NOT_OPEN"
    past = {**DRAFT_REQUEST, "close_at": (now() - timedelta(minutes=1)).isoformat()}
    assert adminClient.post(f"/admin/postings/{postingId}/draft-ai", json=past).status_code == 400


def test_generateFillsTextAndFlagsBias(sessionFactory, adminClient, monkeypatch):
    monkeypatch.setattr(posting_draft, "start", lambda postingId, prompt, **_: None)
    postingId = newEmptyDraft(adminClient)
    adminClient.post(f"/admin/postings/{postingId}/draft-ai", json=DRAFT_REQUEST)

    async def fakeStructured(schema, system, user, timeoutSec, maxTokens=400, temperature=0.4):
        return schema(title="AI/AX 엔지니어 (경력 3년 이상)", company_intro="저희 팀은 제조 데이터를 다루는 AI 조직입니다.",
                      duties="- LLM 서비스 개발\n- RAG 검색 개선", requirements="- Python 3년 이상\n- 20~30대 선호", preferred="- 사내 AI 도입 경험")

    monkeypatch.setattr(llm, "structured", fakeStructured)
    asyncio.run(posting_draft.generate(postingId, "prompt"))
    status = adminClient.get(f"/admin/postings/{postingId}/draft-ai/status").json()
    assert status["status"] == "done"
    assert [w["reason"] for w in status["bias_warnings"]] == ["나이 제한"]
    assert adminClient.get(f"/admin/postings/{postingId}").json()["title"] == "AI/AX 엔지니어 (경력 3년 이상)"


def test_generateFailureIsReported(adminClient, monkeypatch):
    monkeypatch.setattr(posting_draft, "start", lambda postingId, prompt, **_: None)
    postingId = newEmptyDraft(adminClient)
    adminClient.post(f"/admin/postings/{postingId}/draft-ai", json=DRAFT_REQUEST)

    async def failing(*args, **kwargs):
        raise llm.LlmError("timeout")

    monkeypatch.setattr(llm, "structured", failing)
    asyncio.run(posting_draft.generate(postingId, "prompt"))
    assert adminClient.get(f"/admin/postings/{postingId}/draft-ai/status").json()["status"] == "failed"


def runWithAiOutput(adminClient, monkeypatch, request: dict, **fields) -> str:
    """AI 가 fields 를 돌려준다고 치고 초안을 만든다. 공고 ID 를 돌려준다."""
    monkeypatch.setattr(posting_draft, "start", lambda postingId, prompt, **_: None)
    postingId = newEmptyDraft(adminClient)
    adminClient.post(f"/admin/postings/{postingId}/draft-ai", json=request)
    output = {"title": "AI/AX 엔지니어 (신입)", "company_intro": "저희 팀은 제조 데이터를 다루는 AI 조직입니다.",
              "duties": "- LLM 서비스 개발\n- RAG 검색 개선", "requirements": "- Python 개발 경험\n- 협업 경험", "preferred": "", **fields}

    async def fakeStructured(schema, *args, **kwargs):
        return schema(**output)

    monkeypatch.setattr(llm, "structured", fakeStructured)
    asyncio.run(posting_draft.generate(postingId, "prompt", introMemo=request["company_intro"]))
    return postingId


def test_shortIntroFallsBackToAdminMemo(adminClient, monkeypatch):
    """작은 모델이 짧은 메모를 그대로 베껴도 실패하지 않는다: 관리자 메모로 채운다 (2026-11-02 사용자 결정 A)."""
    request = {**DRAFT_REQUEST, "company_intro": "AI 회사"}
    postingId = runWithAiOutput(adminClient, monkeypatch, request, company_intro="AI 회사")
    assert adminClient.get(f"/admin/postings/{postingId}/draft-ai/status").json()["status"] == "done"
    assert adminClient.get(f"/admin/postings/{postingId}").json()["company_intro"] == "AI 회사"


def test_emptyIntroFromAiUsesMemo(adminClient, monkeypatch):
    request = {**DRAFT_REQUEST, "company_intro": "작은 AI 팀"}
    postingId = runWithAiOutput(adminClient, monkeypatch, request, company_intro="  ")
    assert adminClient.get(f"/admin/postings/{postingId}").json()["company_intro"] == "작은 AI 팀"


def test_dashOnlyPreferredBecomesEmpty(adminClient, monkeypatch):
    """우대 사항 메모가 없을 때 AI 가 '-' 만 넣으면 빈칸으로 저장한다."""
    postingId = runWithAiOutput(adminClient, monkeypatch, {**DRAFT_REQUEST, "preferred": ""}, preferred="-\n- ")
    assert adminClient.get(f"/admin/postings/{postingId}").json()["preferred"] == ""


def test_promptAsksToExpandIntroWithoutNewFacts():
    """B: 메모의 사실만으로 2~4문장으로 풀어 쓰라고 지시한다."""
    assert "풀어 쓴다" in posting_draft.SYSTEM
    assert "지어내지 않는다" in posting_draft.SYSTEM


def test_publishWithoutCompanyName(adminClient):
    body = postingBody()
    body.pop("company_name")
    postingId = adminClient.post("/admin/postings", json=body).json()["posting_id"]
    assert adminClient.post(f"/admin/postings/{postingId}/publish").status_code == 200


def test_deleteDraftPosting(adminClient):
    postingId = newEmptyDraft(adminClient)
    assert adminClient.delete(f"/admin/postings/{postingId}").status_code == 204
    assert adminClient.get(f"/admin/postings/{postingId}").status_code == 404
