"""머리글 🔔 알림: 목록 · 읽음 · 숨기기 (2026-11-02 사용자 결정 A: 지우지 않고 숨긴다. 메일 발송 기록은 남긴다)."""

from conftest import APPLICANT_PASSWORD, login, signup

from app.models import Notification, User
from app.timeutil import now


def addNotes(sessionFactory, email: str, read: list[bool]) -> list[str]:
    with sessionFactory() as db:
        userId = db.query(User).filter_by(email=email).first().id
        rows = [Notification(user_id=userId, kind="result_released", title=f"알림 {i}", email_status="failed",
                             read_at=now() if isRead else None) for i, isRead in enumerate(read)]
        db.add_all(rows)
        db.commit()
        ids = [r.id for r in rows]
    return ids


def test_hideOneRemovesFromListButKeepsMailRecord(client, sessionFactory):
    signup(client)
    login(client, "kim@example.com", APPLICANT_PASSWORD)
    first, second = addNotes(sessionFactory, "kim@example.com", [False, False])
    assert client.post(f"/notifications/{first}/hide").status_code == 204
    body = client.get("/notifications").json()
    assert [n["notification_id"] for n in body["items"]] == [second]
    assert body["unread"] == 1  # 숨긴 알림은 안 읽은 수에서도 빠진다
    with sessionFactory() as db:
        row = db.get(Notification, first)
        assert row.hidden_at is not None and row.email_status == "failed"


def test_hideReadHidesOnlyReadOnes(client, sessionFactory):
    signup(client)
    login(client, "kim@example.com", APPLICANT_PASSWORD)
    readId, unreadId, readId2 = addNotes(sessionFactory, "kim@example.com", [True, False, True])
    res = client.post("/notifications/hide-read")
    assert res.status_code == 200 and res.json() == {"hidden": 2}
    assert [n["notification_id"] for n in client.get("/notifications").json()["items"]] == [unreadId]


def test_cannotHideOthersNotification(client, sessionFactory):
    signup(client, "other@example.com")
    signup(client)
    (otherId,) = addNotes(sessionFactory, "other@example.com", [False])
    login(client, "kim@example.com", APPLICANT_PASSWORD)
    assert client.post(f"/notifications/{otherId}/hide").status_code == 404
    with sessionFactory() as db:
        assert db.get(Notification, otherId).hidden_at is None
