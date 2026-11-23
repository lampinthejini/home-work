"""AI 가 만든 질문 글 검사 (본질문·꼬리질문 공통, 2026-11-10 사용자 결정): 찌꺼기·답변 방식 지시.
두 가지를 묻는 질문은 막지 않는다 (2026-11-16 사용자 결정 — 뒷부분만 남기다 맥락이 사라졌다)."""

import pytest

from app.domain import question_text as qt
from app.interview import graph


@pytest.mark.parametrize("text", [
    "점을 본ly, 이 직무에서 가장 중요하게 생각하는 가치는 무엇인가요?",  # 한글에 붙은 영어 (실측)
    "검출 지연을 줄일 때 무엇을 먼저 확인했나요? ✅✅",  # 이모지 (실측)
    "모델을 고를 때 기준은 무엇인가요? {\"note\": 1}",
    "모델을 고를 때 기준은 무엇인가요 [참고]?",
])
def test_junkIsRejected(text):
    assert qt.textProblem(qt.cleanQuestion(text)) == "junk_text"


def test_trailingJsonTailIsCleaned():
    """끝에 붙는 JSON 찌꺼기(실측 "…무엇인가요?'}")는 떼고 쓴다."""
    assert qt.cleanQuestion("가장 중요하게 생각하는 가치는 무엇인가요?'}") == "가장 중요하게 생각하는 가치는 무엇인가요?"
    assert qt.textProblem(qt.cleanQuestion("가장 중요하게 생각하는 가치는 무엇인가요?'}")) is None


@pytest.mark.parametrize("text", [
    "본인의 전문성과 경험을 간단히 설명해 주세요.", "그 이유를 짧게 말씀해 주세요?", "협업 경험을 한마디로 말씀해 주세요?",
    "3분 안에 프로젝트를 설명해 주세요?", "50자 이내로 장점을 말씀해 주세요?", "그 이유를 1문장으로 설명해 주세요?",
])
def test_answerFormatInstructionsAreRejected(text):
    assert qt.textProblem(text) == "meta_phrase"


@pytest.mark.parametrize("text", [
    "가장 중요하게 여기는 가치는 무엇이며, 어떻게 실현할 계획인가요?",
    "어떤 판단 기준을 사용했고, 그 과정에서 어떤 기술적 제약이 있었나요?",
    "데이터 전처리 방법과 그 이유를 설명해 주세요.",
    "역할을 설명해 주시고 그리고 배운 점도 말씀해 주세요.",
    "어떤 상황에서 어떻게 갈등을 풀었나요?",
    "청크 크기는 어떻게 정하나요? 그 기준은 무엇인가요?",
])
def test_twoPartQuestionsPass(text):
    assert qt.textProblem(text) is None


def test_tooLongQuestionIsRejected():
    text = "제조 현장의 설비 데이터를 " * 8 + "다룰 때 가장 중요한 것은 무엇인가요?"
    assert len(text) > qt.QUESTION_MAX_CHARS and qt.textProblem(text) == "too_long"


@pytest.mark.parametrize("text", [
    "RAG 에서 청크 크기를 정하는 기준은 무엇인가요?",
    "2024년 공장 불량 검출 카메라 프로젝트에서 검출 지연을 40ms로 줄일 때 가장 먼저 확인한 것은 무엇이었나요?",
    "C++ 와 Python 을 함께 쓸 때 메모리 관리에서 주의할 점은 무엇인가요?",
    "‘사내 문서 RAG 챗봇’에서 맡은 역할을 구체적으로 설명해 주세요.",
    "팀원과 의견이 달랐을 때 어떻게 조율했는지 구체적으로 말씀해 주세요.",
])
def test_goodQuestionsPass(text):
    assert qt.textProblem(text) is None


def test_followupUsesSameTextCheck():
    """꼬리질문에도 찌꺼기·답변 방식 검사를 똑같이 건다."""
    assert graph.validateFollowup("vague", "그때 데이터 전처리는 구체적으로 어떻게 하셨나요?✅") == "junk_text"
    assert graph.validateFollowup("vague", "그 수치를 간단히 말씀해 주시겠어요?") == "meta_phrase"
    assert graph.validateFollowup("vague", "어떤 지표를 봤고, 그 결과는 어땠나요?") is None
    assert graph.validateFollowup("vague", "그때 데이터 전처리는 구체적으로 어떻게 하셨나요?") is None


