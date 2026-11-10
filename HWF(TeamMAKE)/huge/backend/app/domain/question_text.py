"""AI 가 만든 면접 질문 글 검사. 본질문(T2·T3)과 꼬리질문(T4)이 같이 쓴다 (2026-11-10 사용자 결정).

실측(2026-11-10 시뮬레이션, llm-rt Qwen3 4B)에서 나온 것을 막는다:
- 찌꺼기: 끝에 붙는 JSON 조각("…인가요?'}"), 이모지("✅✅"), 한글에 붙은 영어("본ly")
- 답변 방식 지시: "1문장으로", "간단히", "90초 내에"
- 한 번에 여러 개 묻기: "~했고, ~", "~이며, ~", "~와 그 이유", 의문사 두 개
"""

import re

QUESTION_MAX_CHARS = 100  # 90초 답변에 맞는 질문 길이. 실측에서 좋은 질문은 50~95자였다

# 끝에 붙은 따옴표·괄호·중괄호는 질문 뒤에 새어 나온 JSON 조각이다. 질문이 끝난 자리(?·.·요·까) 뒤의 것만 뗀다
TRAILING_JUNK = re.compile(r"(?<=[?.요까])[\s'\"‘’“”}\])]+$")
# 질문에 써도 되는 글자: 한글 · 영문 · 숫자 · 흔한 문장부호. 이 밖의 글자(이모지·중괄호·대괄호·일본어·한자 등)는 찌꺼기로 본다
ALLOWED_CHAR = re.compile(r"[가-힣A-Za-z0-9\s.,?!·'\"‘’“”()\-/+%&:~_…]")
FOREIGN_SCRIPT = re.compile(r"[぀-ヿ一-鿿]")  # 4B 모델이 가끔 섞는 일본어·한자 (실측: "하나举げ고")
HANGUL_THEN_LATIN = re.compile(r"[가-힣][A-Za-z]")  # 한글 바로 뒤 영어 (실측: "본ly"). "Python을" 처럼 영어 뒤 한글은 괜찮다
META_PHRASE = re.compile(
    r"(한|하나의|두|세|\d+)\s*문장\s*(으로|이내|안에|내로)"
    r"|\d+\s*(초|분)\s*(내|안|이내|동안)"
    r"|\d+\s*(자|글자)\s*(이내|이하|안|로)"
    r"|간단히|간략히|간단하게|짧게|한마디로|요약해\s*(서|주)"
)
COMPOUND = re.compile(
    r"(고|며|이며|으며|이고|하고|했고|였고|었고|하시고|주시고)\s*,"  # "~했고, ~" "~이며, ~"
    r"|그리고|또한|아울러|더불어"
    r"|[와과]\s*,|[와과]\s*그\s"  # "방법과 그 이유를" "이유와, 그 이유가" (실측)
    r"|(무엇이며|무엇이고|이며|으며)\s+그\s"
)
QUESTION_WORD = re.compile(r"무엇|어떻게|어떤|왜|얼마나|언제|어디")
TWO_SENTENCES = re.compile(r"[?.!]\s+\S")  # 실측: "…무엇인가요? 한 가지 원리를 설명해 주세요." "…하시나요. (예: …)"
STATEMENT_END = re.compile(r"[입습]니다\??$")  # 실측: "…된 계기입니다?" 처럼 서술문 끝에 물음표만 붙인 것
QUESTION_END = re.compile(r"(\?|요\.?|까\.?)$")  # 실측: "…동기입니다." "…관심을 갖게 된 이유" 는 질문이 아니다

# 예/아니오로 답할 수 있는 질문 (실측: "의견 차이가 생긴 적이 있었나요?"). 의문사가 없고 부탁하는 꼴("설명해 주시겠어요?")도 아닌 질문
OPEN_WORD = re.compile(r"무엇|어떻게|어떤|왜|얼마|언제|어디|누구|뭐|몇")
REQUEST_FORM = re.compile(r"주세요|주시겠|주실|주십시오|말씀해|설명해|알려")
# 예/아니오 질문 뒤에 그 이유를 묻는 꼬리질문 (2026-11-10 사용자 결정). 짧은 답이면 LLM 없이 이 글로 묻는다
YES_NO_FOLLOWUP = "그렇게 답하신 이유를 구체적으로 말씀해 주세요."


def isYesNo(text: str) -> bool:
    text = (text or "").strip()
    return bool(QUESTION_END.search(text)) and not OPEN_WORD.search(text) and not REQUEST_FORM.search(text)


def cleanQuestion(text: str) -> str:
    return TRAILING_JUNK.sub("", (text or "").strip())


def textProblem(text: str) -> str | None:
    """문제 코드, 괜찮으면 None. 앞에서 cleanQuestion 으로 끝 찌꺼기를 뗀 글을 넣는다."""
    if FOREIGN_SCRIPT.search(text):
        return "foreign_script"
    if HANGUL_THEN_LATIN.search(text) or any(not ALLOWED_CHAR.match(ch) for ch in text):
        return "junk_text"
    if META_PHRASE.search(text):
        return "meta_phrase"
    if text.count("?") > 1 or TWO_SENTENCES.search(text) or COMPOUND.search(text) or len(QUESTION_WORD.findall(text)) > 1:
        return "compound_question"
    if not QUESTION_END.search(text) or STATEMENT_END.search(text):
        return "not_question"
    if len(text) > QUESTION_MAX_CHARS:
        return "too_long"
    return None
