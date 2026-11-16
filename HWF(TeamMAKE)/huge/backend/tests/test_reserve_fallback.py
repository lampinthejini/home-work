"""예비 질문이 바닥났을 때 같은 문장이 여러 자리에 들어가지 않는다 (E11)."""

from datetime import timedelta

from app.models import Application, JobPosting, Question, User
from app.services import question_compose as qc
from app.timeutil import now


def test_lastResortNeverRepeatsWithinOneInterview():
    chosen = []
    for _ in range(len(qc.SLOT_ORDER)):
        chosen.append({"text": qc.lastResort(chosen)})
    assert len({c["text"] for c in chosen}) == len(qc.SLOT_ORDER)


def test_reserveWithoutGroupIsNotPickedTwice(sessionFactory):
    with sessionFactory() as db:
        user = User(email="kim@example.com", password_hash="x", name="김지원", role="applicant")
        posting = JobPosting(status="published", title="AI/AX 엔지니어", close_at=now() + timedelta(days=3), contact_email="r@example.com")
        db.add_all([user, posting, Question(source="reserve", kind="job", text="예비 질문 하나"),
                    Question(source="reserve", kind="job", text="예비 질문 둘")])
        db.flush()
        app = Application(user_id=user.id, posting_id=posting.id, attempt_status="ready", resume_snapshot={})
        db.add(app)
        db.commit()
        ctx = {"usedGroups": set(), "usedIds": set()}
        first = qc.bankFallback(db, app, "job", [], ctx)
        ctx["usedIds"].add(first.id)
        second = qc.bankFallback(db, app, "job", [{"text": first.text}], ctx)
        assert second is not None and second.id != first.id
        ctx["usedIds"].add(second.id)
        assert qc.bankFallback(db, app, "job", [{"text": first.text}, {"text": second.text}], ctx) is None
