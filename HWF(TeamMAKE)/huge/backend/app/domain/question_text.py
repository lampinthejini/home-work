"""AI 가 만든 면접 질문 글 검사. 본질문(T2·T3)과 꼬리질문(T4)이 같이 쓴다 (2026-11-10 사용자 결정).

실측(2026-11-10 시뮬레이션, llm-rt Qwen3 4B)에서 나온 것을 막는다:
- 찌꺼기: 끝에 붙는 JSON 조각("…인가요?'}"), 이모지("✅✅"), 한글에 붙은 영어("본ly")
- 답변 방식 지시: "1문장으로", "간단히", "90초 내에"
"""

import re

QUESTION_MAX_CHARS = 100  # 90초 답변에 맞는 질문 길이. 실측에서 좋은 질문은 50~95자였다

# 끝에 붙은 따옴표·괄호·중괄호는 질문 뒤에 새어 나온 JSON 조각이다. 질문이 끝난 자리(?·.·요·까) 뒤의 것만 뗀다
TRAILING_JUNK = re.compile(r"(?<=[?.요까])[\s'\"‘’“”}\])]+$")
# 질문에 써도 되는 글자: 한글 · 영문 · 숫자 · 흔한 문장부호. 이 밖의 글자(이모지·중괄호·대괄호·일본어·한자 등)는 찌꺼기로 본다
ALLOWED_CHAR = re.compile(r"[가-힣A-Za-z0-9\s.,?!·'\"‘’“”()\-/+%&:~_…]")
FOREIGN_SCRIPT = re.compile(r"[぀-ヿ一-鿿]")  # 4B 모델이 가끔 섞는 일본어·한자 (실측: "하나举げ고")
# 한글 사이 물결표 (실측 2026-11-19: "…활용하셨는가요~인가요?"). '3~5년' 처럼 숫자 사이는 그대로 둔다 (C-28)
HANGUL_TILDE = re.compile(r"[가-힣]\s*~\s*[가-힣]")
HANGUL_THEN_LATIN = re.compile(r"[가-힣][A-Za-z]")  # 한글 바로 뒤 영어 (실측: "본ly"). "Python을" 처럼 영어 뒤 한글은 괜찮다
META_PHRASE = re.compile(
    r"(한|하나의|두|세|\d+)\s*문장\s*(으로|이내|안에|내로)"
    r"|\d+\s*(초|분)\s*(내|안|이내|동안)"
    r"|\d+\s*(자|글자)\s*(이내|이하|안|로)"
    r"|간단히|간략히|간단하게|짧게|한마디로|요약해\s*(서|주)"
)
STATEMENT_END = re.compile(r"[입습]니다\??$")  # 실측: "…된 계기입니다?" 처럼 서술문 끝에 물음표만 붙인 것
QUESTION_END = re.compile(r"(\?|요\.?|까\.?)$")  # 실측: "…동기입니다." "…관심을 갖게 된 이유" 는 질문이 아니다
# 면접 존댓말로 어색한 끝 (실측 2026-11-10: "…매력을 느꼈는가요?"). "느끼셨나요"·"생각하시나요"로 쓴다. "인가요"는 괜찮다
# "일하고 싶은가요"도 "싶으신가요"보다 낮춘 말. "해결하던가요"(실측 2026-11-18)도 어색하지만, 높임이 든 "해결하셨던가요"는 괜찮다
# (실측: '던가요' 를 모두 막았더니 4B 가 즐겨 쓰는 '…셨던가요?' 가 걸려 첫 인성 자리가 세 번 모두 반려됨)
# 문장 가운데 물음도 본다 (실측 2026-11-18: "…성장했는가요? 솔직히 말씀해 주시겠어요?")
# 실측 2026-11-19 (C-29): "…상황은 어떤 것이 되시나요?", "…줄이기 위한 방법을 생각하시나요?"(예/아니오로 읽힘).
# "무엇이 필요하다고 생각하시나요?"처럼 '생각하시나요' 자체는 괜찮아 '방법을' 바로 뒤일 때만 막는다
AWKWARD_END = re.compile(r"((는|싶은)가요|(?<!셨)던가요|것이 되시나요|방법을 생각하시나요)(\?|$)")

# 예/아니오로 답할 수 있는 질문 (실측: "의견 차이가 생긴 적이 있었나요?"). 의문사가 없고 부탁하는 꼴("설명해 주시겠어요?")도 아닌 질문
OPEN_WORD = re.compile(r"무엇|어떻게|어떤|왜|얼마|언제|어디|누구|뭐|몇")
REQUEST_FORM = re.compile(r"주세요|주시겠|주실|주십시오|말씀해|설명해|알려")
# 예/아니오 질문 뒤에 그 이유를 묻는 꼬리질문 (2026-11-10 사용자 결정). 짧은 답이면 LLM 없이 이 글로 묻는다
YES_NO_FOLLOWUP = "그렇게 답하신 이유를 구체적으로 말씀해 주세요."


