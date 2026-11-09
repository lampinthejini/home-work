"""동시 면접 입장 (E10). 입장은 시작 API 의 한 트랜잭션 안에서 정해져야 하고, 숫자 맞추기가 커밋 전 입장을 놓치면 안 된다."""

from test_evaluation import makeApplication

from app.domain import status as st
from app.models import Application
from app.services import admission


def test_acquireDoesNotCommitMidRequest(sessionFactory):
    """중간에 커밋하면 FOR UPDATE 잠금이 풀려 같은 시작 요청이 두 번 통과한다"""
    appId = makeApplication(sessionFactory, status=st.READY)
    with sessionFactory() as db:
        app = db.get(Application, appId)
        assert admission.tryAcquire(db, app, 1)
        db.rollback()
        assert db.get(Application, appId).holds_seat is False


def test_reconcileCountsEntranceNotYetCommitted(sessionFactory):
    """Redis 에 더한 뒤 DB 커밋 전에 숫자를 맞추면 그 자리를 빼먹어 상한을 넘겼다"""
    first = makeApplication(sessionFactory, status=st.READY, email="a@example.com")
    second = makeApplication(sessionFactory, status=st.READY, email="b@example.com")
    with sessionFactory() as db:
        assert admission.tryAcquire(db, db.get(Application, first), 1)  # 아직 커밋 안 함
        with sessionFactory() as other:
            assert admission.reconcile(other) == 1
            assert not admission.tryAcquire(other, other.get(Application, second), 1)
        db.commit()
        with sessionFactory() as other:
            assert admission.reconcile(other) == 1  # 커밋 뒤에도 두 번 세지 않는다
