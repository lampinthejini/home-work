"""서류 평가 (CONFLICTS C-25): 세 축 점수표·근거 확인·문단 고르기·1차/2차 판정·추가 서류·제출·이의 신청(AI 재평가)."""

import asyncio
import re
from datetime import timedelta

import pytest
from conftest import ADMIN_PASSWORD, APPLICANT_PASSWORD, COVER_LETTER, login, postingBody, publishedPosting, signup

from app.config import SETTING_DEFAULTS
from app.domain import status as st
from app.models import Application, JobPosting, Notification, ResumeScreening
from app.services import llm, question_compose, rag, retention
from app.services import resume_screening as rs
from app.timeutil import now

# 동의 문구 버전은 설정 기본값을 따른다 (버전이 올라가도 이 테스트는 고치지 않아도 되게)
CONSENT = {"consent_version": SETTING_DEFAULTS["consent_version"][0], "items": {"data_collection": True, "ai_decision": True, "share_with_admin": True,
                                                "retention": True, "exam_rules": True}}
RESUME = {"method": "manual", "resume": {
    "name": "김지원",
    "education": [{"school": "한국대학교", "major": "컴퓨터공학", "degree": "학사", "start": "2018-03", "end": "2024-02"}],
    "projects": [{"name": "사내 문서 RAG 챗봇", "period": "2025.03~06", "description": "검색 모듈 담당, LangChain으로 구현",
                  "skills": ["Python", "LangChain"]}],
    "skills": ["Python", "SQL"]}}
CRITERIA = {"weights": {"expertise": 30, "logic": 25, "relevance": 20, "delivery": 10, "culture_fit": 15},
            "coding_enabled": False, "coding_ratio": 30, "pass_score": 70,
            "screening_required_skills": ["Python", "SQL", "PyTorch"], "screening_preferred_skills": ["LangChain"],
            "screening_pass_score": 60, "screening_band": 5}
COVER_EVIDENCE = "불편한 점을 숫자로 모아 검색 화면을 고쳤습니다"
EVIDENCE = {"프로젝트": "검색 모듈 담당, LangChain으로 구현", "학력": "컴퓨터공학 학사"}
COMPANY_GROWTH = [item.label for item in rs.ITEMS if item.axis in ("company", "growth")]
# 자격증 없음 · 기술스택은 코드가 2단계(필수 3개 중 Python·SQL) = 10.7점
HIGH = {"프로젝트": 3, "교육·대회·수상": 3, "학력": 2} | {label: 3 for label in COMPANY_GROWTH}  # 10.7+24+4+2+50 = 90.7
# 10.7 + 16 + 2.7 + 2 + 회사 20 + 성장 6.7 = 58.0 → 합격선 60 ± 5 안이라 2차
BORDER = {"프로젝트": 2, "교육·대회·수상": 2, "학력": 2} | {item.label: 2 if item.axis == "company" else 1
                                                         for item in rs.ITEMS if item.axis in ("company", "growth")}


class FakeModel:
    """항목 이름(프롬프트의 [평가 항목])마다 정해 둔 단계·근거로 답한다. 이의 검토(<이의>)는 appeal 값을 쓴다. 부른 레인을 기록한다."""

    def __init__(self, levels: dict[str, int], byLane: dict[str, dict] | None = None, appeal: dict[str, int] | None = None,
                 appealEvidence: str | None = None):
        self.levels, self.byLane, self.appeal, self.appealEvidence = levels, byLane or {}, appeal or {}, appealEvidence
        self.calls: list[tuple[str, str]] = []
        self.prompts: list[str] = []

    async def structured(self, schema, system, prompt, timeoutSec, maxTokens=400, temperature=0.4, lane="rt"):
        label = re.search(r"\[평가 항목\] (.+)", prompt).group(1).strip()
        self.calls.append((label, lane))
        self.prompts.append(prompt)
        if "<이의>" in prompt:
            evidence = self.appealEvidence or EVIDENCE.get(label, COVER_EVIDENCE)
            return schema(level=self.appeal.get(label, 0), evidence=evidence, reason="이의 검토")
        levels = self.byLane.get(lane, self.levels)
        return schema(level=levels.get(label, 0), evidence=EVIDENCE.get(label, COVER_EVIDENCE), reason="테스트")


def useModel(monkeypatch, model) -> None:
    monkeypatch.setattr(llm, "structured", model.structured)


@pytest.fixture(autouse=True)
def everythingFits(monkeypatch):
    async def fits(system, user, maxTokens, lane="rt"):
        return True
    monkeypatch.setattr(llm, "fits", fits)


# ---------- 점수표 ----------

def test_threeAxesMakeHundredWithoutCareer():
    byAxis = {axis: sum(item.weight for item in rs.ITEMS if item.axis == axis) for axis in rs.AXES}
    assert byAxis == {"job": 50, "company": 30, "growth": 20} and rs.TOTAL_WEIGHT == 100
    assert "career" not in rs.ITEM_BY_KEY  # 경력은 채점하지 않는다 (참고 사항만, 2026-11-18 사용자 결정)
    assert (rs.ITEM_BY_KEY["project"].weight, rs.ITEM_BY_KEY["skills"].weight) == (24, 16)


