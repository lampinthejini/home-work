"""AI 공고 초안 그래프 (2026-11-10 사용자 결정): 참고 공고 찾기 → 초안 → 칸별 검사 → 문제 칸만 다시 쓰기 → 저장,
그리고 같은 thread 로 이어서 관리자가 고른 칸만 다시 쓰기."""

import asyncio

from conftest import postingBody
from test_posting_draft import DRAFT_REQUEST, newEmptyDraft

from app.models import JobPosting
from app.services import llm, posting_draft

GOOD = {"title": "AI/AX 엔지니어 (경력 3년 이상)", "company_intro": "저희 부서는 제조 데이터를 다루는 AI 조직입니다.",
        "duties": "- LLM 서비스를 개발합니다\n- RAG 검색을 개선합니다", "requirements": "- Python 개발 경험이 있는 분\n- 협업 경험이 있는 분",
        "preferred": "- 사내 AI 도입 경험이 있는 분"}
OLD_DUTIES = "- 사내 문서를 학습한 대화형 검색 서비스를 처음부터 끝까지 직접 설계하고 운영합니다"


class FakeLlm:
    """스키마별로 정해 둔 답을 차례로 돌려준다. 받은 프롬프트를 남긴다."""

    def __init__(self, draft: dict, sections: list[str] | None = None):
        self.draft, self.sections, self.prompts = draft, list(sections or []), []

    async def __call__(self, schema, system, user, timeoutSec, maxTokens=400, temperature=0.4):
        self.prompts.append((schema.__name__, user))
        if schema is posting_draft.DraftText:
            return schema(**self.draft)
        if not self.sections:
            raise llm.LlmError("no answer")
        return schema(text=self.sections.pop(0))


def makeDraft(adminClient, monkeypatch, request=None) -> tuple[str, list]:
    calls = []
    monkeypatch.setattr(posting_draft, "start", lambda postingId, prompt, **kw: calls.append((prompt, kw)))
    postingId = newEmptyDraft(adminClient)
    assert adminClient.post(f"/admin/postings/{postingId}/draft-ai", json=request or DRAFT_REQUEST).status_code == 202
    return postingId, calls[0]


def run(postingId, call, fake, monkeypatch):
    monkeypatch.setattr(llm, "structured", fake)
    prompt, kw = call
    asyncio.run(posting_draft.generate(postingId, prompt, **kw))


def publishedPosting(adminClient, **fields) -> str:
    body = {**postingBody(), **fields}
    postingId = adminClient.post("/admin/postings", json=body).json()["posting_id"]
    assert adminClient.post(f"/admin/postings/{postingId}/publish").status_code == 200
    return postingId


def test_retrieveUsesPastPostingsOfSameJobOnly(sessionFactory, adminClient, monkeypatch):
    """① 같은 직무의 게시·마감 공고만 참고한다. 임시저장·다른 직무·자기 자신은 빼고, 최대 2건."""
    publishedPosting(adminClient, title="예전 공고 가", duties=OLD_DUTIES)
    publishedPosting(adminClient, title="예전 공고 나")
    publishedPosting(adminClient, title="예전 공고 다")
    adminClient.post("/admin/postings", json={**postingBody(), "title": "임시저장 공고"})
    postingId, call = makeDraft(adminClient, monkeypatch)
    fake = FakeLlm(GOOD)
    run(postingId, call, fake, monkeypatch)
    prompt = fake.prompts[0][1]
    assert prompt.count("<참고 ") == posting_draft.REFERENCE_LIMIT == 2
    assert "임시저장 공고" not in prompt and "그대로 옮기지" in prompt
    status = adminClient.get(f"/admin/postings/{postingId}/draft-ai/status").json()
    assert status["status"] == "done" and any("예전 공고 2건" in n for n in status["notes"])


def test_noPastPostingsStillDrafts(adminClient, monkeypatch):
    postingId, call = makeDraft(adminClient, monkeypatch)
    fake = FakeLlm(GOOD)
    run(postingId, call, fake, monkeypatch)
    assert "<참고 " not in fake.prompts[0][1]
    assert adminClient.get(f"/admin/postings/{postingId}").json()["duties"] == GOOD["duties"]


def test_biasedSectionIsRewrittenAlone(adminClient, monkeypatch):
    """③ 차별 표현이 있는 칸만 다시 쓰게 하고, 고친 글을 저장한다. 다른 칸은 그대로."""
    postingId, call = makeDraft(adminClient, monkeypatch)
    fake = FakeLlm({**GOOD, "requirements": "- Python 개발 경험이 있는 분\n- 20~30대 선호"}, ["- Python 개발 경험이 있는 분\n- 협업을 즐기는 분"])
    run(postingId, call, fake, monkeypatch)
    rewrites = [user for name, user in fake.prompts if name == "SectionText"]
    assert len(rewrites) == 1 and "자격 요건" in rewrites[0] and "20~30대" in rewrites[0]
    p = adminClient.get(f"/admin/postings/{postingId}").json()
    assert p["requirements"].endswith("협업을 즐기는 분") and p["duties"] == GOOD["duties"]
    status = adminClient.get(f"/admin/postings/{postingId}/draft-ai/status").json()
    assert status["bias_warnings"] == [] and any("자격 요건" in n for n in status["notes"])


