"""질문 DB 불러오기 (TRD 7-4 ①, PRD 5-5). manage.py load_questions 가 부른다.

- IT 직무 엑셀: '기업_'·'생성_' 시트. 머신러닝·딥러닝·컴퓨터 비전·데이터 사이언스·파이썬 시트만 active,
  나머지는 준비 중 직무용(status='preparing'). '코딩문제여부'가 '예'이거나 질문 글이 빈 행은 뺀다.
- 인성 엑셀: 지원동기·동기/지원 이유·조직 문화 적합성은 company, 나머지는 personality.
- 같은 (시트, 행 번호)는 다시 넣지 않는다. 같은 질문 글은 duplicate_group 으로 묶는다.
- 임베딩(BGE-M3)은 3단계에서 붙인다.
"""

import re

import openpyxl
from sqlalchemy.orm import Session

from ..domain.scoring import EVAL_ITEMS_BY_KIND
from ..models import Question

JOB_SHEET_KEYWORDS = ("머신러닝", "딥러닝", "컴퓨터 비전", "데이터 사이언", "파이썬")
COMPANY_CATEGORIES = {"지원동기", "동기/지원 이유", "조직 문화 적합성"}
PERSONALITY_SHEET = "인성질문전체"

# 종류별 예비 질문 (source='reserve', QST-05). 이력서 기반 자리는 '경험·프로젝트' 예비 질문으로 바꾼다.
# 종류별 5개 이상 (TRD 15장 T-05). '엑셀'로 표시한 줄은 질문 엑셀 2개에서 회사 이름·특정 직무가 없는 질문을 골라 옮긴 것.
RESERVE_QUESTIONS = {
    "resume": [
        "가장 기억에 남는 프로젝트 하나를 골라 본인 역할을 설명해 주세요.",
        "최근에 맡았던 일 중 가장 어려웠던 문제 하나와 해결 방법을 설명해 주세요.",
        "이력서에 적은 경험 중 가장 자신 있는 기술을 어떻게 익혔는지 설명해 주세요.",
        "과거 업무 경험과 이 직무와의 연관성을 설명해 주시겠어요?",  # 엑셀: 인성 · 자기소개/이력서
        "이전 경험에서 무엇을 배웠나요?",  # 엑셀: 인성 · 자기소개/이력서
    ],
    "job": [
        "과적합이 무엇인지와 이를 줄이는 방법 한 가지를 설명해 주세요.",
        "모델 성능을 평가할 때 정확도만 보면 안 되는 경우를 예로 들어 설명해 주세요.",
        "학습 데이터와 실제 데이터의 분포가 다를 때 생기는 문제를 설명해 주세요.",
        "파이썬에서 리스트와 튜플의 차이를 설명해 주세요.",
        "결측값을 대치하는 데 흔히 사용되는 기법들을 설명해 주시겠어요?",  # 엑셀: IT · 기업_머신러닝
        "딥러닝의 드롭아웃(dropout)이란 무엇인가요?",  # 엑셀: IT · 생성_딥러닝
    ],
    "personality": [
        "팀에서 의견이 달랐던 경험과 그때 어떻게 했는지 말씀해 주세요.",
        "실수를 했던 경험과 그 뒤에 무엇을 바꿨는지 말씀해 주세요.",
        "건설적인 피드백을 받았던 경험을 말씀해 주시겠어요? 어떻게 대처했나요?",  # 엑셀: 인성 · 피드백
        "목표 달성을 위해 다른 부서와 협업해야 했던 상황을 설명해 주세요.",  # 엑셀: 인성 · 협업/팀워크
        "비전문가에게 기술적 개념을 어떻게 설명하나요?",  # 엑셀: 인성 · 커뮤니케이션
    ],
    "company": [
        "이 회사에 지원한 이유를 말씀해 주세요.",
        "이 직무에서 이루고 싶은 목표를 말씀해 주세요.",
        "어떤 회사 문화에서 잘하시나요?",  # 엑셀: 인성 · 조직 문화 적합성
        "긍정적인 팀 환경에 어떻게 기여하나요?",  # 엑셀: 인성 · 조직 문화 적합성
        "이 직무에 대한 동기는 무엇인가요?",  # 엑셀: 인성 · 지원동기
    ],
}


# 다른 회사 이름이 들어간 질문과 면접과 무관한 글 (CONFLICTS F4-2, U1 '한 기업 전용'). 걸리면 status='excluded'.
# 기술 이름(TensorFlow·AWS·Amazon SageMaker 등)은 회사 제품이어도 기술 지식 질문이라 남긴다.
OTHER_COMPANY = re.compile(
    r"(?<![A-Za-z])(Stripe|SAP|Coinbase|Chime|SoFi|NVIDIA|Robinhood|Netflix|Goldman Sachs|Glider AI|Morgan Stanley|PayPal|"
    r"Mastercard|IBM|JPMorgan|JPMC|Facebook|Reddit|Google|LeetCode|Bing|Wells Fargo|Accredian|Capital One|American Express|"
    r"Dropbox|Codility|Citi|Interview Query|Uber|Airbnb|Microsoft|LinkedIn|Twitter|Tesla)(?![A-Za-z])"
    r"|(?<![A-Za-z-])Square(?![A-Za-z-])"  # Chi-Square 는 남긴다
    r"|(?<![A-Za-z])Amazon(?!\s[A-Z])"  # Amazon SageMaker 같은 서비스 이름은 남긴다
    r"|(?<![A-Za-z])(Shell|Visa|Meta|Apple)(?=[가-힣])"  # shell 스크립트·메타데이터와 구분
    r"|아마존|구글|넷플릭스|페이스북|우버|에어비앤비|마이크로소프트|트위터|링크드인|테슬라|골드만|엔비디아|애플(?!리케이션)"
)
UNRELATED = re.compile(r"연봉|자격증을 받|W3Schools|채용 공고가 있나요|과정을 완료하면")


