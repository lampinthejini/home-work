"""말투·문법 다듬기는 규칙으로만 (CONFLICTS C-28, 2026-11-19 사용자 결정).

실측(모의 지원 10명): "…활용하셨는가요~인가요?", "Python과 파이썬의 표준 라이브러리에서…", "LangChain를" 처럼 내용은 맞는데
문장이 어색한 질문이 남았다. 4B 다듬기는 50문항 중 0건을 고쳐 뺐고(사용자: "규칙으로만 진행해도 괜찮을거같네"), 규칙으로 고친다.
"""

import pytest


def test_tildeInQuestionIsJunk():
    from app.domain import question_text
    assert question_text.textProblem("어떻게 활용하셨는가요~인가요?") is not None


@pytest.mark.parametrize("before, after", [
    ("LangChain를 이용해 벡터 DB와 LLM을 연동할 때 어떤 방법을 쓰시나요?", "LangChain을 이용해 벡터 DB와 LLM을 연동할 때 어떤 방법을 쓰시나요?"),
    ("LLM를 쓸 때 주의할 점은 무엇인가요?", "LLM을 쓸 때 주의할 점은 무엇인가요?"),
    ("API이 느려지는 원인은 무엇인가요?", "API가 느려지는 원인은 무엇인가요?"),
    ("SQL는 왜 쓰나요?", "SQL은 왜 쓰나요?"),
    ("Docker을 쓰는 이유는 무엇인가요?", "Docker를 쓰는 이유는 무엇인가요?"),
    ("XGBoost를 사용한 이유는 무엇인가요?", "XGBoost를 사용한 이유는 무엇인가요?"),  # '부스트' — 받침 없음, 그대로
    ("FastAPI와 Django의 차이는 무엇인가요?", "FastAPI와 Django의 차이는 무엇인가요?"),
    ("Python과 파이썬의 리스트와 딕셔너리의 차이는 무엇인가요?", "Python의 리스트와 딕셔너리의 차이는 무엇인가요?"),
])
def test_latinParticleAndDoubledNameAreFixed(before, after):
    """영문 낱말 뒤 조사를 읽는 소리(받침)에 맞추고, 영어·한글로 두 번 쓴 이름은 하나로 (C-28, 4B 가 못 잡음)."""
    from app.domain import question_text
    assert question_text.cleanQuestion(before) == after
