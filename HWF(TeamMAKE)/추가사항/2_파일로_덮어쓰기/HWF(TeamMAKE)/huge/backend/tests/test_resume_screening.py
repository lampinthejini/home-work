"""서류 평가 (CONFLICTS C-24): 점수 계산·근거 확인·1차/2차 판정·상태 전이·이의 신청."""

import asyncio
import re
from datetime import timedelta

import pytest
from conftest import ADMIN_PASSWORD, APPLICANT_PASSWORD, login, postingBody, publishedPosting, signup

from app.config import SETTING_DEFAULTS
from app.domain import status as st
from app.models import Application, Notification, ResumeScreening
from app.services import llm, question_compose, retention
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
    "skills": ["Python", "SQL"],
    "cover_letter": "AI 부트캠프 6개월 수료 후 팀 프로젝트를 진행했습니다."}}
SCREENING_CRITERIA = {"weights": {"expertise": 30, "logic": 25, "relevance": 20, "delivery": 10, "culture_fit": 15},
                      "coding_enabled": False, "coding_ratio": 30, "pass_score": 70,
                      "screening_enabled": True, "screening_required_skills": ["Python", "SQL", "PyTorch"],
                      "screening_preferred_skills": ["LangChain"], "screening_pass_score": 75, "screening_band": 5}
# 예시 지원자 (시각 자료와 같은 값): 프로젝트 2 · 기술 2 · 경력 0 · 경험 2 · 자격증 0 · 학력 2 → 79.3
SAMPLE_LEVELS = {"프로젝트": 2, "기술스택": 2, "경력": 0, "경험": 2, "자격증": 0, "학력": 2}
# 경력·자격증 칸이 없는 이력서라 나머지를 최고 단계로. 기술스택은 코드가 2단계(필수 3개 중 2개): 60 + 12 + 6.7 + 4 + 2 = 84.7
HIGH_LEVELS = {"프로젝트": 3, "경험": 3, "학력": 2}
EVIDENCE = {"프로젝트": "검색 모듈 담당, LangChain으로 구현", "기술스택": "Python, SQL", "경험": "AI 부트캠프 6개월 수료",
            "학력": "컴퓨터공학 학사"}


class FakeModel:
    """항목 이름(프롬프트의 [평가 항목])마다 정해 둔 단계·근거로 답한다. 부른 레인을 기록한다."""

    def __init__(self, levels: dict[str, int], evidence: dict[str, str] | None = None, byLane: dict[str, dict] | None = None):
        self.levels, self.evidence, self.byLane = levels, evidence or EVIDENCE, byLane or {}
        self.calls: list[tuple[str, str]] = []

    async def structured(self, schema, system, prompt, timeoutSec, maxTokens=400, temperature=0.4, lane="rt"):
        label = re.search(r"\[평가 항목\] (\S+)", prompt).group(1)
        self.calls.append((label, lane))
        levels = self.byLane.get(lane, self.levels)
        return schema(level=levels.get(label, 0), evidence=self.evidence.get(label, ""), reason="테스트")


def useModel(monkeypatch, model) -> None:
    monkeypatch.setattr(llm, "structured", model.structured)


# ---------- 점수와 판정 ----------

def test_sampleApplicantScoresAsInTheProposal():
    levels = {rs.ITEMS[i].key: lv for i, lv in enumerate([2, 2, 0, 2, 0, 2])}
    assert rs.totalScore(levels) == 79.3


def test_allTopLevelsMakeHundredAndAllZeroMakeBase():
    assert rs.totalScore({item.key: item.maxLevel for item in rs.ITEMS}) == 100
    assert rs.totalScore({item.key: 0 for item in rs.ITEMS}) == rs.BASE_SCORE


@pytest.mark.parametrize(("total", "expected"), [(80, "pass"), (79.9, "second"), (75, "second"), (70, "second"), (69.9, "fail")])
def test_firstDecisionBands(total, expected):
    assert rs.firstDecision(total, 75, 5) == expected


def test_zeroBandMeansNoSecondRound():
    assert rs.firstDecision(75, 75, 0) == "pass"
    assert rs.firstDecision(74.9, 75, 0) == "fail"


def test_secondDecisionUsesPassScoreOnly():
    assert rs.secondDecision(75, 75) == "pass"
    assert rs.secondDecision(74.9, 75) == "fail"


def test_educationSourceLeavesOutSchoolName():
    text = rs.sourceText(rs.ITEM_BY_KEY["education"], RESUME["resume"])
    assert "컴퓨터공학" in text and "한국대학교" not in text