def test_allTopLevelsMakeHundredAndAllZeroMakeZero():
    assert rs.totalScore({item.key: item.maxLevel for item in rs.ITEMS}) == 100
    assert rs.totalScore({item.key: 0 for item in rs.ITEMS}) == 0  # 기본 점수 없음


@pytest.mark.parametrize(("total", "expected"), [(65, "pass"), (64.9, "second"), (60, "second"), (55, "second"), (54.9, "fail")])
def test_firstDecisionBands(total, expected):
    assert rs.firstDecision(total, 60, 5) == expected


def test_zeroBandMeansNoSecondRound():
    assert rs.firstDecision(60, 60, 0) == "pass" and rs.firstDecision(59.9, 60, 0) == "fail"


def test_secondDecisionUsesPassScoreOnly():
    assert rs.secondDecision(60, 60) == "pass" and rs.secondDecision(59.9, 60) == "fail"


# ---------- 서류 글 ----------

def source(key, resume=None, docs=()):
    return asyncio.run(rs.sourceText(rs.ITEM_BY_KEY[key], resume or RESUME["resume"], rs.DocIndex(list(docs))))


COVER_DOC = {"kind": "cover_letter", "source": "text", "text": COVER_LETTER}
CAREER_RESUME = {**RESUME["resume"], "career": [{"company": "AIIT", "role": "인턴", "start": "2024-07", "end": "2024-12",
                                                  "description": "RAG 검색 기능을 맡아 응답 시간 30% 단축"}]}


def test_educationSourceLeavesOutSchoolName():
    text, _ = source("education")
    assert "컴퓨터공학" in text and "한국대학교" not in text


def test_companyAndGrowthReadResumeExperienceAndDocuments():
    # 인재상·적응 근거는 추가 서류만이 아니라 이력서의 프로젝트·경력(단체 생활 포함)에서도 찾는다 (2026-11-18 사용자 의견)
    text, ground = source("together", CAREER_RESUME, [COVER_DOC])
    assert "검색 모듈 담당" in text and "응답 시간 30% 단축" in text and COVER_LETTER in text
    assert rs.grounded(COVER_EVIDENCE, ground) and rs.grounded("RAG 검색 기능을 맡아", ground)
    assert not rs.grounded("[자기소개서]", ground)  # 서류 이름 표시는 근거가 아니다


def test_careerTextIsEvidenceButNotScored():
    text, _ = source("project", CAREER_RESUME)
    assert "경력: 인턴" in text and "AIIT" not in text  # 회사 이름은 넣지 않는다 (연차·회사로 채점하지 않음)


def test_everyItemSeesSameMaterialButEvidenceComesFromItsOwnParts():
    # AI 에 보여 주는 글은 모든 항목이 같다 (llama.cpp 프롬프트 캐시). 근거로 인정하는 범위만 항목마다 다르다
    shown = {key: source(key, CAREER_RESUME, [COVER_DOC])[0] for key in ("education", "certificate", "project", "measure")}
    assert len(set(shown.values())) == 1
    _, ground = source("education", CAREER_RESUME, [COVER_DOC])
    assert "컴퓨터공학" in ground and COVER_LETTER not in ground and "검색 모듈" not in ground
    assert COVER_LETTER in source("certificate", docs=[COVER_DOC])[1]  # 자격증은 추가 서류에 적은 것도 본다


def test_itemWithNothingToReadIsEmpty():
    assert source("certificate") == ("", "")  # 자격증 칸도 추가 서류도 없음 → LLM 을 부르지 않는다


def test_promptPutsSharedPartFirst():
    first = rs.itemPrompt(rs.ITEM_BY_KEY["project"], "서류", "AI/AX", ["Python"], [])
    second = rs.itemPrompt(rs.ITEM_BY_KEY["measure"], "서류", "AI/AX", ["Python"], [])
    shared = first[: first.index("[평가 항목]")]
    assert second.startswith(shared) and "</서류>" in shared


def test_fairnessRuleIsInEveryPrompt():
    for system in (rs.SYSTEM, rs.APPEAL_SYSTEM):
        assert "군 복무 여부" in system and "개인 특성은 평가하지 않는다" in system


def test_splitChunksKeepsParagraphsUnderSize():
    chunks = rs.splitChunks("가" * 900 + "\n\n짧은 문단\n또 한 줄")
    assert all(len(c) <= rs.CHUNK_CHARS for c in chunks) and len(chunks) == 3
    assert chunks[-1] == "가" * 100 + "\n짧은 문단\n또 한 줄"  # 짧은 문단은 크기 안에서 이어 붙인다


def fakeEmbed(monkeypatch, broken=False):
    calls = []

    async def embed(texts, timeoutSec=10):
        if broken:
            raise rag.EmbedUnavailable("down")
        calls.append(len(texts))
        return [[1.0, 0.0] if "숫자" in t else [0.0, 1.0] for t in texts]
    monkeypatch.setattr(rag, "embed", embed)
    return calls


