from decimal import Decimal

from app.domain.scoring import (
    DEFAULT_WEIGHTS,
    codingScore,
    interviewScore,
    itemScores,
    quoteInAnswer,
    totalScore,
    validateCodingRatio,
    validateWeights,
)


def test_prdWorkedExample():
    # PRD 5-7 계산 예시: 74.5점, 코딩 60점, 70:30 → 70.15
    items = {"expertise": Decimal(80), "logic": Decimal(70), "relevance": Decimal(75), "delivery": Decimal(60), "culture_fit": Decimal(80)}
    interview = interviewScore(items, DEFAULT_WEIGHTS)
    assert interview == Decimal("74.50")
    assert totalScore(interview, Decimal(60), True, 30) == Decimal("70.15")


def test_totalWithoutCodingIsInterview():
    assert totalScore(Decimal("74.50"), None, False, 30) == Decimal("74.50")


def test_itemScoresAverageOnlyQuestionsThatSeeItem():
    scores = [{"expertise": 4, "logic": 3}, {"expertise": 5}, {"culture_fit": 2}]
    items = itemScores(scores)
    assert items["expertise"] == Decimal("90.00")  # (4+5)/2/5*100
    assert items["logic"] == Decimal("60.00")
    assert items["culture_fit"] == Decimal("40.00")
    assert items["delivery"] == Decimal(0)


def test_codingScoreEqualWeightPerProblem():
    assert codingScore([(5, 5), (1, 4)]) == Decimal("62.50")
    assert codingScore([]) == Decimal(0)


def test_validateWeights():
    assert validateWeights(DEFAULT_WEIGHTS) is None
    assert validateWeights({**DEFAULT_WEIGHTS, "logic": 26, "delivery": 9}) is not None  # 5 단위 아님
    assert validateWeights({**DEFAULT_WEIGHTS, "delivery": 0, "logic": 35}) is not None  # 5 미만
    assert validateWeights({**DEFAULT_WEIGHTS, "logic": 30}) is not None  # 합계 105
    assert validateWeights({"expertise": 100}) is not None


def test_validateCodingRatio():
    assert validateCodingRatio(30)
    assert not validateCodingRatio(35)
    assert not validateCodingRatio(0)


def test_quoteInAnswerIgnoresSpacingAndPunctuation():
    answer = "저는 이전 프로젝트에서 데이터 불균형을, 오버샘플링으로 해결했습니다."
    assert quoteInAnswer("데이터 불균형을 오버샘플링으로 해결했습니다", answer)
    assert not quoteInAnswer("모델을 새로 학습했습니다", answer)
    assert not quoteInAnswer("", answer)