def test_portfolioIsUsedOnlyForProjectSkillsAndExperience():
    resume = RESUME["resume"]
    for key in ("project", "skills", "experience"):
        assert "포트폴리오: 챗봇 화면" in rs.sourceText(rs.ITEM_BY_KEY[key], resume, "챗봇 화면")
    for key in ("career", "certificate", "education"):
        assert "포트폴리오" not in rs.sourceText(rs.ITEM_BY_KEY[key], resume, "챗봇 화면")


# ---------- 기술스택 (코드) ----------

def skills(resume, required, preferred=(), portfolio=""):
    return rs.rateSkills(resume, portfolio, list(required), list(preferred))


def test_skillsHalfOfRequiredIsLevelTwo():
    row = skills(RESUME["resume"], ["Python", "SQL", "PyTorch"], ["LangChain"])
    assert (row["level"], row["by"]) == (2, "code")
    assert "Python, SQL" in row["evidence"] and "LangChain" in row["evidence"] and "PyTorch" in row["reason"]


def test_skillsAllRequiredUsedInProjectsIsLevelThree():
    assert skills(RESUME["resume"], ["python", "langchain"])["level"] == 3


def test_skillsListedButNotUsedInProjectIsLevelTwo():
    assert skills(RESUME["resume"], ["Python", "SQL"])["level"] == 2  # SQL 은 프로젝트에 없음


def test_skillsOnlyPreferredOrFewRequiredIsLevelOne():
    assert skills(RESUME["resume"], ["Java", "Kotlin"], ["SQL"])["level"] == 1
    assert skills(RESUME["resume"], ["Python", "Java", "Kotlin"])["level"] == 1


def test_skillsNothingMatchingIsZeroAndWordBoundaryIsKept():
    resume = {"skills": ["Google Cloud"], "projects": []}
    assert skills(resume, ["Go"])["level"] == 0


def test_skillsCanComeFromPortfolio():
    assert skills({"skills": [], "projects": []}, ["PyTorch"], portfolio="PyTorch 로 이미지 분류 모델을 학습")["level"] == 3


# ---------- 항목 하나 평가 ----------

def rate(key: str, material: str):
    return asyncio.run(rs.rateItem(rs.ITEM_BY_KEY[key], material, "AI/AX 엔지니어", ["Python"], [], "rt"))


def test_emptyMaterialIsZeroWithoutCallingLlm(monkeypatch):
    model = FakeModel({"경력": 3})
    useModel(monkeypatch, model)
    row = rate("career", "")
    assert row["level"] == 0 and model.calls == []


def test_groundedEvidenceKeepsLevel(monkeypatch):
    useModel(monkeypatch, FakeModel({"프로젝트": 2}))
    row = rate("project", "프로젝트: 사내 문서 RAG 챗봇 검색 모듈 담당, LangChain으로 구현")
    assert (row["level"], row["points"], row["grounded"]) == (2, 8.0, True)


def test_evidenceNotInDocumentsRetriesOnceThenZero(monkeypatch):
    model = FakeModel({"프로젝트": 3}, evidence={"프로젝트": "대규모 트래픽 서비스를 혼자 배포함"})
    useModel(monkeypatch, model)
    row = rate("project", "프로젝트: 사내 문서 RAG 챗봇 검색 모듈 담당")
    assert len(model.calls) == 2
    assert (row["level"], row["grounded"]) == (0, False)
    assert "3단계" in row["reason"]


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


# ---------- 지원 흐름 ----------

def screeningApplicant(adminClient, criteria=None):
    postingId = publishedPosting(adminClient, criteria=criteria or SCREENING_CRITERIA)
    adminClient.post("/auth/logout")
    signup(adminClient)
    login(adminClient, "kim@example.com", APPLICANT_PASSWORD)
    appId = adminClient.post("/applications", json={"posting_id": postingId}).json()["application_id"]
    assert adminClient.post(f"/applications/{appId}/consent", json=CONSENT).status_code == 201
    res = adminClient.post(f"/applications/{appId}/resume", json=RESUME)
    assert res.status_code == 200, res.text
    return adminClient, appId


def runScreen(appId):
    asyncio.run(rs.screen(appId))


def test_submitOnScreeningPostingWaitsForScreening(adminClient):
    client, appId = screeningApplicant(adminClient)
    assert client.get(f"/applications/{appId}").json()["attempt_status"] == "screening"
    assert client.get(f"/applications/{appId}").json()["posting"]["has_screening"] is True
    card = client.get("/me/applications").json()["items"][0]
    assert card["next_action"] is None and card["screening_decided"] is False