def test_longDocumentsPickParagraphsCloseToItem(monkeypatch):
    calls = fakeEmbed(monkeypatch)
    filler = "\n\n".join("나" * 390 for _ in range(6))
    doc = {"kind": "portfolio", "source": "pdf", "text": filler + "\n\n가설을 세우고 숫자로 확인해 방향을 바꿨습니다."}
    index = rs.DocIndex([doc])
    assert index.totalChars > rs.DOC_CHARS
    text, ground = asyncio.run(rs.sourceText(rs.ITEM_BY_KEY["measure"], {}, index))
    assert "숫자로 확인해" in text and "[자기소개서]" in text and len(ground) <= rs.DOC_CHARS + 10
    again, _ = asyncio.run(rs.sourceText(rs.ITEM_BY_KEY["learning"], {}, index))
    readers = [item for item in rs.ITEMS if item.readsDocs]
    assert again == text and calls == [7, len(readers)]  # 모든 항목이 같은 문단 묶음 (임베딩은 한 번만)


def test_appealPicksParagraphsWithItsOwnText(monkeypatch):
    fakeEmbed(monkeypatch)
    filler = "\n\n".join("나" * 390 for _ in range(6))
    index = rs.DocIndex([{"kind": "portfolio", "source": "pdf", "text": filler + "\n\n결과를 숫자로 비교했습니다."}])
    text, _ = asyncio.run(rs.sourceText(rs.ITEM_BY_KEY["together"], {}, index, "숫자로 비교한 부분을 봐 주세요"))
    assert "숫자로 비교했습니다" in text


def test_shortDocumentsAreReadWholeWithoutEmbedding(monkeypatch):
    calls = fakeEmbed(monkeypatch)
    assert COVER_LETTER in source("measure", docs=[COVER_DOC])[0] and calls == []


def test_embedDownPausesScreening(monkeypatch):
    fakeEmbed(monkeypatch, broken=True)
    index = rs.DocIndex([{"kind": "other", "source": "pdf", "text": "가" * (rs.DOC_CHARS + 500)}])
    with pytest.raises(rs.ScreeningUnavailable):
        asyncio.run(rs.sourceText(rs.ITEM_BY_KEY["measure"], {}, index))


def test_longMaterialIsTrimmedUntilItFits(monkeypatch):
    async def fitsShort(system, user, maxTokens, lane="rt"):
        return len(user) < 2000
    monkeypatch.setattr(llm, "fits", fitsShort)
    item = rs.ITEM_BY_KEY["learning"]
    material = asyncio.run(rs.fitMaterial(rs.SYSTEM, lambda m: rs.itemPrompt(item, m, "AI/AX", [], []), "가" * 3000))
    assert len(rs.itemPrompt(item, material, "AI/AX", [], [])) < 2000


# ---------- 기술스택 (코드) ----------

def skills(resume, required, preferred=(), docs=""):
    return rs.rateSkills(resume, docs, list(required), list(preferred))


def test_skillsHalfOfRequiredIsLevelTwo():
    row = skills(RESUME["resume"], ["Python", "SQL", "PyTorch"], ["LangChain"])
    assert (row["level"], row["by"], row["points"]) == (2, "code", 10.7)
    assert "Python, SQL" in row["evidence"] and "LangChain" in row["evidence"] and "PyTorch" in row["reason"]


def test_skillsAllRequiredUsedInProjectsIsLevelThree():
    assert skills(RESUME["resume"], ["python", "langchain"])["level"] == 3


def test_skillsUsedInCareerDescriptionCount():
    assert skills({"skills": ["SQL"], "career": [{"description": "SQL 로 통계 화면 작성"}]}, ["SQL"])["level"] == 3


def test_skillsListedButNotUsedInProjectIsLevelTwo():
    assert skills(RESUME["resume"], ["Python", "SQL"])["level"] == 2  # SQL 은 프로젝트에 없음


def test_skillsOnlyPreferredOrFewRequiredIsLevelOne():
    assert skills(RESUME["resume"], ["Java", "Kotlin"], ["SQL"])["level"] == 1
    assert skills(RESUME["resume"], ["Python", "Java", "Kotlin"])["level"] == 1


def test_skillsNothingMatchingIsZeroAndWordBoundaryIsKept():
    assert skills({"skills": ["Google Cloud"], "projects": []}, ["Go"])["level"] == 0


def test_skillsKoreanSpellingCountsAsSameSkill():
    resume = {"skills": ["파이썬", "파이토치"], "projects": [{"description": "파이썬과 파이토치로 분류 모델 학습", "skills": []}]}
    assert skills(resume, ["Python", "PyTorch"])["level"] == 3


def test_skillsCanComeFromDocuments():
    assert skills({"skills": [], "projects": []}, ["PyTorch"], docs="PyTorch 로 이미지 분류 모델을 학습")["level"] == 3


# ---------- 항목 하나 평가 ----------

def rate(key: str, material: str):
    return asyncio.run(rs.rateItem(rs.ITEM_BY_KEY[key], material, material, "AI/AX 엔지니어", ["Python"], [], "rt"))


def test_emptyMaterialIsZeroWithoutCallingLlm(monkeypatch):
    model = FakeModel({"자격증": 3})
    useModel(monkeypatch, model)
    assert rate("certificate", "")["level"] == 0 and model.calls == []


def test_groundedEvidenceKeepsLevel(monkeypatch):
    useModel(monkeypatch, FakeModel({"프로젝트": 2}))
    row = rate("project", "프로젝트: 사내 문서 RAG 챗봇 검색 모듈 담당, LangChain으로 구현")
    assert (row["level"], row["points"], row["grounded"], row["level_text"]) == (2, 16.0, True, "직무 관련, 본인 역할 명시")