@pytest.mark.parametrize("text", [
    "우리 회사의 AI 기반 설비 데이터 분석 업무를 맡아 성장하고 싶은 이유와 그에 어울리는 동기입니다.",  # 실측: 질문이 아님
    "우리 회사의 AI 기반 데이터 전환 프로세스에 가장 관심을 갖게 된 이유",  # 실측: 끝맺지 않음
    "팀워크를 함께 해서 프로젝트를 성공적으로 마무리했습니다.",
])
def test_notAQuestionIsRejected(text):
    assert qt.textProblem(text) == "not_question"


@pytest.mark.parametrize("text", [
    "비전 검사 모델의 정확도와 신뢰성 사이의 균형을 유지하기 위한 기준은 무엇인가요? 한 가지 원리를 설명해 주세요.",  # 실측
    "특정 프로젝트에서 팀원과 협업할 때 어떤 방식으로 소통하셨나요? 특히 효과적인 의사소통 방식은 무엇인가요?",
])
def test_twoSentencesPass(text):
    assert qt.textProblem(text) is None


def test_questionEndingInExampleParenIsNotAQuestion():
    assert qt.textProblem("데이터의 정확성을 어떻게 보장하시나요. (예: 문서의 품질 기준, 검증 절차 등)") == "not_question"  # 실측


@pytest.mark.parametrize("text", [
    "우리 회사의 제조 현장과 AI를 연결하는 방식에 어떤 호기심을 갖게 된 계기입니다?",  # 실측: 서술문 끝에 물음표만 붙임
    "우리 회사의 AI 기반 설비 운영에 어떤 관심을 갖게 된 계기입니다?",
])
def test_statementWithQuestionMarkIsRejected(text):
    assert qt.textProblem(text) == "not_question"
    assert qt.textProblem("어떤 점이 이 직무에 맞는다고 생각하십니까?") is None


@pytest.mark.parametrize(("text", "expected"), [
    ("설비 데이터를 분석할 때 팀원들과의 의견 차이가 생긴 적이 있었나요?", True),  # 실측 (3차 시뮬레이션)
    ("팀원의 접근 방식에 동의하지 않았던 적이 있나요?", True),
    ("LLM 서비스에서 프롬프트를 설계해 본 경험이 있으신가요?", True),
    ("협업 중 갈등이 생겼을 때 어떻게 해결하셨나요?", False),
    ("정규화와 표준화의 차이를 설명해 주시겠어요?", False),  # 부탁하는 꼴은 예/아니오 질문이 아니다
    ("맡은 역할을 구체적으로 말씀해 주실 수 있나요?", False),
    ("이 검사에서 실제로 양성일 확률은 얼마인가요?", False),  # 질문은행 실측: "얼마" 도 의문사
])
def test_yesNoQuestionIsDetected(text, expected):
    assert qt.isYesNo(text) is expected


def test_yesNoQuestionWithShortAnswerAsksReasonWithoutLlm():
    """2026-11-10 사용자 결정: 예/아니오 질문에는 그 이유를 꼬리질문으로 묻는다. 짧은 답이면 LLM 없이 정한 글로 묻는다."""
    from app.interview import engine
    yesNo = "팀원과 의견 차이가 생긴 적이 있나요?"
    assert engine.yesNoFollowup(yesNo, "네, 있습니다.") == qt.YES_NO_FOLLOWUP
    assert engine.yesNoFollowup(yesNo, "아니요 없었던 것 같습니다") == qt.YES_NO_FOLLOWUP
    assert engine.yesNoFollowup(yesNo, "네. 작년 프로젝트에서 배포 일정을 두고 팀원과 부딪혔고, 회의에서 위험을 표로 정리해 합의했습니다.") is None
    assert engine.yesNoFollowup("갈등은 어떻게 해결하셨나요?", "네") is None
    assert qt.textProblem(qt.YES_NO_FOLLOWUP) is None


def test_yesNoQuestionTellsLlmToAskReason():
    from app.interview import engine
    assert "이유" in engine.followupPrompt("팀원과 의견 차이가 생긴 적이 있나요?", "네, 있었고 회의로 풀었습니다.", "")
    assert "예/아니오" not in engine.followupPrompt("갈등은 어떻게 해결하셨나요?", "회의로 풀었습니다.", "")


