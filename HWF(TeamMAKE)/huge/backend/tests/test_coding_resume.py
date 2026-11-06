"""코딩테스트 이어가기 (COD-04, TC-085): 다시 연결되면 안내 화면 없이 저장된 코드와 남은 시간부터 이어 간다."""

from test_evaluation import makeApplication

from app.domain import status as st
from app.interview import lifecycle
from app.models import Application, CodingSubmission
from app.services import coding, coding_bank
from app.settings_store import getSetting
from app.timeutil import now


def enter(sessionFactory):
    appId = makeApplication(sessionFactory, status=st.INTERVIEWING)
    db = sessionFactory()
    app = db.get(Application, appId)
    lifecycle.enterCoding(db, app)
    return db, app


def test_firstEntryShowsIntroAndDoesNotStartTimer(sessionFactory):
    db, app = enter(sessionFactory)
    assert lifecycle.resumeCodingTimer(db, app) is False
    assert app.coding_started_at is None
    assert app.coding_remaining_sec == getSetting(db, "coding_limit_sec")
    db.close()


def test_reconnectAfterPauseSkipsIntroAndRestartsTimer(sessionFactory):
    db, app = enter(sessionFactory)
    app.coding_remaining_sec = 2400  # 40분 남기고 끊겨 pauseCodingTimer 가 멈춘 상태
    app.coding_started_at = None
    db.commit()
    assert lifecycle.resumeCodingTimer(db, app) is True
    assert app.coding_started_at is not None
    assert 2398 <= lifecycle.codingRemaining(app) <= 2400
    db.close()


def test_runningTimerIsNotRestarted(sessionFactory):
    db, app = enter(sessionFactory)
    startedAt = now()
    app.coding_started_at = startedAt
    db.commit()
    assert lifecycle.resumeCodingTimer(db, app) is True
    assert lifecycle.codingStarted(db, app) is True
    assert app.coding_remaining_sec == getSetting(db, "coding_limit_sec")
    db.close()


def test_problemViewsCarrySavedCode(sessionFactory):
    db, app = enter(sessionFactory)
    row = db.query(CodingSubmission).filter_by(application_id=app.id, problem_no=1).one()
    row.code = "# saved"
    row.saved_at = now()
    db.commit()
    views = {v["problem_no"]: v for v in coding.problemViews(db, app)}
    assert views[1]["saved_code"] == "# saved"
    assert views[1]["saved_at"] is not None
    assert views[2]["saved_code"] == coding_bank.PROBLEMS[coding_bank.pickProblems(app.id)[1]]["starter"]
    db.close()