def test_storyItemLevelsAreAboutConcretenessNotLength():
    assert rs.ITEM_BY_KEY["together"].levels == rs.STORY_LEVELS
    assert "주장만" in rs.STORY_LEVELS[1] and "구체적인 사례" in rs.STORY_LEVELS[2]
    assert "길다고 단계를 올리지 않는다" in rs.itemPrompt(rs.ITEM_BY_KEY["together"], "글", "AI/AX", [], [])


def test_evidenceNotInDocumentsRetriesOnceThenZero(monkeypatch):
    model = FakeModel({"프로젝트": 3})
    useModel(monkeypatch, model)
    row = rate("project", "프로젝트: 다른 이야기만 적힌 서류")
    assert len(model.calls) == 2 and (row["level"], row["grounded"]) == (0, False) and "3단계" in row["reason"]


def test_levelAboveItemMaximumIsClamped(monkeypatch):
    useModel(monkeypatch, FakeModel({"학력": 3}))
    row = rate("education", "학력: 컴퓨터공학 학사")
    assert (row["level"], row["max_level"], row["points"]) == (2, 2, 2.0)


def test_llmErrorTwiceStopsScreening(monkeypatch):
    async def broken(*args, **kwargs):
        raise llm.LlmError("timeout")
    monkeypatch.setattr(llm, "structured", broken)
    with pytest.raises(rs.ScreeningUnavailable):
        rate("project", "프로젝트: 무엇")


# ---------- 공고 설정 ----------

def test_screeningNeedsRequiredSkills(adminClient):
    res = adminClient.post("/admin/postings", json=postingBody(criteria={**CRITERIA, "screening_required_skills": [" "]}))
    assert res.json()["code"] == "SCREENING_SKILLS"


def test_postingHasNoEssayQuestionsOrToggle(adminClient):
    postingId = adminClient.post("/admin/postings", json=postingBody(criteria=CRITERIA)).json()["posting_id"]
    criteria = adminClient.get(f"/admin/postings/{postingId}").json()["criteria"]
    assert "screening_essays" not in criteria and "screening_enabled" not in criteria
    res = adminClient.post("/admin/postings", json=postingBody(criteria={**CRITERIA, "screening_essays": ["지원 동기"]}))
    assert res.status_code == 422  # 자기소개서 문항은 공고에서 정하지 않는다 (2026-11-18 사용자 결정)


def test_screeningCriteriaLockOnceSomeoneWasScreened(adminClient, monkeypatch):
    client, appId = submitted(adminClient)
    useModel(monkeypatch, FakeModel({}))
    runScreen(appId)
    asAdmin(client)
    postingId = client.get("/admin/postings").json()["items"][0]["posting_id"]
    res = client.patch(f"/admin/postings/{postingId}", json={"criteria": {**CRITERIA, "screening_pass_score": 50}})
    assert res.json()["code"] == "SCREENING_STARTED"
    res = client.patch(f"/admin/postings/{postingId}", json={"criteria": {**CRITERIA, "pass_score": 75}})
    assert res.status_code == 200, res.text  # 서류 평가 칸을 그대로 두면 다른 기준은 지금처럼 바꿀 수 있다


# ---------- 추가 서류 · 제출 ----------

def drafted(adminClient, criteria=None, resume=None):
    postingId = publishedPosting(adminClient, criteria=criteria or CRITERIA)
    adminClient.post("/auth/logout")
    signup(adminClient)
    login(adminClient, "kim@example.com", APPLICANT_PASSWORD)
    appId = adminClient.post("/applications", json={"posting_id": postingId}).json()["application_id"]
    assert adminClient.post(f"/applications/{appId}/consent", json=CONSENT).status_code == 201
    if resume is not False:
        res = adminClient.post(f"/applications/{appId}/resume", json={**RESUME, "resume": resume or RESUME["resume"]})
        assert res.status_code == 200, res.text
    return adminClient, appId


def submitted(adminClient, criteria=None, cover=COVER_LETTER, resume=None):
    client, appId = drafted(adminClient, criteria, resume)
    res = client.post(f"/applications/{appId}/submit", json={"cover_text": cover})
    assert res.status_code == 200, res.text
    return client, appId


def asAdmin(client):
    client.post("/auth/logout")
    login(client, "admin@huge.local", ADMIN_PASSWORD)


def runScreen(appId):
    asyncio.run(rs.screen(appId))


def test_documentsNeedSavedResume(adminClient):
    client, appId = drafted(adminClient, resume=False)
    assert client.get(f"/applications/{appId}").json()["next_step"] == "resume"
    assert client.post(f"/applications/{appId}/submit", json={}).json()["code"] == "RESUME_REQUIRED"


def test_coverTextSavesDraftAndHasLimit(adminClient):
    client, appId = drafted(adminClient)
    assert client.get(f"/applications/{appId}").json()["next_step"] == "documents"
    docs = client.get(f"/applications/{appId}/documents").json()
    assert (docs["cover_text"], docs["files"], docs["max_files"]) == ("", [], rs.MAX_FILES)
    assert client.put(f"/applications/{appId}/documents", json={"cover_text": " 짧게 "}).json()["cover_text"] == "짧게"
    res = client.put(f"/applications/{appId}/documents", json={"cover_text": "가" * (rs.COVER_TEXT_MAX + 1)})
    assert res.json()["code"] == "COVER_TOO_LONG"