def test_biasLeftAfterRewriteLimitIsWarnedNotBlocked(adminClient, monkeypatch):
    """다시 써도 남으면 지금처럼 막지 않고 알린다. 다시 쓰기는 칸마다 REWRITE_LIMIT 번."""
    postingId, call = makeDraft(adminClient, monkeypatch)
    biased = "- Python 개발 경험이 있는 분\n- 20~30대 선호"
    fake = FakeLlm({**GOOD, "requirements": biased}, [biased, biased, biased])
    run(postingId, call, fake, monkeypatch)
    assert sum(name == "SectionText" for name, _ in fake.prompts) == posting_draft.REWRITE_LIMIT
    status = adminClient.get(f"/admin/postings/{postingId}/draft-ai/status").json()
    assert status["status"] == "done" and [w["reason"] for w in status["bias_warnings"]] == ["나이 제한"]


def test_religionIsFlaggedLikeTheEditor():
    """화면(PostingEditor)과 같은 규칙: 종교도 차별 표현으로 본다 (TC-170)."""
    assert [w["reason"] for w in posting_draft.biasWarnings("- 교회 출석하는 분")] == ["종교"]


def test_copiedReferenceSentenceIsRewritten(adminClient, monkeypatch):
    """예전 공고 문장을 40자 넘게 그대로 옮기면 새 문장으로 다시 쓰게 한다."""
    publishedPosting(adminClient, duties=OLD_DUTIES)
    postingId, call = makeDraft(adminClient, monkeypatch)
    fake = FakeLlm({**GOOD, "duties": OLD_DUTIES + "\n- 모델을 배포합니다"}, ["- 사내 검색 서비스를 만들고 운영합니다\n- 모델을 배포합니다"])
    run(postingId, call, fake, monkeypatch)
    assert adminClient.get(f"/admin/postings/{postingId}").json()["duties"].startswith("- 사내 검색 서비스를")


def test_badRewriteKeepsPreviousText(adminClient, monkeypatch):
    """다시 쓴 글이 너무 짧으면 버리고 앞의 글을 둔다 (나빠지게 고치지 않는다)."""
    postingId, call = makeDraft(adminClient, monkeypatch)
    biased = "- Python 개발 경험이 있는 분\n- 20~30대 선호"
    run(postingId, call, FakeLlm({**GOOD, "requirements": biased}, ["-"]), monkeypatch)
    assert adminClient.get(f"/admin/postings/{postingId}").json()["requirements"] == biased


def test_draftFailsAfterAttempts(adminClient, monkeypatch):
    postingId, call = makeDraft(adminClient, monkeypatch)

    async def failing(*args, **kwargs):
        raise llm.LlmError("timeout")

    monkeypatch.setattr(llm, "structured", failing)
    prompt, kw = call
    asyncio.run(posting_draft.generate(postingId, prompt, **kw))
    status = adminClient.get(f"/admin/postings/{postingId}/draft-ai/status").json()
    assert (status["status"], status["error"]) == ("failed", "timeout")


def reviseRequest(adminClient, monkeypatch, postingId, **body):
    """라우터가 startRevision 에 넘긴 값 그대로 revise 를 돌린다."""
    calls = []
    monkeypatch.setattr(posting_draft, "startRevision", lambda *args: calls.append(args))
    res = adminClient.post(f"/admin/postings/{postingId}/draft-ai/revise", json=body)
    return res, calls


def test_reviseRewritesOnlyRequestedSectionWithSavedContext(sessionFactory, adminClient, monkeypatch):
    """④ 같은 thread 로 이어서: 처음 입력·참고 공고를 다시 쓰고, 관리자 요청과 화면의 지금 글로 그 칸만 다시 쓴다. DB 는 바꾸지 않는다."""
    publishedPosting(adminClient, title="예전 공고 가")
    postingId, call = makeDraft(adminClient, monkeypatch)
    fake = FakeLlm(GOOD, ["- 대규모 언어 모델 서비스를 설계합니다\n- 검색 품질을 측정하고 개선합니다"])
    run(postingId, call, fake, monkeypatch)

    res, calls = reviseRequest(adminClient, monkeypatch, postingId, section="duties", note="검색 품질 측정을 넣어 줘",
                               current="- 관리자가 고친 업무입니다")
    assert res.status_code == 202, res.text
    asyncio.run(posting_draft.revise(*calls[0]))
    prompt = fake.prompts[-1][1]
    assert "검색 품질 측정을 넣어 줘" in prompt and "관리자가 고친 업무" in prompt and "<참고 1>" in prompt and "경력 3년 이상" in prompt
    status = adminClient.get(f"/admin/postings/{postingId}/draft-ai/status").json()
    assert status["revision"] == {"section": "duties", "text": "- 대규모 언어 모델 서비스를 설계합니다\n- 검색 품질을 측정하고 개선합니다"}
    assert adminClient.get(f"/admin/postings/{postingId}").json()["duties"] == GOOD["duties"]


