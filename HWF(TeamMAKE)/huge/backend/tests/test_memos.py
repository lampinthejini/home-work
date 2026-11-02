"""관리자 메모 (ADM-05, API 명세서 10장 메모, 테이블 정의서 4-21)."""

from test_evaluation import makeApplication

from app.models import AuditLog, Memo


def test_memoCreateUpdateDeleteShowsInDetail(sessionFactory, adminClient):
    appId = makeApplication(sessionFactory)
    res = adminClient.post(f"/admin/applicants/{appId}/memo", json={"body": "  2차 면접 때 RAG 경험 더 물어보기  "})
    assert res.status_code == 201, res.text
    memo = res.json()
    assert memo["body"] == "2차 면접 때 RAG 경험 더 물어보기" and memo["updated_at"] is None
    detail = adminClient.get(f"/admin/applicants/{appId}").json()
    assert [m["memo_id"] for m in detail["memos"]] == [memo["memo_id"]]

    res = adminClient.patch(f"/admin/memos/{memo['memo_id']}", json={"body": "고친 메모"})
    assert res.status_code == 200 and res.json()["body"] == "고친 메모" and res.json()["updated_at"]
    assert adminClient.delete(f"/admin/memos/{memo['memo_id']}").status_code == 204
    assert adminClient.get(f"/admin/applicants/{appId}").json()["memos"] == []
    with sessionFactory() as db:
        actions = [a.action for a in db.query(AuditLog).filter(AuditLog.action.like("memo.%")).order_by(AuditLog.id)]
        assert actions == ["memo.create", "memo.update", "memo.delete"]
        assert all("body" not in (a.detail or {}) for a in db.query(AuditLog).filter(AuditLog.action.like("memo.%")))


def test_memoLengthLimits(sessionFactory, adminClient):
    appId = makeApplication(sessionFactory)
    assert adminClient.post(f"/admin/applicants/{appId}/memo", json={"body": "   "}).status_code == 400
    assert adminClient.post(f"/admin/applicants/{appId}/memo", json={"body": "가" * 2001}).status_code == 422
    assert adminClient.post(f"/admin/applicants/{appId}/memo", json={"body": "가" * 2000}).status_code == 201


def test_memoUnknownTargetsAre404(sessionFactory, adminClient):
    assert adminClient.post("/admin/applicants/nope/memo", json={"body": "메모"}).status_code == 404
    assert adminClient.patch("/admin/memos/nope", json={"body": "메모"}).status_code == 404
    assert adminClient.delete("/admin/memos/nope").status_code == 404


def test_memoDeletedWithApplication(sessionFactory, adminClient):
    appId = makeApplication(sessionFactory)
    adminClient.post(f"/admin/applicants/{appId}/memo", json={"body": "메모"})
    from app.models import Application
    with sessionFactory() as db:
        db.delete(db.get(Application, appId))
        db.commit()
        assert db.query(Memo).count() == 0