def test_submitWithoutAnyDocumentIsAllowed(adminClient, sessionFactory):
    client, appId = submitted(adminClient, cover="")
    assert client.get(f"/applications/{appId}").json()["attempt_status"] == "screening"
    with sessionFactory() as db:
        assert db.get(Application, appId).extra_documents == []


def test_submitStartsScreeningAndCopiesCoverForInterviewQuestions(adminClient, sessionFactory):
    client, appId = submitted(adminClient)
    assert client.get(f"/applications/{appId}").json()["attempt_status"] == "screening"
    card = client.get("/me/applications").json()["items"][0]
    assert card["next_action"] is None and card["screening_decided"] is False
    with sessionFactory() as db:
        app = db.get(Application, appId)
        assert app.extra_documents[0]["text"] == COVER_LETTER
        assert app.resume_snapshot["cover_letter"] == COVER_LETTER  # 면접 질문 만들기가 읽는 자리
    assert client.put(f"/applications/{appId}/documents", json={"cover_text": "a"}).json()["code"] == "RESUME_LOCKED"


# ---------- 판정 ----------

def test_highFirstScorePassesAndStartsQuestions(adminClient, sessionFactory, monkeypatch):
    client, appId = submitted(adminClient)
    useModel(monkeypatch, FakeModel(HIGH))
    composed = []
    monkeypatch.setattr(question_compose, "scheduleCompose", composed.append)
    runScreen(appId)
    with sessionFactory() as db:
        app = db.get(Application, appId)
        row = db.query(ResumeScreening).filter_by(application_id=appId).one()
        assert app.attempt_status == st.READY
        assert (row.decision, row.decided_by, row.stage, float(row.final_total)) == ("pass", "ai", "done", 90.7)
        assert row.second_total is None and row.rounds["timings"]["first_sec"] >= 0
        assert db.query(Notification).filter_by(application_id=appId, kind="screening").count() == 1
    assert composed == [appId]
    card = client.get("/me/applications").json()["items"][0]
    assert card["next_action"] == "precheck" and card["screening_decided"] is True


def test_lowFirstScoreIsRejectedAndApplicantSeesLevelsNotPoints(adminClient, monkeypatch):
    client, appId = submitted(adminClient)
    model = FakeModel({})
    useModel(monkeypatch, model)
    runScreen(appId)
    assert {lane for _, lane in model.calls} == {"rt"}
    body = client.get(f"/applications/{appId}/screening").json()
    view = body["screening"]
    assert body["attempt_status"] == "screen_rejected" and body["can_appeal"] is True and view["decision"] == "fail"
    assert len(view["items"]) == len(rs.ITEMS)
    for key in ("final_total", "pass_score", "rounds", "first_total", "timings"):
        assert key not in view
    for item in view["items"]:
        assert "points" not in item and "weight" not in item and item["level_text"]
    appealable = {i["item"]: i["appealable"] for i in view["items"]}
    assert appealable["skills"] is False and appealable["project"] is True
    assert client.get("/me/applications").json()["items"][0]["next_action"] == "view_screening"


def test_borderlineGoesToSecondRoundAndSecondScoreDecides(adminClient, sessionFactory, monkeypatch):
    _client, appId = submitted(adminClient)
    second = BORDER | {item.label: 2 for item in rs.ITEMS if item.axis == "growth"}  # 2차는 성장 항목을 2단계로 → 64.7
    model = FakeModel(BORDER, byLane={"eval": second})
    useModel(monkeypatch, model)
    runScreen(appId)
    with sessionFactory() as db:
        row = db.query(ResumeScreening).filter_by(application_id=appId).one()
        assert (float(row.first_total), float(row.second_total), float(row.final_total)) == (58.0, 64.7, 64.7)
        assert row.decision == "pass" and db.get(Application, appId).attempt_status == st.READY
    # 기술스택(코드)만 LLM 을 부르지 않는다
    assert [lane for _, lane in model.calls].count("eval") == len(rs.ITEMS) - 1


def test_secondRoundCanReject(adminClient, sessionFactory, monkeypatch):
    _client, appId = submitted(adminClient)
    useModel(monkeypatch, FakeModel(BORDER, byLane={"eval": BORDER | {item.label: 1 for item in rs.ITEMS if item.axis == "company"}}))
    runScreen(appId)
    with sessionFactory() as db:
        row = db.query(ResumeScreening).filter_by(application_id=appId).one()
        assert row.decision == "fail" and float(row.final_total) < 60
        assert db.get(Application, appId).attempt_status == st.SCREEN_REJECTED


