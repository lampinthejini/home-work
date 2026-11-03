"""AI 공고 초안 (S-R02): 정해진 값은 그대로 복사, 문장은 AI, 회사명 없이 게시 가능."""

import asyncio
from datetime import timedelta

from conftest import postingBody

from app.models import Notification, User
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
    """AI 가 fields 를 돌려준다고 치고 초안을 만든다. 라우터가 start 에 넘긴 값 그대로 generate 를 돌린다. 공고 ID 를 돌려준다."""
    calls = []
    monkeypatch.setattr(posting_draft, "start", lambda postingId, prompt, **kw: calls.append((prompt, kw)))
    postingId = newEmptyDraft(adminClient)
    assert adminClient.post(f"/admin/postings/{postingId}/draft-ai", json=request).status_code == 202
    output = {"title": "AI/AX 엔지니어 (신입)", "company_intro": "저희 부서는 제조 데이터를 다루는 AI 조직입니다.",
              "duties": "- LLM 서비스 개발\n- RAG 검색 개선", "requirements": "- Python 개발 경험\n- 협업 경험", "preferred": "", **fields}

    async def fakeStructured(schema, *args, **kwargs):
        return schema(**output)

    monkeypatch.setattr(llm, "structured", fakeStructured)
    prompt, kw = calls[0]
    asyncio.run(posting_draft.generate(postingId, prompt, **kw))
    return postingId


def test_shortIntroFallsBackToDutyBasedIntro(adminClient, monkeypatch):
    """AI 가 부서 소개를 짧게 쓰면 메모를 그대로 내보내지 않고, 맡을 일로 만든 소개를 넣는다 (2026-11-02 사용자 결정)."""
    request = {**DRAFT_REQUEST, "company_intro": "AI 회사"}
    postingId = runWithAiOutput(adminClient, monkeypatch, request, company_intro="AI 회사")
    assert adminClient.get(f"/admin/postings/{postingId}/draft-ai/status").json()["status"] == "done"
    intro = adminClient.get(f"/admin/postings/{postingId}").json()["company_intro"]
    assert intro != "AI 회사"
    assert posting_draft.DUTY_PHRASES["LLM 서비스 개발"] in intro and posting_draft.DUTY_PHRASES["RAG·검색"] in intro


def test_emptyIntroFromAiUsesDutyBasedIntro(adminClient, monkeypatch):
    postingId = runWithAiOutput(adminClient, monkeypatch, DRAFT_REQUEST, company_intro="  ")
    assert posting_draft.DUTY_PHRASES["LLM 서비스 개발"] in adminClient.get(f"/admin/postings/{postingId}").json()["company_intro"]


def test_departmentMemoIsOptional(adminClient, monkeypatch):
    """부서 소개 메모는 비워도 된다. 비우면 프롬프트에 (없음)으로 알린다."""
    postingId = runWithAiOutput(adminClient, monkeypatch, {**DRAFT_REQUEST, "company_intro": ""})
    assert adminClient.get(f"/admin/postings/{postingId}/draft-ai/status").json()["status"] == "done"


def test_dashOnlyPreferredBecomesEmpty(adminClient, monkeypatch):
    """우대 사항 메모가 없을 때 AI 가 '-' 만 넣으면 빈칸으로 저장한다."""
    postingId = runWithAiOutput(adminClient, monkeypatch, {**DRAFT_REQUEST, "preferred": ""}, preferred="-\n- ")
    assert adminClient.get(f"/admin/postings/{postingId}").json()["preferred"] == ""


def test_promptWritesDepartmentIntroFromDuties():
    """부서 소개: 메모가 부족하면 맡을 일·기술로 풀어 쓰되, 없는 사실(수치·회사명 등)은 지어내지 않는다."""
    assert "부서 소개" in posting_draft.SYSTEM and "회사·팀 소개" not in posting_draft.SYSTEM
    assert "주로 맡을 일" in posting_draft.SYSTEM
    assert "지어내지 않는다" in posting_draft.SYSTEM
    assert "부서 소개 메모: (없음)" in posting_draft.buildPrompt(_body(company_intro=""), "AI/AX 엔지니어")