@pytest.mark.parametrize("text", [
    "우리 회사에서 팀원들이 함께 성장할 수 있는 문화에 어떻게 매력을 느꼈는가요?",  # 실측 2026-11-10 공고 기반 후보
    "우리 회사의 혁신적인 아이디어를 현실로 만들기 위한 환경에 어떤 호감을 느꼈는가요?",
    "이 직무에서 가장 중요한 역량은 무엇이라고 생각하는가요?",
    "협업 문화 속에서 자신이 어떻게 일하고 싶은가요?",  # 실측: '싶으신가요'보다 낮춘 말
    "팀 내에서 의견이 달라졌을 때 어떻게 조율하고 함께 해결하던가요?",  # 실측 2026-11-18
    "AIIT에서 모르는 것을 모른다고 말하고, 함께 더 나아지는 방식으로 일하고 싶은 상황은 어떤 것이 되시나요?",  # 실측 2026-11-19 (C-29)
    "RAG 파이프라인에서 검색 결과의 관련성 저하가 생기는 원인은 무엇이고, 이를 줄이기 위한 방법을 생각하시나요?",  # 실측 2026-11-19, 예/아니오로 읽힘
])
def test_awkwardEndingIsRejected(text):
    """'~는가요'는 면접 존댓말로 어색하다 ('느끼셨나요'·'생각하시나요'로 써야 함)."""
    assert qt.textProblem(text) == "awkward_ending"


@pytest.mark.parametrize("text", [
    "우리 회사의 검색 서비스에 관심을 갖게 된 계기는 무엇인가요?",
    "입사하면 추천 서비스에서 어떤 일을 해 보고 싶으신가요?",
    "함께 성장하는 팀이 되려면 무엇이 필요하다고 생각하시나요?",
])
def test_naturalEndingsPass(text):
    assert qt.textProblem(text) is None


def test_connectiveDeIsJoined():
    """실측 2026-11-18: 'AIIT가 … 만들어가고 있는 데, …' — 쉼표 앞 '데'는 이어 주는 말(-는데)이라 붙인다."""
    assert qt.cleanQuestion("AIIT가 사용자 중심의 서비스를 만들어가고 있는 데, 참여해 보고 싶은 이유는 무엇인가요?") == \
        "AIIT가 사용자 중심의 서비스를 만들어가고 있는데, 참여해 보고 싶은 이유는 무엇인가요?"
    assert qt.cleanQuestion("모델이 작은 데 , 성능을 지키는 방법은 무엇인가요?") == "모델이 작은데, 성능을 지키는 방법은 무엇인가요?"
    # 쉼표가 없으면 '곳·경우' 뜻일 수 있어 그대로 둔다 ('배포하는 데 걸리는 시간')
    assert qt.cleanQuestion("모델을 배포하는 데 걸리는 시간을 줄이는 방법은 무엇인가요?") == "모델을 배포하는 데 걸리는 시간을 줄이는 방법은 무엇인가요?"


def test_honorificPastEndingIsAllowed():
    assert qt.textProblem("그 상황을 어떻게 해결해 나가셨던가요?") is None


def test_awkwardEndingInsideTwoSentenceQuestionIsRejected():
    text = "팀 프로젝트에서 계획이 지연된 상황에서 어떤 점을 통해 성장했는가요? 솔직히 말씀해 주시겠어요?"
    assert qt.textProblem(text) == "awkward_ending"


@pytest.mark.parametrize(("raw", "fixed"), [
    ("그 실패를 통해 무엇을 배웠는가요?", "그 실패를 통해 무엇을 배웠나요?"),  # 실측 2026-11-18
    ("어떻게 함께 방향을 정하고 조율했는가요?", "어떻게 함께 방향을 정하고 조율했나요?"),
    ("어떻게 기여하고 싶은가요?", "어떻게 기여하고 싶으신가요?"),
    ("무엇을 배웠는가요? 솔직히 말씀해 주시겠어요?", "무엇을 배웠나요? 솔직히 말씀해 주시겠어요?"),
    ("어떤 점이 중요하다고 생각하시나요?", "어떤 점이 중요하다고 생각하시나요?"),
    # 실측 c38(2026-11-23): '…삼으시겠는가요?' 가 '…삼으시겠나요?' 로 고쳐져 4B 가 1/1점, '겠습니까' 는 3/4점
    ("무엇을 우선 기준으로 삼으시겠는가요?", "무엇을 우선 기준으로 삼으시겠습니까?"),
    ("어떻게 대응하겠는가요? 구체적으로 말씀해 주세요.", "어떻게 대응하겠습니까? 구체적으로 말씀해 주세요."),
])
def test_fixableAwkwardEndingIsFixed(raw, fixed):
    assert qt.cleanQuestion(raw) == fixed and qt.textProblem(qt.cleanQuestion(raw)) is None