def test_aiDownPausesAndRetriesLater(adminClient, sessionFactory, monkeypatch):
    _client, appId = submitted(adminClient)

    async def broken(*args, **kwargs):
        raise llm.LlmError("timeout")
    monkeypatch.setattr(llm, "structured", broken)
    runScreen(appId)
    with sessionFactory() as db:
        row = db.query(ResumeScreening).filter_by(application_id=appId).one()
        assert (row.stage, row.error_count) == ("error", 1)
        assert db.get(Application, appId).attempt_status == st.SCREENING
        started = []
        monkeypatch.setattr(rs, "scheduleScreening", started.append)
        assert rs.resumePending(db) == 0  # 아직 RETRY_SEC 이 안 지남
        row.started_at = now() - timedelta(seconds=rs.RETRY_SEC + 1)
        db.commit()
        assert rs.resumePending(db) == 1 and started == [appId]
    useModel(monkeypatch, FakeModel(HIGH))
    runScreen(appId)
    with sessionFactory() as db:
        assert db.get(Application, appId).attempt_status == st.READY


def test_postingClosedDuringScreeningKeepsClosedStatus(adminClient, sessionFactory, monkeypatch):
    _client, appId = submitted(adminClient)
    with sessionFactory() as db:
        app = db.get(Application, appId)
        app.attempt_status = st.statusOnClose(app.attempt_status)
        db.commit()
    assert st.statusOnClose(st.SCREENING) == st.NOT_TAKEN_CLOSED
    useModel(monkeypatch, FakeModel(HIGH))
    runScreen(appId)  # 서류 평가 중이 아니면 평가하지 않는다
    with sessionFactory() as db:
        assert db.get(Application, appId).attempt_status == st.NOT_TAKEN_CLOSED


# ---------- 이의 신청 ----------

def rejected(adminClient, monkeypatch, resume=None):
    client, appId = submitted(adminClient, resume=resume)
    useModel(monkeypatch, FakeModel({}))
    runScreen(appId)
    return client, appId


ALL_STORY = [{"item": item.key, "text": "자기소개서에 사례가 있습니다."} for item in rs.ITEMS if item.axis in ("company", "growth")]


def appealBody(claims=None):
    return {"claims": (claims or ALL_STORY) + [{"item": "project", "text": "프로젝트 칸에 본인 역할을 적었습니다."}]}


def test_appealGroundedInDocumentsPassesAndStartsQuestions(adminClient, sessionFactory, monkeypatch):
    client, appId = rejected(adminClient, monkeypatch)
    assert client.post(f"/applications/{appId}/screening/appeal", json=appealBody()).status_code == 200
    assert client.post(f"/applications/{appId}/screening/appeal", json=appealBody()).json()["code"] == "APPEAL_DONE"
    model = FakeModel({}, appeal={label: 3 for label in [*COMPANY_GROWTH, "프로젝트"]})
    useModel(monkeypatch, model)
    composed = []
    monkeypatch.setattr(question_compose, "scheduleCompose", composed.append)
    asyncio.run(rs.reviewAppeal(appId))
    assert {lane for _, lane in model.calls} == {"eval"} and all("<이의>" in p for p in model.prompts)
    with sessionFactory() as db:
        row = db.query(ResumeScreening).filter_by(application_id=appId).one()
        assert (row.appeal_status, row.decision, row.decided_by) == ("accepted", "pass", "appeal")
        assert float(row.final_total) == 84.7  # 10.7 + 24 + 30 + 20
        assert db.get(Application, appId).attempt_status == st.READY
    assert composed == [appId]
    view = client.get(f"/applications/{appId}/screening").json()["screening"]
    assert view["appeal"]["status"] == "accepted" and all(i["accepted"] for i in view["appeal"]["items"])
    assert next(i for i in view["items"] if i["item"] == "project")["level"] == 3  # 바뀐 단계로 보여 준다


def test_appealWithEvidenceOnlyInAppealTextIsRejected(adminClient, sessionFactory, monkeypatch):
    client, appId = rejected(adminClient, monkeypatch)
    claims = [{"item": "career", "text": "사실 AIIT 에서 2년 일했습니다."}]
    assert client.post(f"/applications/{appId}/screening/appeal", json={"claims": claims}).json()["code"] == "APPEAL_ITEM"  # 경력은 채점 항목이 아님
    claims = [{"item": "learning", "text": "사실 Rust 를 혼자 배워 서비스에 적용했습니다."}]
    assert client.post(f"/applications/{appId}/screening/appeal", json={"claims": claims}).status_code == 200
    useModel(monkeypatch, FakeModel({}, appeal={"새 기술을 스스로 배워 적용": 3}, appealEvidence="Rust 를 혼자 배워 서비스에 적용했습니다"))
    asyncio.run(rs.reviewAppeal(appId))
    with sessionFactory() as db:
        row = db.query(ResumeScreening).filter_by(application_id=appId).one()
        assert (row.appeal_status, row.decision) == ("rejected", "fail")
        assert row.appeal_result["items"][0]["accepted"] is False and "제출 서류" in row.appeal_result["items"][0]["reason"]
        assert db.get(Application, appId).attempt_status == st.SCREEN_REJECTED
        assert db.query(Notification).filter_by(application_id=appId, kind="screening").count() == 2  # 결과 + 이의 결과
    assert client.get(f"/applications/{appId}/screening").json()["can_appeal"] is False