def test_promptFixesSentenceEndingsAndKeepsAbbreviations():
    """끝맺음은 칸마다 하나로 정하고, 약어는 틀리게 풀어 쓰지 않도록 그대로 둔다 (2026-11-03 사용자 결정)."""
    assert "'~습니다'" in posting_draft.SYSTEM and "'~합니다'" in posting_draft.SYSTEM and "'~ 분'" in posting_draft.SYSTEM
    assert "약어" in posting_draft.SYSTEM and "풀어 쓰지 않고" in posting_draft.SYSTEM


def test_promptKeepsPreferredMemo():
    """우대 사항 메모를 주면 AI 가 비우지 않게 한다. 옛 문구('없으면 빈 문자열')로는 실측 6번 모두 비었다 (2026-11-03)."""
    assert "우대 사항 메모가 있으면 반드시 그 내용을 살려" in posting_draft.SYSTEM
    assert "(없음)일 때만" in posting_draft.SYSTEM
    assert "(없음)일 때만" in posting_draft.DraftText.model_fields["preferred"].description


def test_requirementLinesAreUnifiedToBun():
    """4B 모델이 자격 요건·우대 사항을 '~있습니다'로 쓰는 경우가 있어 (실측 30개 중 4개) 마지막에 '~ 분'으로 맞춘다."""
    text = "\n".join([
        "- Python을 활용한 개발 경험을 가지고 있습니다.", "- 문제 해결 능력을 갖추고 있습니다",
        "- 실험적 사고를 갖춘 경력자입니다.", "- 협업할 수 있는 분", "- 영어 문서를 읽을 수 있음", "- 기술력이 있어야 합니다.",
    ])
    assert posting_draft.unifyBunLines(text) == "\n".join([
        "- Python을 활용한 개발 경험을 가지고 있는 분", "- 문제 해결 능력을 갖추고 있는 분",
        "- 실험적 사고를 갖춘 경력자인 분", "- 협업할 수 있는 분", "- 영어 문서를 읽을 수 있음", "- 기술력이 있는 분",
    ])
    assert posting_draft.unifyBunLines("") == ""


def test_fillGapsUnifiesRequirementsAndPreferred():
    draft = posting_draft.DraftText(title="AI/AX 엔지니어", company_intro="저희 부서는 LLM 서비스를 만듭니다.", duties="- 개발합니다",
                                    requirements="- 개발 경험이 있습니다.", preferred="- 논문 구현 경험이 있습니다")
    filled = posting_draft.fillGaps(draft, "대체")
    assert (filled.requirements, filled.preferred) == ("- 개발 경험이 있는 분", "- 논문 구현 경험이 있는 분")


def test_fallbackIntroTemplatesAllUseDutiesAndSkills():
    """대체 문구는 여러 개 중 하나를 쓴다. 어느 것이든 관리자가 고른 맡을 일·기술만 쓰고 메모는 옮기지 않는다."""
    assert len(posting_draft.INTRO_TEMPLATES) >= 3
    body = _body(company_intro="AI 회사")
    for template in posting_draft.INTRO_TEMPLATES:
        text = posting_draft.fallbackIntro(body, "AI/AX 엔지니어", template)
        assert posting_draft.DUTY_PHRASES["LLM 서비스 개발"] in text and "Python" in text and "AI 회사" not in text


def test_fallbackIntroUsesPresetPhrasesForEveryDutyChip():
    """화면의 맡을 일 칩 7개는 미리 정한 문구로 바꿔 넣는다. 문구가 '업무'로 끝나 '업무 업무'가 되지 않게 기본 문구도 '~ 등을'로 맺는다."""
    chips = ["LLM 서비스 개발", "RAG·검색", "모델 파인튜닝", "MLOps", "데이터 파이프라인", "컴퓨터 비전", "업무 자동화(AX)"]
    assert set(chips) <= set(posting_draft.DUTY_PHRASES)
    for template in posting_draft.INTRO_TEMPLATES:
        text = posting_draft.fallbackIntro(_body(duties=["업무 자동화(AX)"], skills=[]), "AI/AX 엔지니어", template)
        assert posting_draft.DUTY_PHRASES["업무 자동화(AX)"] in text
        assert "업무 업무" not in text and ")  " not in text and "  " not in text


def test_fallbackIntroKeepsCustomDutyAsTyped():
    text = posting_draft.fallbackIntro(_body(duties=["사내 챗봇 운영"], skills=[]), "AI/AX 엔지니어", posting_draft.INTRO_TEMPLATES[0])
    assert "사내 챗봇 운영 등을" in text