def isYesNo(text: str) -> bool:
    text = (text or "").strip()
    return bool(QUESTION_END.search(text)) and not OPEN_WORD.search(text) and not REQUEST_FORM.search(text)


# 쉼표 앞 '데'는 이어 주는 말(-는데·-은데)이라 앞말에 붙인다 (실측 2026-11-18: '만들어가고 있는 데,').
# 쉼표가 없으면 '곳·경우' 뜻('배포하는 데 걸리는')일 수 있어 건드리지 않는다
SPACED_CONNECTIVE_DE = re.compile(r"([가-힣]) 데\s*,")


# 바로 고칠 수 있는 어색한 말끝 (실측 2026-11-18: 4B 가 '…배웠는가요?' '…조율했는가요?' 를 자주 써 3번 다시 만들고도 예비 질문으로 넘어감).
# '는가요' → '나요'(배웠나요·조율했나요·있나요), '싶은가요' → '싶으신가요'. '해결하던가요' 처럼 고치기 어려운 것은 그대로 두고 반려한다
ENDING_FIXES = ((re.compile(r"싶은가요(?=\?|$)"), "싶으신가요"), (re.compile(r"는가요(?=\?|$)"), "나요"))


def fixEnding(text: str) -> str:
    for pattern, replacement in ENDING_FIXES:
        text = pattern.sub(replacement, text)
    return text


# ---------- 영문 낱말 뒤 조사 · 두 번 쓴 이름 (CONFLICTS C-28, 2026-11-19) ----------
# 실측: "LangChain를", "Python과 파이썬의 …". 4B 다듬기는 이런 것을 거의 고치지 못해(모의 50문항 중 0건) 규칙으로 고친다.
LATIN_PARTICLE = re.compile(r"([A-Za-z][A-Za-z0-9.+#-]*)(을|를|이|가|은|는|과|와)(?=[\s,.?!]|$)")
WITH_BATCHIM = {"를": "을", "가": "이", "는": "은", "와": "과"}  # 받침 없을 때 → 있을 때
WITHOUT_BATCHIM = {v: k for k, v in WITH_BATCHIM.items()}
LETTER_WITH_BATCHIM = set("LMNR")  # 알파벳 이름이 받침으로 끝나는 글자 (엘·엠·엔·알)
KOREAN_NAMES = {"Python": "파이썬", "Java": "자바", "Docker": "도커", "Redis": "레디스", "React": "리액트"}
DOUBLED_NAME = re.compile("(" + "|".join(KOREAN_NAMES) + r")(?:과|와)\s*(" + "|".join(KOREAN_NAMES.values()) + ")")


def readsWithBatchim(word: str) -> bool | None:
    """영문 낱말을 우리말로 읽을 때 끝에 받침이 있는가. 숫자로 끝나면 모름(None).
    약어(모두 대문자)는 알파벳 이름으로(LLM → 엘엘엠), 낱말은 끝 소리로(LangChain → 랭체인, XGBoost → 엑스지부스트)."""
    letters = word.rstrip(".+#-")
    if not letters or letters[-1].isdigit():
        return None
    if letters.isupper():
        return letters[-1] in LETTER_WITH_BATCHIM
    return letters.lower().endswith(("n", "m", "l", "ng"))


def fixLatinParticle(text: str) -> str:
    def fix(m: re.Match) -> str:
        word, particle = m.group(1), m.group(2)
        batchim = readsWithBatchim(word)
        if batchim is None:
            return m.group(0)
        return word + (WITH_BATCHIM if batchim else WITHOUT_BATCHIM).get(particle, particle)
    return LATIN_PARTICLE.sub(fix, text)


def dropDoubledName(text: str) -> str:
    """'Python과 파이썬의' → 'Python의' (같은 이름을 영어·한글로 두 번)."""
    def fix(m: re.Match) -> str:
        return m.group(1) if KOREAN_NAMES[m.group(1)] == m.group(2) else m.group(0)
    return DOUBLED_NAME.sub(fix, text)


def cleanQuestion(text: str) -> str:
    text = SPACED_CONNECTIVE_DE.sub(r"\1데,", TRAILING_JUNK.sub("", (text or "").strip()))
    return fixEnding(fixLatinParticle(dropDoubledName(text)))


def textProblem(text: str) -> str | None:
    """문제 코드, 괜찮으면 None. 앞에서 cleanQuestion 으로 끝 찌꺼기를 뗀 글을 넣는다."""
    if FOREIGN_SCRIPT.search(text):
        return "foreign_script"
    if HANGUL_THEN_LATIN.search(text) or HANGUL_TILDE.search(text) or any(not ALLOWED_CHAR.match(ch) for ch in text):
        return "junk_text"
    if META_PHRASE.search(text):
        return "meta_phrase"
    if not QUESTION_END.search(text) or STATEMENT_END.search(text):
        return "not_question"
    if AWKWARD_END.search(text):
        return "awkward_ending"
    if len(text) > QUESTION_MAX_CHARS:
        return "too_long"
    return None