def test_skillsAreNotAppealableAndClaimsMustBeUnique(adminClient, monkeypatch):
    client, appId = rejected(adminClient, monkeypatch)
    assert client.post(f"/applications/{appId}/screening/appeal",
                       json={"claims": [{"item": "skills", "text": "파이썬"}]}).json()["code"] == "APPEAL_ITEM"
    twice = [{"item": "project", "text": "a"}, {"item": "project", "text": "b"}]
    assert client.post(f"/applications/{appId}/screening/appeal", json={"claims": twice}).json()["code"] == "APPEAL_ITEM"


def test_appealNeedsOpenPosting(adminClient, sessionFactory, monkeypatch):
    client, appId = rejected(adminClient, monkeypatch)
    with sessionFactory() as db:
        posting = db.get(Application, appId).posting
        posting.close_at = now() - timedelta(minutes=1)
        db.commit()
    assert client.post(f"/applications/{appId}/screening/appeal", json=appealBody()).json()["code"] == "POSTING_CLOSED"


def test_appealPassingAfterPostingClosedEndsAsNotTaken(adminClient, sessionFactory, monkeypatch):
    client, appId = rejected(adminClient, monkeypatch)
    client.post(f"/applications/{appId}/screening/appeal", json=appealBody())
    with sessionFactory() as db:
        db.query(JobPosting).update({"status": "closed"})
        db.commit()
    useModel(monkeypatch, FakeModel({}, appeal={label: 3 for label in [*COMPANY_GROWTH, "프로젝트"]}))
    composed = []
    monkeypatch.setattr(question_compose, "scheduleCompose", composed.append)
    asyncio.run(rs.reviewAppeal(appId))
    with sessionFactory() as db:
        assert db.get(Application, appId).attempt_status == st.NOT_TAKEN_CLOSED
    assert composed == []


def test_appealAiDownRetriesLater(adminClient, sessionFactory, monkeypatch):
    client, appId = rejected(adminClient, monkeypatch)
    client.post(f"/applications/{appId}/screening/appeal", json=appealBody())

    async def broken(*args, **kwargs):
        raise llm.LlmError("timeout")
    monkeypatch.setattr(llm, "structured", broken)
    asyncio.run(rs.reviewAppeal(appId))
    with sessionFactory() as db:
        row = db.query(ResumeScreening).filter_by(application_id=appId).one()
        assert row.appeal_status == "error"
        started = []
        monkeypatch.setattr(rs, "scheduleAppeal", started.append)
        assert rs.resumePending(db) == 0
        row.appeal_started_at = now() - timedelta(seconds=rs.RETRY_SEC + 1)
        db.commit()
        assert rs.resumePending(db) == 1 and started == [appId]


def test_adminSeesScoresDocumentsAndCareerReferenceButCannotChangeDecision(adminClient, monkeypatch):
    client, appId = rejected(adminClient, monkeypatch, resume=CAREER_RESUME)
    client.post(f"/applications/{appId}/screening/appeal", json=appealBody())
    assert client.get(f"/admin/applications/{appId}/screening").status_code in (401, 403)
    asAdmin(client)
    body = client.get(f"/admin/applications/{appId}/screening").json()
    view = body["screening"]
    assert view["final_total"] == 10.7 and view["pass_score"] == 60 and set(view["rounds"]) == {"first"}
    assert "first_sec" in view["timings"]
    assert view["appeal"]["status"] == "pending" and len(view["appeal"]["claims"]) == len(ALL_STORY) + 1
    assert body["documents"] == [{"kind": "cover_letter", "source": "text", "name": "자기소개서", "text": COVER_LETTER}]
    assert body["career"][0]["company"] == "AIIT"  # 경력은 점수 없이 참고 사항으로만
    res = client.post(f"/admin/applications/{appId}/screening/decision", json={"decision": "pass", "note": "x"})
    assert res.status_code in (404, 405)  # 관리자 판정 변경 없음 (PRD N2)


def test_rejectedAndScreeningApplicationsArePurgedWithUnscored():
    assert st.SCREENING in retention.UNSCORED_STATUSES and st.SCREEN_REJECTED in retention.UNSCORED_STATUSES
    assert st.SCREEN_REJECTED not in st.FINAL_STATUSES  # 응시 통계·채점 대상이 아니다


# ---------- 추가 서류 PDF ----------

PDF = b"%PDF-1.4 document"


@pytest.fixture()
def fakeFiles(monkeypatch):
    from app.services import resume_extract, storage

    stored: dict[str, bytes] = {}
    monkeypatch.setattr(storage, "putObject", lambda key, data, contentType="": stored.__setitem__(key, data))
    monkeypatch.setattr(storage, "deletePrefix", lambda prefix: sum(1 for k in list(stored) if k.startswith(prefix) and stored.pop(k)))
    pages = {"text": "PyTorch 와 SQL 로 이미지 분류 모델을 학습하고 결과를 배포했습니다."}

    async def readPages(data):
        if "scanPage" in pages:  # 2쪽: 1쪽은 글자, 2쪽은 글자 없는 그림(스캔)
            return [resume_extract.PageText(1, pages["text"], "pymupdf"), resume_extract.PageText(2, "", "none")]
        text = pages["text"]
        images = 1 if "imageText" in pages else 0  # 글자와 큰 그림이 함께 있는 쪽
        return [resume_extract.PageText(1, text, "pymupdf" if text else "none", images=images)]

    async def ocr(data, contentType, pageNos):
        found = pages.get("scanPage") or pages.get("imageText")
        if not found:
            raise resume_extract.OcrError("down")
        return [(resume_extract.PageText(no, found, "ocr"), []) for no in pageNos]
    monkeypatch.setattr(resume_extract, "readPages", readPages)
    monkeypatch.setattr(resume_extract, "ocrPages", ocr)
    return stored, pages


