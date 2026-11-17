"""예비 질문 (2026-11-16 사용자 결정, CONFLICTS C-20).

엑셀 질문 DB 는 지웠다. 질문 DB 는 예비 질문(source='reserve') 하나만 쓴다:
- 기본 질문: 종류(인성·회사·이력서 기반·직무)마다 10개 (RESERVE_QUESTIONS, manage reset_questions 가 넣는다)
- AI 가 만든 질문: 면접·공고 게시 때 만든 질문 중 개인적이지 않고 같은 종류 예비 질문과 0.8 미만으로 비슷한 것을
  승인 없이 바로 넣는다. 종류마다 RESERVE_LIMIT_PER_KIND 개가 차면 더 넣지 않는다.
예비 질문은 AI 가 질문을 만들 때 보는 예시(RAG)이고, 못 만들었을 때 대신 내는 질문이다.
"""

import re

from sqlalchemy.orm import Session

from ..domain.scoring import EVAL_ITEMS_BY_KIND
from ..models import AuditLog, InterviewQuestion, Question, QuestionUsage
from . import rag

RESERVE_LIMIT_PER_KIND = 100
RESERVE_KINDS = ("personality", "company", "resume", "job")
DEFAULT_JOB_CODE = "AI_AX"
SEED_CATEGORY = "기본"

# 종류마다 10개 (AI/AX 엔지니어 기준). 회사 질문은 회사 정보(services/company.py DEFAULT_PROFILE)에 맞춘다
RESERVE_QUESTIONS = {
    "personality": [
        "팀원과 의견이 달랐을 때 어떻게 합의점을 찾으셨나요?",
        "맡은 일에서 실수를 했을 때 어떻게 바로잡으셨나요?",
        "받은 피드백 가운데 가장 도움이 된 것은 무엇이고, 어떻게 반영하셨나요?",
        "마감이 겹치는 여러 일을 동시에 맡았을 때 우선순위를 어떻게 정하셨나요?",
        "새로운 기술을 짧은 시간 안에 익혀야 했을 때 어떻게 공부하셨나요?",
        "목표를 이루지 못했던 일에서 가장 크게 배운 점은 무엇인가요?",
        "다른 직군 동료와 협업할 때 소통을 위해 가장 신경 쓰는 점은 무엇인가요?",
        "AI가 만든 결과가 틀렸을 때 어떻게 대응해야 한다고 생각하시나요?",
        "스스로 문제를 찾아 개선을 제안했던 일을 말씀해 주세요.",
        "반복되는 일을 더 효율적으로 바꿔 본 적이 있다면 어떻게 바꾸셨나요?",
    ],
    "company": [
        "AIIT에 지원하게 된 계기는 무엇인가요?",
        "AIIT의 서비스 가운데 AI로 가장 먼저 개선하고 싶은 것은 무엇인가요?",
        "자체 언어 모델 AIIT-X를 가진 회사에서 AI/AX 엔지니어로 어떤 일을 해 보고 싶으신가요?",
        "AIIT가 사내 업무에 AI를 도입한다면 가장 먼저 바꿔야 할 업무는 무엇이라고 생각하시나요?",
        "작은 조직이 스스로 목표를 정하고 빠르게 실험하는 문화에서 어떻게 일하고 싶으신가요?",
        "입사 후 1년 안에 AIIT에서 이루고 싶은 목표는 무엇인가요?",
        "AIIT가 생성형 AI 서비스를 내놓을 때 사용자 신뢰를 얻으려면 무엇이 중요하다고 생각하시나요?",
        "검색·쇼핑·결제처럼 여러 서비스를 가진 회사에서 AI를 적용할 때의 장점은 무엇이라고 생각하시나요?",
        "AIIT의 핵심 가치 가운데 본인과 가장 잘 맞는 것은 무엇인가요?",
        "AI 업계의 최근 변화 가운데 AIIT가 가장 주목해야 할 흐름은 무엇이라고 생각하시나요?",
    ],
    "resume": [
        "가장 기억에 남는 프로젝트 하나를 골라 본인이 맡은 역할을 설명해 주세요.",
        "프로젝트에서 가장 어려웠던 기술 문제와 해결 방법을 설명해 주세요.",
        "이력서에 적은 기술 가운데 가장 자신 있는 것을 실제로 어떻게 써 보셨나요?",
        "지금까지의 경험이 AI/AX 엔지니어 직무와 어떻게 이어진다고 생각하시나요?",
        "프로젝트에서 데이터를 모으고 정리할 때 무엇을 가장 신경 쓰셨나요?",
        "프로젝트 결과를 어떤 기준으로 평가하셨나요?",
        "팀 프로젝트에서 본인의 판단으로 방향을 바꾼 일이 있다면 그 이유는 무엇인가요?",
        "이전 프로젝트를 다시 한다면 무엇을 다르게 하고 싶으신가요?",
        "AI나 자동화로 일을 줄여 본 사례를 설명해 주세요.",
        "프로젝트에서 쓴 모델이나 도구를 고른 이유는 무엇인가요?",
    ],
    "job": [
        "과적합이 생기는 원인과 이를 줄이는 방법은 무엇인가요?",
        "RAG는 무엇이고, 파인튜닝보다 RAG가 나은 경우는 언제인가요?",
        "LLM이 사실과 다른 답을 만드는 환각을 줄이는 방법에는 무엇이 있나요?",
        "벡터 검색에서 문서를 나누는 크기는 무엇을 기준으로 정하나요?",
        "분류 모델을 평가할 때 정확도만 보면 안 되는 경우는 언제인가요?",
        "학습 데이터와 실제 데이터의 분포가 달라지면 어떤 문제가 생기나요?",
        "모델을 배포한 뒤 성능이 떨어지는 것을 알아채려면 무엇을 지켜봐야 하나요?",
        "프롬프트 인젝션이란 무엇이고 어떻게 막을 수 있나요?",
        "큰 모델을 작은 GPU에서 돌리기 위한 경량화 방법에는 무엇이 있나요?",
        "파이썬에서 리스트와 제너레이터의 차이는 무엇이고 언제 제너레이터를 쓰나요?",
    ],
}


