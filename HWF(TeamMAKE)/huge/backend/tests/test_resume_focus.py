"""이력서 두 자리 나누기 (CONFLICTS C-32, 사용자 2026-11-21: '프로젝트 관련 하나, 프로젝트와 관련 없는 하나').
c31c 실측: 두 자리가 같은 경험 전체를 받아 21쌍 중 8쌍이 같은 프로젝트의 같은 일을 다시 물음(유사도 0.82~0.88)."""

import asyncio
import random

from app.models import Application
from app.services import question_compose
from app.services.question_compose import resumeFocus
from tests.test_question_rag import composed, makeApplication, world  # noqa: F401 — world 는 pytest fixture

TWO_PROJECTS = {
    "projects": [
        {"name": "사내 규정 검색 챗봇", "period": "2025", "description": "문단 단위 분할로 정답 문서 포함률을 61%에서 84%로 올렸다."},
        {"name": "리뷰 감성 분류", "period": "2025", "description": "KoBERT 를 미세조정해 리뷰 2만 건을 분류했다."},
    ],
    "cover_letter": ("저는 문서를 찾는 데 시간을 쓰는 사람들을 돕고 싶어 RAG 를 공부했습니다. "
                     "졸업 프로젝트로 규정 문서 검색 챗봇을 만들었습니다. 학교 도서관에서 2년 동안 근로 학생으로 일하며 이용자 문의를 받았습니다."),
}
CAREER = {
    "career": [{"company": "다온커머스", "role": "백엔드 개발자",
                "description": "주문·정산 API 를 개발했다. 2025년 고객 문의 자동 분류에 GPT API 를 붙여 분류 시간을 40% 줄였다."}],
    "projects": [{"name": "고객 문의 자동 분류", "period": "2025", "description": "문의 글을 12개 유형으로 분류하는 LLM 파이프라인."}],
}


def test_firstSlotIsOneProjectAndSecondAvoidsIt():
    first = resumeFocus(TWO_PROJECTS, 0, None, random.Random(0))
    assert first.project in ("사내 규정 검색 챗봇", "리뷰 감성 분류")
    assert first.experience.count("프로젝트:") == 1 and first.anchors == [first.project]
    second = resumeFocus(TWO_PROJECTS, 1, "사내 규정 검색 챗봇", random.Random(0))
    assert second.apart and "프로젝트:" not in second.experience  # 프로젝트가 아닌 자기소개
    assert "도서관" in second.experience and "검색 챗봇" not in second.experience  # 첫 자리 프로젝트 문장은 뺀다
    assert second.anchors == []  # 자기소개뿐이면 이름을 짚지 않아도 된다


def test_secondSlotDropsCareerSentenceAboutTheFirstProject():
    """사람 2: 경력 줄에도 '고객 문의 자동 분류' 가 나온다 → 그 문장을 빼면 '주문·정산 API' 가 남는다."""
    second = resumeFocus(CAREER, 1, "고객 문의 자동 분류", random.Random(0))
    assert "주문·정산 API" in second.experience and "고객 문의" not in second.experience
    assert second.anchors == ["다온커머스"] and second.apart


def test_secondSlotFallsBackToAnotherProjectThenTheSameOne():
    noCover = {"projects": TWO_PROJECTS["projects"]}
    other = resumeFocus(noCover, 1, "사내 규정 검색 챗봇", random.Random(0))
    assert other.anchors == ["리뷰 감성 분류"] and other.apart
    single = {"projects": TWO_PROJECTS["projects"][:1]}
    same = resumeFocus(single, 1, "사내 규정 검색 챗봇", random.Random(0))
    assert not same.apart and "다른 면" in same.focus  # 경험이 하나뿐이면 같은 경험의 다른 면


def test_noProjectUsesCareerForTheFirstSlot():
    first = resumeFocus({"career": CAREER["career"]}, 0, None, random.Random(0))
    assert first.project is None and first.anchors == ["다온커머스"] and "경력:" in first.experience


def test_secondResumeSlotPromptAsksForNonProjectExperience(sessionFactory, world, monkeypatch):  # noqa: F811
    """둘째 이력서 자리 프롬프트는 프로젝트가 아닌 경력·자기소개를 묻게 한다."""
    fake = world()
    appId = makeApplication(sessionFactory)
    with sessionFactory() as db:
        app = db.get(Application, appId)
        app.resume_snapshot = TWO_PROJECTS
        db.commit()
    monkeypatch.setattr(question_compose, "materialRandom", random.Random(1))
    asyncio.run(question_compose.compose(appId))
    resumePrompts = [p for p in fake.prompts if p.startswith("[만들 질문] 이력서")]
    assert resumePrompts and "프로젝트가 아닌 경력·자기소개" in resumePrompts[-1]
    rows = [r for r in composed(sessionFactory, appId) if r.qtype == "resume"]
    assert len(rows) == 2


def test_secondResumeQuestionTooCloseToTheFirstIsNotKept(sessionFactory, world, monkeypatch):  # noqa: F811
    """앞 이력서 질문과 0.8 이상 비슷하면 마지막 시도에도 받지 않는다 (c31c: 같은 일을 다시 물은 짝 0.82~0.88)."""
    world()
    monkeypatch.setattr(question_compose, "RESUME_SAME_SIMILARITY", -1.0)  # 늘 비슷하다고 보게
    appId = makeApplication(sessionFactory)
    asyncio.run(question_compose.compose(appId))
    rows = [r for r in composed(sessionFactory, appId) if r.qtype == "resume"]
    assert [r.source for r in rows][0] == "generated" and rows[1].source != "generated"


def test_secondSlotDropsCoverSentencesRetellingTheFirstProject():
    """c31c: 자기소개가 이름 없이 같은 프로젝트를 다시 말한다('처음 정확도는 78%였는데'). 숫자·낱말이 겹치는 문장도 뺀다.
    경력 줄은 다른 일이라 낱말이 겹쳐도 남긴다 (사람 10: 'Playwright, pytest')."""
    resume = {
        "career": [{"company": "테스트원", "role": "QA 엔지니어", "description": "웹 서비스 테스트 자동화(Playwright, pytest)."}],
        "projects": [{"name": "고객 문의 자동 분류", "period": "2025",
                      "description": "틀린 분류를 모아 프롬프트를 매주 고쳤다. 정확도 78%→90%. pytest 테스트를 붙였다."}],
        "cover_letter": ("처음 정확도는 78%였는데 90%까지 올렸습니다. 틀린 분류를 매주 모아 프롬프트를 고쳤습니다. "
                         "로그로 원인을 찾는 일이 중요하다고 배웠습니다."),
    }
    second = resumeFocus(resume, 1, "고객 문의 자동 분류", random.Random(0))
    assert "78%" not in second.experience and "매주" not in second.experience
    assert "로그로 원인을" in second.experience and "Playwright" in second.experience


def test_secondSlotWithCoverDoesNotRequireCompanyName():
    """c32: 경력+자기소개 재료에 회사 이름을 꼭 넣게 하니 자기소개 질문이 '이름 없음' 으로 떨어져 예비 질문 9개 중 6개."""
    resume = {**CAREER, "cover_letter": "운영하면서 모델 답이 흔들릴 때 로그로 원인을 찾는 일이 가장 중요하다는 것을 배웠습니다."}
    second = resumeFocus(resume, 1, "고객 문의 자동 분류", random.Random(0))
    assert second.anchors == [] and "자기소개:" in second.experience and "'자기소개에서'" in second.focus