def upload(client, appId, name="포트폴리오.pdf", data=PDF, contentType="application/pdf"):
    return client.post(f"/applications/{appId}/documents/files", files={"file": (name, data, contentType)})


def test_pdfTextIsUsedInScreening(adminClient, sessionFactory, monkeypatch, fakeFiles):
    stored, _pages = fakeFiles
    client, appId = drafted(adminClient)
    res = upload(client, appId)
    assert res.status_code == 200, res.text
    assert res.json()["files"][0]["name"] == "포트폴리오.pdf" and len(stored) == 1
    assert next(iter(stored)).startswith(f"documents/{appId}/")
    client.post(f"/applications/{appId}/submit", json={})
    useModel(monkeypatch, FakeModel({}))
    runScreen(appId)
    with sessionFactory() as db:
        rounds = db.query(ResumeScreening).filter_by(application_id=appId).one().rounds
    skillsRow = next(r for r in rounds["first"] if r["item"] == "skills")
    # 이력서만으로는 2단계(PyTorch 없음). 포트폴리오에 PyTorch·SQL 을 쓴 근거가 있어 필수 3개 모두 + 사용 근거 → 3단계
    assert skillsRow["level"] == 3 and "PyTorch" in skillsRow["evidence"]
    assert upload(client, appId).json()["code"] == "RESUME_LOCKED"


def test_everyPdfIsCoverLetterAndCopiedForInterviewQuestions(adminClient, sessionFactory, fakeFiles):
    client, appId = drafted(adminClient)
    res = upload(client, appId, "프로젝트 기술서.pdf")
    assert res.json()["files"][0]["kind"] == "cover_letter"  # 포트폴리오·기술서도 자기소개서로 본다 (회의 결정)
    client.post(f"/applications/{appId}/submit", json={"cover_text": COVER_LETTER})
    with sessionFactory() as db:
        cover = db.get(Application, appId).resume_snapshot["cover_letter"]
        assert COVER_LETTER in cover and "이미지 분류" in cover  # 글과 PDF 글을 이어 둔다


def test_pageWithoutTextIsReadByOcr(adminClient, sessionFactory, fakeFiles):
    _stored, pages = fakeFiles
    pages["scanPage"] = "스캔한 쪽의 글자"
    client, appId = drafted(adminClient)
    assert upload(client, appId).status_code == 200
    with sessionFactory() as db:
        text = db.get(Application, appId).extra_documents[0]["text"]
    assert text.index("이미지 분류") < text.index("스캔한 쪽의 글자")  # 쪽 순서대로


def test_textInsideImageIsReadByOcrWithoutRepeatingLayerText(adminClient, sessionFactory, fakeFiles):
    _stored, pages = fakeFiles
    # OCR 은 쪽 전체를 읽으므로 글자층 문장도 다시 나온다 → 그림 속 글자 줄만 덧붙인다
    pages["imageText"] = "PyTorch 와 SQL 로 이미지 분류 모델을 학습하고 결과를 배포했습니다.\n화면 캡처: 정확도 81% 달성"
    client, appId = drafted(adminClient)
    assert upload(client, appId).status_code == 200
    with sessionFactory() as db:
        text = db.get(Application, appId).extra_documents[0]["text"]
    assert text.count("이미지 분류 모델") == 1 and text.endswith("화면 캡처: 정확도 81% 달성")


def test_upToThreePdfsAndDelete(adminClient, fakeFiles):
    stored, _pages = fakeFiles
    client, appId = drafted(adminClient)
    for n in range(rs.MAX_FILES):
        assert upload(client, appId, f"{n}.pdf").status_code == 200
    assert upload(client, appId, "x.pdf").json()["code"] == "DOCUMENT_LIMIT"
    client.put(f"/applications/{appId}/documents", json={"cover_text": "글"})  # 자기소개서 글은 PDF 수에 들지 않는다
    files = client.get(f"/applications/{appId}/documents").json()["files"]
    assert len(files) == 3 and len(stored) == 3
    res = client.delete(f"/applications/{appId}/documents/files/{files[0]['id']}")
    assert res.status_code == 200 and len(res.json()["files"]) == 2 and res.json()["cover_text"] == "글" and len(stored) == 2
    assert client.delete(f"/applications/{appId}/documents/files/none").status_code == 404


def test_pdfMustHaveText(adminClient, fakeFiles):
    _stored, pages = fakeFiles
    client, appId = drafted(adminClient)
    assert upload(client, appId, "a.png", data=b"\x89PNG\r\n\x1a\nxxxx", contentType="image/png").json()["code"] == "UNSUPPORTED_FILE"
    pages["text"] = ""  # 글자 없는 쪽뿐이고 OCR 도 안 됨
    assert upload(client, appId, "scan.pdf").json()["code"] == "DOCUMENT_NO_TEXT"