def test_postingWithoutScreeningIsUnchanged(adminClient):
    criteria = {**SCREENING_CRITERIA, "screening_enabled": False}
    client, appId = screeningApplicant(adminClient, criteria)
    assert client.get(f"/applications/{appId}").json()["attempt_status"] == "ready"


def test_screeningNeedsRequiredSkills(adminClient):
    res = adminClient.post("/admin/postings", json=postingBody(criteria={**SCREENING_CRITERIA, "screening_required_skills": [" "]}))
    assert res.json()["code"] == "SCREENING_SKILLS"


def test_criteriaViewShowsScreeningSettings(adminClient):
    postingId = adminClient.post("/admin/postings", json=postingBody(criteria=SCREENING_CRITERIA)).json()["posting_id"]
    criteria = adminClient.get(f"/admin/postings/{postingId}").json()["criteria"]
    assert criteria["screening_enabled"] is True
    assert criteria["screening_required_skills"] == ["Python", "SQL", "PyTorch"]


def test_highFirstScorePassesAndStartsQuestions(adminClient, sessionFactory, monkeypatch):
    client, appId = screeningApplicant(adminClient)
    useModel(monkeypatch, FakeModel(HIGH_LEVELS))
    composed = []
    monkeypatch.setattr(question_compose, "scheduleCompose", composed.append)
    runScreen(appId)
    with sessionFactory() as db:
        app = db.get(Application, appId)
        row = db.query(ResumeScreening).filter_by(application_id=appId).one()
        assert app.attempt_status == st.READY
        assert (row.decision, row.decided_by, row.stage, float(row.final_total)) == ("pass", "ai", "done", 84.7)
        assert row.second_total is None
        assert db.query(Notification).filter_by(application_id=appId, kind="screening").count() == 1
    assert composed == [appId]
    card = client.get("/me/applications").json()["items"][0]
    assert card["next_action"] == "precheck" and card["screening_decided"] is True  # 합격자도 서류 결과 링크


def test_lowFirstScoreIsRejectedWithoutSecondRound(adminClient, sessionFactory, monkeypatch):
    client, appId = screeningApplicant(adminClient)
    model = FakeModel({})
    useModel(monkeypatch, model)
    runScreen(appId)
    assert {lane for _, lane in model.calls} == {"rt"}
    view = client.get(f"/applications/{appId}/screening").json()
    assert view["attempt_status"] == "screen_rejected"
    assert view["screening"]["decision"] == "fail" and view["screening"]["final_total"] == 66.7  # 기술스택 2단계(코드)만
    assert client.get("/me/applications").json()["items"][0]["next_action"] == "view_screening"
    assert "rounds" not in view["screening"]  # 지원자에게는 최종 판정에 쓴 결과만


def test_borderlineGoesToSecondRoundAndSecondScoreDecides(adminClient, sessionFactory, monkeypatch):
    client, appId = screeningApplicant(adminClient)
    # 1차 79.3 (2차 구간) → 2차는 경험을 1단계로 봐서 78.0 → 합격선 75 이상이라 합격
    model = FakeModel(SAMPLE_LEVELS, byLane={"eval": {**SAMPLE_LEVELS, "경험": 1}})
    useModel(monkeypatch, model)
    runScreen(appId)
    with sessionFactory() as db:
        row = db.query(ResumeScreening).filter_by(application_id=appId).one()
        assert (float(row.first_total), float(row.second_total), float(row.final_total)) == (79.3, 78.0, 78.0)
        assert row.decision == "pass"
        assert db.get(Application, appId).attempt_status == st.READY
    assert [lane for _, lane in model.calls].count("eval") == 3  # 경력·자격증은 서류에 없고 기술스택은 코드가 정해 LLM 을 부르지 않는다
    assert client.get(f"/applications/{appId}/screening").json()["screening"]["used_round"] == "second"


def test_secondRoundCanReject(adminClient, sessionFactory, monkeypatch):
    _client, appId = screeningApplicant(adminClient)
    useModel(monkeypatch, FakeModel(SAMPLE_LEVELS, byLane={"eval": {**SAMPLE_LEVELS, "프로젝트": 1, "경험": 0}}))
    runScreen(appId)
    with sessionFactory() as db:
        row = db.query(ResumeScreening).filter_by(application_id=appId).one()
        assert row.decision == "fail" and float(row.final_total) < 75
        assert db.get(Application, appId).attempt_status == st.SCREEN_REJECTED


def test_aiDownPausesAndRetriesLater(adminClient, sessionFactory, monkeypatch):
    _client, appId = screeningApplicant(adminClient)

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
    useModel(monkeypatch, FakeModel(HIGH_LEVELS))
    runScreen(appId)
    with sessionFactory() as db:
        assert db.get(Application, appId).attempt_status == st.READY


