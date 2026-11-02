"""질문 10개 안에 같은 질문이 두 번 나오지 않게 하는 비교."""

from app.services.question_compose import isRepeat, sameText


def test_sameTextIgnoresSpacingAndPunctuation():
    assert sameText("휴지테크에 입사하고 싶은 이유는 무엇인가요?", "휴지테크에 입사하고 싶은 이유는  무엇인가요")
    assert not sameText("휴지테크에 입사하고 싶은 이유는 무엇인가요?", "휴지테크에서 하고 싶은 일은 무엇인가요?")


def test_isRepeatChecksAllChosen():
    chosen = [{"text": "GPU란 무엇인가요?"}, {"text": "휴지테크에 입사하고 싶은 이유는 무엇인가요?"}]
    assert isRepeat("휴지테크에 입사하고 싶은 이유는 무엇인가요", chosen)
    assert not isRepeat("이상치는 어떻게 처리하나요?", chosen)


def test_otherCompanyAndUnrelatedQuestionsExcluded():
    from app.services.question_bank import excludedReason
    for text in ("왜 Goldman Sachs인가요?", "SAP에 적합한 이유는 무엇인가요?", "Square의 결제 처리 데이터에서 부정거래를 탐지하려면?",
                 "아마존 고객을 위한 추천 시스템을 어떻게 설계하시겠습니까?", "구글의 데이터 사이언티스트는 무엇을 하나요?",
                 "Shell에서 일하고 싶은 이유는 무엇인가요?", "NVIDIA 데이터 사이언티스트의 일반적인 업무는 무엇인가요?",
                 "교육기관, 팀 또는 기업으로서 W3Schools 서비스를 어떻게 이용하나요?", "기대하는 연봉은 얼마인가요?",
                 "이 과정을 완료하면 어떻게 자격증을 받을 수 있나요?", "Glider AI는 데이터 사이언티스트 채용에 어떻게 도움이 되나요?"):
        assert excludedReason(text), text
    for text in ("빅데이터 애플리케이션에서 데이터 보안을 보장하려면?", "모델에 메타파라미터가 있나요?", "카이제곱(Chi-Square) 검정을 설명해 주세요.",
                 "AWS에서 리소스 배포를 자동화하려면?", "Amazon SageMaker 로 모델을 배포하는 과정을 설명해 주세요.",
                 "employees 테이블에서 총 급여를 구하는 SQL 쿼리를 작성하세요.", "Pandas 데이터프레임을 정의하세요.",
                 "TensorFlow 와 PyTorch 의 차이는 무엇인가요?", "shell 스크립트로 로그를 정리하는 방법은?"):
        assert excludedReason(text) is None, text


def test_loadMarksExistingCompanyQuestionsExcluded(sessionFactory):
    from app.models import Question
    from app.services import question_bank
    with sessionFactory() as db:
        db.add_all([Question(source="excel", kind="company", text="Visa에 입사하고 싶은 이유는 무엇인가요?", status="active"),
                    Question(source="excel", kind="company", text="우리 회사에 지원한 이유는 무엇인가요?", status="active")])
        db.commit()
        assert question_bank.excludeOtherCompanies(db) == 1
        assert [q.status for q in db.query(Question).order_by(Question.id)] == ["excluded", "active"]