# 다른 회사 이름이 들어간 질문과 면접과 무관한 글 (CONFLICTS F4-2, U1 '한 기업 전용'). 걸리면 예비 질문에 넣지 않는다.
# 네이버는 AIIT 의 모티프라 프로젝트를 옮겨 적을 때 이름이 남을 수 있다 — 질문에 남아 있으면 뺀다 (C-20, C-21).
# 기술 이름(TensorFlow·AWS·Amazon SageMaker 등)은 회사 제품이어도 기술 지식 질문이라 남긴다.
OTHER_COMPANY = re.compile(
    r"(?<![A-Za-z])(Stripe|SAP|Coinbase|Chime|SoFi|NVIDIA|Robinhood|Netflix|Goldman Sachs|Glider AI|Morgan Stanley|PayPal|"
    r"Mastercard|IBM|JPMorgan|JPMC|Facebook|Reddit|Google|LeetCode|Bing|Wells Fargo|Accredian|Capital One|American Express|"
    r"Dropbox|Codility|Citi|Interview Query|Uber|Airbnb|Microsoft|LinkedIn|Twitter|Tesla)(?![A-Za-z])"
    r"|(?<![A-Za-z-])Square(?![A-Za-z-])"  # Chi-Square 는 남긴다
    r"|(?<![A-Za-z])Amazon(?!\s[A-Z])"  # Amazon SageMaker 같은 서비스 이름은 남긴다
    r"|(?<![A-Za-z])(Shell|Visa|Meta|Apple)(?=[가-힣])"  # shell 스크립트·메타데이터와 구분
    r"|네이버|NAVER|아마존|구글|넷플릭스|페이스북|우버|에어비앤비|마이크로소프트|트위터|링크드인|테슬라|골드만|엔비디아|애플(?!리케이션)"
)
UNRELATED = re.compile(r"연봉|자격증을 받|W3Schools|채용 공고가 있나요|과정을 완료하면")