def test_postingClosedDuringScreeningKeepsClosedStatus(adminClient, sessionFactory, monkeypatch):
    _client, appId = screeningApplicant(adminClient)
    with sessionFactory() as db:
        app = db.get(Application, appId)
        app.attempt_status = st.statusOnClose(app.attempt_status)
        db.commit()
    assert st.statusOnClose(st.SCREENING) == st.NOT_TAKEN_CLOSED
    useModel(monkeypatch, FakeModel({**SAMPLE_LEVELS, "경력": 3}))
    runScreen(appId)  # 서류 평가 중이 아니면 평가하지 않는다
    with sessionFactory() as db:
        assert db.get(Application, appId).attempt_status == st.NOT_TAKEN_CLOSED


def test_appealNotifiesAdminsAndAdminCanPass(adminClient, sessionFactory, monkeypatch):
    client, appId = screeningApplicant(adminClient)
    useModel(monkeypatch, FakeModel({}))
    runScreen(appId)
    res = client.post(f"/applications/{appId}/screening/appeal", json={"text": "포트폴리오에 경력이 있습니다."})
    assert res.status_code == 200, res.text
    assert client.post(f"/applications/{appId}/screening/appeal", json={"text": "다시"}).json()["code"] == "APPEAL_DONE"
    client.post("/auth/logout")
    login(client, "admin@huge.local", ADMIN_PASSWORD)
    view = client.get(f"/admin/applications/{appId}/screening").json()["screening"]
    assert view["appeal_text"] == "포트폴리오에 경력이 있습니다." and set(view["rounds"]) == {"first"}
    composed = []
    monkeypatch.setattr(question_compose, "scheduleCompose", composed.append)
    res = client.post(f"/admin/applications/{appId}/screening/decision", json={"decision": "pass", "note": "경력 확인"})
    assert res.status_code == 200, res.text
    assert res.json()["attempt_status"] == "ready" and res.json()["screening"]["decided_by"] == "admin"
    assert composed == [appId]
    with sessionFactory() as db:
        assert db.query(Notification).filter_by(kind="screening_appeal").count() == 1


def test_applicantCannotSeeAdminScreening(adminClient, monkeypatch):
    client, appId = screeningApplicant(adminClient)
    useModel(monkeypatch, FakeModel({}))
    runScreen(appId)
    assert client.get(f"/admin/applications/{appId}/screening").status_code in (401, 403)


def test_rejectedAndScreeningApplicationsArePurgedWithUnscored():
    assert st.SCREENING in retention.UNSCORED_STATUSES and st.SCREEN_REJECTED in retention.UNSCORED_STATUSES
    assert st.SCREEN_REJECTED not in st.FINAL_STATUSES  # 응시 통계·채점 대상이 아니다


def test_screeningCriteriaLockOnceSomeoneWasScreened(adminClient, monkeypatch):
    client, appId = screeningApplicant(adminClient)
    useModel(monkeypatch, FakeModel({}))
    runScreen(appId)
    client.post("/auth/logout")
    login(client, "admin@huge.local", ADMIN_PASSWORD)
    postingId = client.get("/admin/postings").json()["items"][0]["posting_id"]
    res = client.patch(f"/admin/postings/{postingId}", json={"criteria": {**SCREENING_CRITERIA, "screening_pass_score": 60}})
    assert res.json()["code"] == "SCREENING_STARTED"
    res = client.patch(f"/admin/postings/{postingId}", json={"criteria": {**SCREENING_CRITERIA, "pass_score": 75}})
    assert res.status_code == 200, res.text  # 서류 평가 칸을 그대로 두면 다른 기준은 지금처럼 바꿀 수 있다


# ---------- 포트폴리오 ----------

PDF = b"%PDF-1.4 portfolio"


@pytest.fixture()
def fakeFiles(monkeypatch):
    from app.services import resume_extract, storage

    stored: dict[str, bytes] = {}
    monkeypatch.setattr(storage, "putObject", lambda key, data, contentType="": stored.__setitem__(key, data))
    monkeypatch.setattr(storage, "deletePrefix", lambda prefix: sum(1 for k in list(stored) if k.startswith(prefix) and stored.pop(k)))
    pages = {"text": "PyTorch 와 SQL 로 이미지 분류 모델을 학습하고 결과를 배포했습니다."}

    async def readPages(data):
        text = pages["text"]
        return [resume_extract.PageText(1, text, "pymupdf" if text else "none")]

    async def noOcr(*args, **kwargs):
        raise resume_extract.OcrError("down")
    monkeypatch.setattr(resume_extract, "readPages", readPages)
    monkeypatch.setattr(resume_extract, "ocrPages", noOcr)
    return stored, pages


