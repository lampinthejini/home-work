"""답변을 받아 적을 때 STT 에 주는 참고 말 (2026-11-17 사용자 결정, STT 방식 '가')."""

from app.services import speech


def test_hintsAreQuestionAndResumeSkills():
    resume = {"name": "홍길동", "email": "a@b.c", "skills": ["Python", " PyTorch "],
              "projects": [{"name": "사내 챗봇", "skills": ["python", "LangChain"]}]}
    hints = speech.sttHints("RAG 와  파인튜닝의 차이는?", resume)
    assert hints == "RAG 와 파인튜닝의 차이는? Python PyTorch LangChain"
    assert "홍길동" not in hints and "a@b.c" not in hints


def test_hintsKeepOnlySomeSkills():
    resume = {"skills": [f"skill{i}" for i in range(20)]}
    hints = speech.sttHints("질문", resume)
    assert hints.split()[1:] == [f"skill{i}" for i in range(speech.HINT_SKILL_COUNT)]


def test_hintsWithoutResume():
    assert speech.sttHints("질문입니다", {}) == "질문입니다"
