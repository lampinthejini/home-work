"""예비 질문이 바닥났을 때 같은 문장이 여러 자리에 들어가지 않는다 (E11)."""

from app.models import Question
from app.services import question_compose as qc


def test_lastResortNeverRepeatsWithinOneInterview():
    chosen = []
    for _ in range(len(qc.SLOT_ORDER)):
        chosen.append({"text": qc.lastResort(chosen)})
    assert len({c["text"] for c in chosen}) == len(qc.SLOT_ORDER)


def test_reserveWithoutGroupIsNotPickedTwice(sessionFactory):
    with sessionFactory() as db:
        db.add_all([Question(source="reserve", kind="job", text="예비 질문 하나"), Question(source="reserve", kind="job", text="예비 질문 둘")])
        db.commit()
        first = qc.reserveFor(db, "job", set(), set(), [])
        second = qc.reserveFor(db, "job", set(), {first.id}, [{"text": first.text}])
        assert second is not None and second.id != first.id
        assert qc.reserveFor(db, "job", set(), {first.id, second.id}, [{"text": first.text}, {"text": second.text}]) is None