def test_reviseLoopsAgainWhenResultIsBiased(adminClient, monkeypatch):
    """관리자 요청으로 쓴 글도 같은 검사를 거친다. 차별 표현이 나오면 한 번 더 다시 쓴다."""
    postingId, call = makeDraft(adminClient, monkeypatch)
    fake = FakeLlm(GOOD, ["- 남성 우대", "- 야근 없이 일할 수 있는 분"])
    run(postingId, call, fake, monkeypatch)
    _, calls = reviseRequest(adminClient, monkeypatch, postingId, section="preferred", note="근무 환경을 넣어 줘", current=GOOD["preferred"])
    asyncio.run(posting_draft.revise(*calls[0]))
    assert sum(name == "SectionText" for name, _ in fake.prompts) == 2
    assert adminClient.get(f"/admin/postings/{postingId}/draft-ai/status").json()["revision"]["text"] == "- 야근 없이 일할 수 있는 분"


def test_reviseCanBeRepeated(adminClient, monkeypatch):
    postingId, call = makeDraft(adminClient, monkeypatch)
    fake = FakeLlm(GOOD, ["AI/AX 엔지니어 (경력)", "AI/AX 엔지니어 (경력 3년+)"])
    run(postingId, call, fake, monkeypatch)
    for note in ("짧게", "더 짧게"):
        _, calls = reviseRequest(adminClient, monkeypatch, postingId, section="title", note=note, current=GOOD["title"])
        asyncio.run(posting_draft.revise(*calls[0]))
    assert adminClient.get(f"/admin/postings/{postingId}/draft-ai/status").json()["revision"]["text"] == "AI/AX 엔지니어 (경력 3년+)"


def test_reviseFailureKeepsEditorText(adminClient, monkeypatch):
    postingId, call = makeDraft(adminClient, monkeypatch)
    fake = FakeLlm(GOOD, [])
    run(postingId, call, fake, monkeypatch)
    _, calls = reviseRequest(adminClient, monkeypatch, postingId, section="duties", note="더 자세히", current=GOOD["duties"])
    asyncio.run(posting_draft.revise(*calls[0]))
    status = adminClient.get(f"/admin/postings/{postingId}/draft-ai/status").json()
    assert status["status"] == "failed" and status["revision"] is None


def test_reviseNeedsSavedDraftThread(adminClient, monkeypatch):
    """AI 초안 기록이 없으면(직접 작성·초안 실패·게시 후) 다시 쓰기를 받지 않는다."""
    postingId = adminClient.post("/admin/postings", json=postingBody()).json()["posting_id"]
    res, _ = reviseRequest(adminClient, monkeypatch, postingId, section="duties", note="x", current="y")
    assert res.status_code == 404  # AI 초안 공고가 아님

    draftId, call = makeDraft(adminClient, monkeypatch)
    res, _ = reviseRequest(adminClient, monkeypatch, draftId, section="duties", note="x", current="y")
    assert res.json()["code"] == "DRAFT_NOT_REVISABLE"  # 아직 초안을 다 만들지 않음

    run(draftId, call, FakeLlm(GOOD), monkeypatch)
    assert adminClient.patch(f"/admin/postings/{draftId}", json=postingBody()).status_code == 200
    assert adminClient.post(f"/admin/postings/{draftId}/publish").status_code == 200
    res, _ = reviseRequest(adminClient, monkeypatch, draftId, section="duties", note="x", current="y")
    assert res.status_code == 409


def test_reviseValidatesInput(adminClient, monkeypatch):
    postingId, call = makeDraft(adminClient, monkeypatch)
    run(postingId, call, FakeLlm(GOOD), monkeypatch)
    for body in ({"section": "location", "note": "x", "current": ""}, {"section": "duties", "note": "", "current": ""},
                 {"section": "duties", "note": "x" * 301, "current": ""}):
        assert reviseRequest(adminClient, monkeypatch, postingId, **body)[0].status_code == 422


def test_deletePostingRemovesDraftThread(sessionFactory, adminClient, monkeypatch):
    postingId, call = makeDraft(adminClient, monkeypatch)
    run(postingId, call, FakeLlm(GOOD), monkeypatch)
    assert asyncio.run(posting_draft.hasDraft(postingId))
    assert adminClient.delete(f"/admin/postings/{postingId}").status_code == 204
    assert not asyncio.run(posting_draft.hasDraft(postingId))
    with sessionFactory() as db:
        assert db.get(JobPosting, postingId) is None