def excludedReason(text: str) -> str | None:
    if OTHER_COMPANY.search(text or ""):
        return "other_company"
    if UNRELATED.search(text or ""):
        return "unrelated"
    return None


def normalizeText(text: str) -> str:
    return re.sub(r"[\s\W_]+", "", text or "").lower()


def newReserve(kind: str, text: str, category: str, jobCode: str | None) -> Question:
    return Question(source="reserve", kind=kind, category=category, text=text, status="active", answer_seconds=90,
                    eval_items=EVAL_ITEMS_BY_KIND[kind], duplicate_group=normalizeText(text)[:128], job_code=jobCode)


def seedReserve(db: Session) -> int:
    """기본 질문 40개를 넣는다. 예비 질문이 하나라도 있으면 넣지 않는다 (관리자가 지운 기본 질문이 되살아나지 않게)."""
    if db.query(Question.id).filter(Question.source == "reserve").first():
        return 0
    count = 0
    for kind, texts in RESERVE_QUESTIONS.items():
        for text in texts:
            db.add(newReserve(kind, text, SEED_CATEGORY, DEFAULT_JOB_CODE if kind == "job" else None))
            count += 1
    db.commit()
    return count


def deleteQuestions(db: Session, ids: list[int]) -> int:
    """질문을 지운다. 이미 낸 면접 질문의 출처 표시는 비운다 (면접 기록은 그대로)."""
    if not ids:
        return 0
    db.query(InterviewQuestion).filter(InterviewQuestion.source_question_id.in_(ids)).update(
        {"source_question_id": None}, synchronize_session=False)
    db.query(QuestionUsage).filter(QuestionUsage.question_id.in_(ids)).delete(synchronize_session=False)
    return db.query(Question).filter(Question.id.in_(ids)).delete(synchronize_session=False)


def resetQuestions(db: Session) -> dict:
    """엑셀·AI 생성·예전 예비 질문을 모두 지우고 기본 질문 40개를 넣는다 (manage reset_questions, 2026-11-16 사용자 요청)."""
    ids = [i for (i,) in db.query(Question.id)]
    deleted = deleteQuestions(db, ids)
    db.add(AuditLog(action="question.reset", target="questions", detail={"deleted": deleted}))
    db.commit()
    return {"deleted": deleted, "seeded": seedReserve(db)}


def reserveCount(db: Session, kind: str) -> int:
    return db.query(Question.id).filter(Question.source == "reserve", Question.kind == kind).count()


def isKnown(db: Session, text: str) -> bool:
    return db.query(Question.id).filter(Question.duplicate_group == normalizeText(text)[:128]).first() is not None


def saveReserve(db: Session, kind: str, text: str, vector: list[float] | None, category: str,
                jobCode: str | None = None) -> Question | None:
    """AI 가 만든 질문을 예비 질문으로 넣는다. 넣지 않으면 None: 다른 회사·무관한 글, 같은 글, 종류별 상한,
    같은 종류 예비 질문과 0.8 이상 비슷함 (벡터가 있을 때). 개인 정보 검사는 부르는 쪽이 한다."""
    if kind not in RESERVE_KINDS or excludedReason(text) or isKnown(db, text):
        return None
    if reserveCount(db, kind) >= RESERVE_LIMIT_PER_KIND:
        return None
    vectorsOn = vector is not None and rag.supported(db)
    if vectorsOn and rag.maxStoredSimilarity(db, kind, vector) >= rag.RESERVE_DUPLICATE_SIMILARITY:
        return None
    question = newReserve(kind, text, category, jobCode)
    db.add(question)
    db.flush()
    if vectorsOn:
        rag.storeVector(db, question.id, vector)
    return question