def test_fallbackIntroTidiesSentenceLikeCustomDuty():
    """직접 입력을 문장처럼 써도 대체 문구에는 '사내 챗봇 운영' 같은 짧은 말로 다듬어 넣는다 (2026-11-03 사용자 요청)."""
    cases = {
        "사내 챗봇을 운영함": "사내 챗봇 운영",
        "사내 챗봇을 운영합니다.": "사내 챗봇 운영",
        "고객 문의를 분석한다": "고객 문의 분석",
        "모델 배포하기": "모델 배포",
        "고객 문의 분석 업무": "고객 문의 분석 업무",
        "Agent workflow design": "Agent workflow design",
        "RAG를 개선함": "RAG 개선",
        "서비스를 운영": "서비스 운영",
        "모델 결함": "모델 결함",
        "버그·결함 분석": "버그·결함 분석",
        "버그·결함": "버그·결함",
        "데이터 포함": "데이터 포함",
    }
    for typed, tidy in cases.items():
        assert posting_draft.tidyDuty(typed) == tidy, typed


def test_blankDutiesAreAllowedAndAiPicksThem(adminClient, monkeypatch):
    """맡을 일은 비워도 된다 (2026-11-03 사용자 결정). 공백 항목은 지우고, 비면 AI 가 직무·기술에 맞게 정하도록 알린다."""
    assert _body(duties=["  ", " RAG·검색 ", "RAG·검색"]).duties == ["RAG·검색"]
    prompts = []
    monkeypatch.setattr(posting_draft, "start", lambda postingId, prompt, **_: prompts.append(prompt))
    for duties in (["   "], []):
        postingId = newEmptyDraft(adminClient)
        res = adminClient.post(f"/admin/postings/{postingId}/draft-ai", json={**DRAFT_REQUEST, "duties": duties})
        assert res.status_code == 202, res.text
    assert all("주로 맡을 일: (지정 없음)" in prompt for prompt in prompts)
    assert "지정 없음" in posting_draft.SYSTEM and "다듬" in posting_draft.SYSTEM


def test_fallbackIntroWithoutDutiesStillReadsNaturally():
    assert len(posting_draft.NO_DUTY_INTRO_TEMPLATES) >= 3
    for template in posting_draft.NO_DUTY_INTRO_TEMPLATES:
        text = posting_draft.fallbackIntro(_body(duties=[], skills=["Python"]), "AI/AX 엔지니어", template)
        assert "AI/AX 엔지니어" in text and "Python" in text
        assert "  " not in text and " 등을" not in text and "{" not in text
    assert posting_draft.fallbackIntro(_body(duties=[], skills=[]), "AI/AX 엔지니어") .endswith(".")


def _body(**overrides):
    from app.schemas import DraftAiRequest
    return DraftAiRequest(**{**DRAFT_REQUEST, **overrides})


def test_publishWithoutCompanyName(adminClient):
    body = postingBody()
    body.pop("company_name")
    postingId = adminClient.post("/admin/postings", json=body).json()["posting_id"]
    assert adminClient.post(f"/admin/postings/{postingId}/publish").status_code == 200


def test_deleteDraftPosting(adminClient):
    postingId = newEmptyDraft(adminClient)
    assert adminClient.delete(f"/admin/postings/{postingId}").status_code == 204
    assert adminClient.get(f"/admin/postings/{postingId}").status_code == 404


def test_deletePostingRemovesItsNotifications(sessionFactory, adminClient):
    """지운 공고를 가리키는 알림(마감 임박 등)은 같이 지운다. 남기면 눌렀을 때 없는 공고로 간다."""
    postingId = newEmptyDraft(adminClient)
    otherId = newEmptyDraft(adminClient)
    with sessionFactory() as db:
        adminId = db.query(User).filter_by(role="admin").first().id
        db.add(Notification(user_id=adminId, kind="posting_closing", title="내일 마감", link=f"/admin/applicants?posting={postingId}"))
        db.add(Notification(user_id=adminId, kind="posting_closing", title="다른 공고", link=f"/admin/applicants?posting={otherId}"))
        db.commit()
    assert adminClient.delete(f"/admin/postings/{postingId}").status_code == 204
    with sessionFactory() as db:
        assert [n.title for n in db.query(Notification).all()] == ["다른 공고"]
