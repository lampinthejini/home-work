"""점수 계산 (PRD 5-7 EVL-02~04, COD-06). api 는 조회용, 2단계 worker 는 확정용으로 같은 코드를 쓴다.

점수는 Decimal 로 계산하고 소수점 둘째 자리에서 반올림한다 (기술 아키텍처 11장).
"""

import re
from decimal import ROUND_HALF_UP, Decimal
from difflib import SequenceMatcher

EVAL_ITEMS = ("expertise", "logic", "relevance", "delivery", "culture_fit")
DEFAULT_WEIGHTS = {"expertise": 30, "logic": 25, "relevance": 20, "delivery": 10, "culture_fit": 15}

# 질문 종류별로 보는 평가 항목 (PRD 5-7 '어떤 질문에서 보나')
EVAL_ITEMS_BY_KIND = {
    "job": ["expertise", "logic", "relevance", "delivery"],
    "resume": ["expertise", "logic", "relevance", "delivery"],
    "personality": ["logic", "relevance", "delivery", "culture_fit"],
    "company": ["logic", "relevance", "delivery", "culture_fit"],
}

TWO_PLACES = Decimal("0.01")
HUNDRED = Decimal(100)


def roundScore(value: Decimal) -> Decimal:
    return value.quantize(TWO_PLACES, rounding=ROUND_HALF_UP)


def validateWeights(weights: dict) -> str | None:
    """틀린 이유를 돌려주고, 맞으면 None. 5 단위 · 항목마다 5 이상 · 합계 100 (JOB-04)."""
    if set(weights) != set(EVAL_ITEMS):
        return "평가 항목 5개의 비율을 모두 입력해 주세요"
    for key in EVAL_ITEMS:
        value = weights[key]
        if not isinstance(value, int) or value < 5 or value % 5:
            return "비율은 5% 단위, 항목마다 5% 이상이어야 합니다"
    if sum(weights.values()) != 100:
        return "비율의 합계는 100%여야 합니다"
    return None


def validateCodingRatio(ratio: int) -> bool:
    return isinstance(ratio, int) and 10 <= ratio <= 90 and ratio % 10 == 0


def itemScores(questionScores: list[dict[str, int]]) -> dict[str, Decimal]:
    """항목 점수 = 그 항목을 본 질문들의 점수 평균 ÷ 5 × 100 (EVL-03).

    questionScores: 질문마다 {항목: 0~5}. 그 질문이 보지 않는 항목은 넣지 않는다.
    """
    result = {}
    for item in EVAL_ITEMS:
        values = [Decimal(s[item]) for s in questionScores if item in s]
        if not values:
            result[item] = Decimal(0)
            continue
        result[item] = roundScore(sum(values) / len(values) / 5 * HUNDRED)
    return result


def interviewScore(items: dict[str, Decimal], weights: dict[str, int]) -> Decimal:
    """AI 면접 점수 = Σ(항목 점수 × 항목 비율)."""
    return roundScore(sum(items[k] * Decimal(weights[k]) / HUNDRED for k in EVAL_ITEMS))


def codingScore(problems: list[tuple[int, int]]) -> Decimal:
    """코딩테스트 점수 = 문제별 (통과 수 ÷ 전체 수)의 평균 × 100. 2문제 같은 배점 (COD-06)."""
    if not problems:
        return Decimal(0)
    ratios = [Decimal(passed) / Decimal(total) if total else Decimal(0) for passed, total in problems]
    return roundScore(sum(ratios) / len(ratios) * HUNDRED)


def totalScore(interview: Decimal, coding: Decimal | None, codingEnabled: bool, codingRatio: int) -> Decimal:
    """총점 (EVL-04). 코딩테스트를 안 쓰면 AI 면접 점수가 곧 총점."""
    if not codingEnabled:
        return interview
    ratio = Decimal(codingRatio)
    return roundScore(interview * (HUNDRED - ratio) / HUNDRED + (coding or Decimal(0)) * ratio / HUNDRED)


QUOTE_IGNORED = r"[\s\.,!?·…\"'“”‘’]"
QUOTE_MATCH_RATIO = 0.9  # 근거가 답변 속 구절과 이만큼 같으면 그 구절을 근거로 쓴다 (E17, 2026-11-09 사용자 결정)


def normalizeForQuote(text: str) -> str:
    return re.sub(QUOTE_IGNORED + "+", "", text or "")


def quoteInAnswer(quote: str, answer: str) -> bool:
    """근거 문장이 실제 답변에 있는지 (EVL-02). 띄어쓰기·문장부호 차이는 무시한다."""
    q = normalizeForQuote(quote)
    return bool(q) and q in normalizeForQuote(answer)


def matchQuote(quote: str, answer: str, minRatio: float = QUOTE_MATCH_RATIO) -> str | None:
    """AI 가 따온 근거와 맞는 답변 속 구절을 답변 글 그대로 돌려준다. 없으면 None.

    AI 가 한두 글자 다르게 옮기면 근거가 거절돼 1점이 되고, 같은 답변의 점수가 흔들렸다 (E17).
    띄어쓰기·문장부호를 뺀 글에서 같은 구절을 찾고, 없으면 minRatio 이상 비슷한 구절을 찾는다.
    돌려주는 글은 답변에서 잘라 온 것이라 저장되는 근거는 항상 지원자가 실제로 한 말이다.
    """
    q = normalizeForQuote(quote)
    if not q or not answer:
        return None
    keep = [i for i, ch in enumerate(answer) if not re.fullmatch(QUOTE_IGNORED, ch)]
    norm = "".join(answer[i] for i in keep)
    start = norm.find(q)
    end = start + len(q)
    if start < 0:
        span = closestSpan(q, norm, minRatio)
        if span is None:
            return None
        start, end = span
    return answer[keep[start]: keep[end - 1] + 1].strip()


def closestSpan(q: str, norm: str, minRatio: float) -> tuple[int, int] | None:
    """가장 긴 공통 부분을 기준으로 앞뒤·길이를 조금씩 바꿔 가장 비슷한 구간을 찾는다."""
    anchor = SequenceMatcher(None, q, norm, autojunk=False).find_longest_match(0, len(q), 0, len(norm))
    if anchor.size == 0:
        return None
    base = anchor.b - anchor.a
    slack = max(2, len(q) // 20)
    best, bestRatio = None, minRatio
    for length in range(max(1, len(q) - slack), len(q) + slack + 1):
        for begin in range(max(0, base - slack), min(len(norm) - 1, base + slack) + 1):
            window = norm[begin: begin + length]
            if not window:
                continue
            ratio = SequenceMatcher(None, q, window, autojunk=False).ratio()
            if ratio >= bestRatio:
                best, bestRatio = (begin, begin + len(window)), ratio
    return best
