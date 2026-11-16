"""운영 명령.  python -m app.manage <명령>

  init            테이블 · 직무 코드 · 관리자 계정(초기 비밀번호, 첫 로그인 때 변경 강제)
  load_questions  기본 예비 질문 40개(종류마다 10개)를 넣는다. 예비 질문이 하나라도 있으면 건너뛴다 (앱 시작 때도 한다)
  reset_questions 질문 DB 를 모두 지우고(엑셀·AI 생성·예비) 기본 예비 질문 40개를 넣은 뒤 임베딩한다 (C-20)
  embed_questions 질문 DB 의 임베딩(BGE-M3)을 만든다. 없는 것만 하므로 다시 돌려도 된다 (RAG)
  sample_posting  확인용 공고 1건(AI/AX 엔지니어, 오늘부터 14일, 코딩테스트 사용)
  load_web_questions <공고 id>  인터넷 참고 후보 질문(/data/web_questions.json)을 예비 질문으로 넣는다.
                  직무 질문은 그 공고의 직무만 (C-20). 이미 있는 글·0.8 이상 비슷한 글은 건너뛴다
"""

import os
import sys
from datetime import timedelta

from . import migrate
from .config import ENV
from .db import Base, SessionLocal, engine
from .domain.scoring import DEFAULT_WEIGHTS
from .models import EvaluationCriteria, JobPosting, User
from .security import hashPassword
from .services import company, question_bank
from .services.postings import seedJobCodes
from .timeutil import now, releaseAtFor


def init(db) -> None:
    Base.metadata.create_all(engine)
    migrate.addColumns(engine)
    seedJobCodes(db)
    if db.query(User).filter_by(role="admin").first() is None:
        if not ENV.adminInitialPassword:
            sys.exit("ADMIN_INITIAL_PASSWORD 가 비어 있습니다 (.env)")
        db.add(User(email=ENV.adminEmail.lower(), password_hash=hashPassword(ENV.adminInitialPassword), name="관리자",
                    role="admin", must_change_password=True))
        db.commit()
        print(f"관리자 계정을 만들었습니다: {ENV.adminEmail} (첫 로그인 때 비밀번호를 바꿔야 합니다)")
    else:
        print("관리자 계정이 이미 있습니다.")


def loadQuestions(db) -> None:
    print(f"seeded {question_bank.seedReserve(db)} reserve questions")


def resetQuestions(db) -> None:
    print(question_bank.resetQuestions(db))
    embedQuestions(db)


def samplePosting(db) -> None:
    admin = db.query(User).filter_by(role="admin").first()
    openAt = now().replace(hour=0, minute=0, second=0, microsecond=0)
    closeAt = (openAt + timedelta(days=14)).replace(hour=18)
    posting = JobPosting(
        status="published", source="manual", title="AI/AX 엔지니어 (신입·경력)", job_code="AI_AX", company_name=company.getProfile(db).name,
        company_intro="생성형 AI 로 기업 업무를 자동화하는 솔루션 회사입니다.",
        duties="LLM 기반 서비스 설계·개발\nRAG 파이프라인 구축과 성능 평가\n사내 AI 도입 컨설팅(AX)",
        requirements="Python 개발 경험\n머신러닝·딥러닝 기본 지식", preferred="LangChain·벡터 DB 사용 경험",
        employment_type="full_time", location="서울 강남구", headcount=2, open_at=openAt, close_at=closeAt,
        release_at=releaseAtFor(closeAt), contact_email=admin.email if admin else ENV.adminEmail, published_at=now(),
    )
    posting.criteria.append(EvaluationCriteria(version=1, weights=dict(DEFAULT_WEIGHTS), coding_enabled=True, coding_ratio=30, pass_score=70))
    db.add(posting)
    db.commit()
    print(f"확인용 공고를 만들었습니다: {posting.id}")


def embedQuestions(db) -> None:
    from .services import rag

    done = rag.indexQuestions(db)
    print(f"embedded {done} questions, total {rag.indexedCount(db)}")


def loadWebQuestions(db, postingId: str) -> None:
    from .services import posting_questions

    path = os.environ.get("WEB_QUESTIONS_PATH", "/data/web_questions.json")
    print(f"saved {posting_questions.loadWebCandidates(db, path, postingId)} reserve questions")


ARG_COMMANDS = {"load_web_questions": loadWebQuestions}
COMMANDS = {"init": init, "load_questions": loadQuestions, "reset_questions": resetQuestions, "sample_posting": samplePosting,
            "embed_questions": embedQuestions}

if __name__ == "__main__":
    if not (len(sys.argv) == 2 and sys.argv[1] in COMMANDS or len(sys.argv) == 3 and sys.argv[1] in ARG_COMMANDS):
        sys.exit(__doc__)
    session = SessionLocal()
    try:
        if sys.argv[1] in ARG_COMMANDS:
            ARG_COMMANDS[sys.argv[1]](session, sys.argv[2])
        else:
            COMMANDS[sys.argv[1]](session)
    finally:
        session.close()