def excludedReason(text: str) -> str | None:
    if OTHER_COMPANY.search(text or ""):
        return "other_company"
    if UNRELATED.search(text or ""):
        return "unrelated"
    return None


def excludeOtherCompanies(db: Session) -> int:
    """이미 넣은 엑셀 질문 중 걸리는 것을 'excluded'로 바꾼다 (load_questions 때마다 다시 확인)."""
    count = 0
    for q in db.query(Question).filter(Question.source == "excel", Question.status.in_(("active", "preparing"))):
        if excludedReason(q.text):
            q.status = "excluded"
            count += 1
    db.commit()
    return count


def normalizeText(text: str) -> str:
    return re.sub(r"[\s\W_]+", "", text or "").lower()


def cell(row: tuple, header: list[str], name: str):
    try:
        return row[header.index(name)]
    except (ValueError, IndexError):
        return None


def existingKeys(db: Session) -> set[tuple[str, int]]:
    return {(s, r) for s, r in db.query(Question.sheet, Question.row_no).filter(Question.sheet.isnot(None))}


def loadItQuestions(db: Session, path: str, keys: set) -> dict:
    stats = {"inserted": 0, "skipped_coding": 0, "skipped_empty": 0, "duplicate_rows": 0}
    workbook = openpyxl.load_workbook(path, read_only=True)
    for sheetName in workbook.sheetnames:
        if not sheetName.startswith(("기업_", "생성_")):
            continue
        rows = list(workbook[sheetName].iter_rows(values_only=True))
        if not rows:
            continue
        header = [str(h).strip() if h is not None else "" for h in rows[0]]
        active = any(k in sheetName for k in JOB_SHEET_KEYWORDS)
        for rowNo, row in enumerate(rows[1:], start=2):
            text = (cell(row, header, "질문(한글)") or "").strip()
            if not text:
                stats["skipped_empty"] += 1
                continue
            if (cell(row, header, "코딩문제여부") or "").strip() == "예":
                stats["skipped_coding"] += 1
                continue
            if (sheetName, rowNo) in keys:
                stats["duplicate_rows"] += 1
                continue
            category = cell(row, header, "분야") or cell(row, header, "직무") or sheetName.split("_", 1)[1]
            db.add(Question(
                source="excel", kind="job", category=str(category), text=text, sheet=sheetName, row_no=rowNo,
                duplicate_group=normalizeText(text)[:128],
                status="excluded" if excludedReason(text) else "active" if active else "preparing",
                answer_seconds=90, eval_items=EVAL_ITEMS_BY_KIND["job"],
            ))
            stats["inserted"] += 1
    return stats


def loadPersonalityQuestions(db: Session, path: str, keys: set) -> dict:
    stats = {"inserted": 0, "company": 0, "personality": 0, "skipped_empty": 0}
    workbook = openpyxl.load_workbook(path, read_only=True)
    sheet = workbook.worksheets[0]
    rows = list(sheet.iter_rows(values_only=True))
    header = [str(h).strip() if h is not None else "" for h in rows[0]]
    for rowNo, row in enumerate(rows[1:], start=2):
        text = (cell(row, header, "질문(한글)") or "").strip()
        if not text:
            stats["skipped_empty"] += 1
            continue
        if (sheet.title, rowNo) in keys:
            continue
        category = (cell(row, header, "카테고리") or "").strip()
        kind = "company" if category in COMPANY_CATEGORIES else "personality"
        db.add(Question(
            source="excel", kind=kind, category=category, text=text, sheet=sheet.title, row_no=rowNo,
            duplicate_group=normalizeText(text)[:128], status="excluded" if excludedReason(text) else "active", answer_seconds=90,
            eval_items=EVAL_ITEMS_BY_KIND[kind],
        ))
        stats["inserted"] += 1
        stats[kind] += 1
    return stats


def loadReserveQuestions(db: Session) -> int:
    existing = {t for (t,) in db.query(Question.text).filter(Question.source == "reserve")}
    count = 0
    for kind, texts in RESERVE_QUESTIONS.items():
        for text in texts:
            if text in existing:
                continue
            db.add(Question(source="reserve", kind=kind, category="예비", text=text, status="active",
                            answer_seconds=90, eval_items=EVAL_ITEMS_BY_KIND[kind], duplicate_group=normalizeText(text)[:128]))
            count += 1
    return count


def loadAll(db: Session, itPath: str, personalityPath: str) -> dict:
    keys = existingKeys(db)
    result = {
        "it": loadItQuestions(db, itPath, keys),
        "personality": loadPersonalityQuestions(db, personalityPath, keys),
        "reserve": loadReserveQuestions(db),
    }
    db.commit()
    result["excluded"] = excludeOtherCompanies(db)
    return result
