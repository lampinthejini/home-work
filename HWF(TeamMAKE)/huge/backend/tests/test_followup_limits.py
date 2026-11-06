"""꼬리질문 상한 (INT-06): 질문당 1개, 질문 종류별 1개, 전체 4개. 앞 질문이 상한을 다 써서 직무 질문이 빠지는 일을 막는다."""

from test_evaluation import makeApplication

from app.domain import status as st
from app.interview import engine as en
from app.models import Application, InterviewQuestion

SLOTS = ["personality", "company", "resume", "resume", "job", "job", "job", "job", "personality", "company"]


def addQuestion(db, appId: str, seq: int, qtype: str, kind: str = "base") -> InterviewQuestion:
    row = InterviewQuestion(application_id=appId, seq=seq, kind=kind, answer_order=1 if kind == "base" else 2, qtype=qtype,
                            text="질문", source="generated", answer_sec=90, eval_items=[])
    db.add(row)
    db.flush()
    return row


def setUp(sessionFactory):
    appId = makeApplication(sessionFactory, status=st.INTERVIEWING)
    db = sessionFactory()
    db.query(InterviewQuestion).filter_by(application_id=appId).delete()
    rows = [addQuestion(db, appId, seq, qtype) for seq, qtype in enumerate(SLOTS, start=1)]
    db.commit()
    return db, db.get(Application, appId), rows


def giveFollowup(db, app, base):
    addQuestion(db, app.id, base.seq, base.qtype, kind="follow_up")
    app.followup_count += 1
    db.commit()


def test_oneFollowupPerQuestionType(sessionFactory):
    db, app, rows = setUp(sessionFactory)
    giveFollowup(db, app, rows[2])  # 3번 이력서
    assert en.followupLimitCause(db, app, rows[3], 4) == "type_limit"  # 4번 이력서
    assert en.followupLimitCause(db, app, rows[4], 4) is None  # 5번 직무
    db.close()


def test_earlyQuestionsCannotUseUpJobFollowup(sessionFactory):
    db, app, rows = setUp(sessionFactory)
    given = []
    for base in rows:
        if en.followupLimitCause(db, app, base, 4) is None:
            giveFollowup(db, app, base)
            given.append(base.seq)
    assert given == [1, 2, 3, 5]  # 인성·회사·이력서·직무에서 하나씩
    db.close()


def test_sameQuestionGetsOnlyOneFollowup(sessionFactory):
    db, app, rows = setUp(sessionFactory)
    giveFollowup(db, app, rows[4])
    assert en.followupLimitCause(db, app, rows[4], 4) == "per_question_limit"
    db.close()


def test_totalLimitStillApplies(sessionFactory):
    db, app, rows = setUp(sessionFactory)
    app.followup_count = 4
    db.commit()
    assert en.followupLimitCause(db, app, rows[4], 4) == "total_limit"
    db.close()