def draftApplication(adminClient, criteria=None):
    postingId = publishedPosting(adminClient, criteria=criteria or SCREENING_CRITERIA)
    adminClient.post("/auth/logout")
    signup(adminClient)
    login(adminClient, "kim@example.com", APPLICANT_PASSWORD)
    appId = adminClient.post("/applications", json={"posting_id": postingId}).json()["application_id"]
    assert adminClient.post(f"/applications/{appId}/consent", json=CONSENT).status_code == 201
    return adminClient, appId


def test_portfolioTextIsUsedInScreening(adminClient, sessionFactory, monkeypatch, fakeFiles):
    stored, _pages = fakeFiles
    client, appId = draftApplication(adminClient)
    res = client.post(f"/applications/{appId}/portfolio", files={"file": ("포트폴리오.pdf", PDF, "application/pdf")})
    assert res.status_code == 200, res.text
    assert res.json()["portfolio"]["file_name"] == "포트폴리오.pdf" and len(stored) == 1
    assert client.post(f"/applications/{appId}/resume", json=RESUME).status_code == 200
    useModel(monkeypatch, FakeModel({}))
    runScreen(appId)
    with sessionFactory() as db:
        rounds = db.query(ResumeScreening).filter_by(application_id=appId).one().rounds
    skillsRow = next(r for r in rounds["first"] if r["item"] == "skills")
    # 이력서만으로는 2단계(PyTorch 없음). 포트폴리오에 PyTorch·SQL 을 쓴 근거가 있어 필수 3개 모두 + 사용 근거 → 3단계
    assert skillsRow["level"] == 3
    assert "PyTorch" in skillsRow["evidence"]
    assert client.post(f"/applications/{appId}/portfolio", files={"file": ("p.pdf", PDF, "application/pdf")}).json()["code"] == "RESUME_LOCKED"


def test_portfolioReplacedAndDeleted(adminClient, fakeFiles):
    stored, _pages = fakeFiles
    client, appId = draftApplication(adminClient)
    client.post(f"/applications/{appId}/portfolio", files={"file": ("a.pdf", PDF, "application/pdf")})
    client.post(f"/applications/{appId}/portfolio", files={"file": ("b.pdf", PDF, "application/pdf")})
    assert len(stored) == 1 and client.get(f"/applications/{appId}/portfolio").json()["portfolio"]["file_name"] == "b.pdf"
    assert client.delete(f"/applications/{appId}/portfolio").status_code == 204
    assert stored == {} and client.get(f"/applications/{appId}/portfolio").json()["portfolio"] is None


def test_portfolioRejectedWhenPostingHasNoScreening(adminClient, fakeFiles):
    client, appId = draftApplication(adminClient, {**SCREENING_CRITERIA, "screening_enabled": False})
    res = client.post(f"/applications/{appId}/portfolio", files={"file": ("a.pdf", PDF, "application/pdf")})
    assert res.json()["code"] == "PORTFOLIO_NOT_USED"


def test_portfolioMustBePdfWithText(adminClient, fakeFiles):
    _stored, pages = fakeFiles
    client, appId = draftApplication(adminClient)
    res = client.post(f"/applications/{appId}/portfolio", files={"file": ("a.png", b"\x89PNG\r\n\x1a\nxxxx", "image/png")})
    assert res.json()["code"] == "UNSUPPORTED_FILE"
    pages["text"] = ""
    res = client.post(f"/applications/{appId}/portfolio", files={"file": ("scan.pdf", PDF, "application/pdf")})
    assert res.json()["code"] == "PORTFOLIO_NO_TEXT"


def test_adminPassStartsQuestionsInsideEventLoop(adminClient, monkeypatch):
    """실제 scheduleCompose 처럼 이벤트 루프가 있어야 하는 함수로 바꿔 본다 (E2E 에서 500: 동기 엔드포인트라 루프가 없었음)."""
    client, appId = screeningApplicant(adminClient)
    useModel(monkeypatch, FakeModel({}))
    runScreen(appId)
    client.post("/auth/logout")
    login(client, "admin@huge.local", ADMIN_PASSWORD)
    started = []
    monkeypatch.setattr(question_compose, "scheduleCompose", lambda applicationId: started.append(asyncio.get_running_loop()))
    res = client.post(f"/admin/applications/{appId}/screening/decision", json={"decision": "pass", "note": "확인"})
    assert res.status_code == 200, res.text
    assert len(started) == 1
