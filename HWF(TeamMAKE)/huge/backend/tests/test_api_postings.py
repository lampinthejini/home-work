from datetime import timedelta

from conftest import postingBody, publishedPosting

from app.models import Application, PostingRevision, User
from app.timeutil import now


def test_createDraftHiddenFromPublic(adminClient):
    res = adminClient.post("/admin/postings", json=postingBody())
    assert res.status_code == 201
    postingId = res.json()["posting_id"]
    assert res.json()["status"] == "draft"
    assert adminClient.get(f"/postings/{postingId}").status_code == 404
    assert adminClient.get("/postings").json()["total"] == 0


def test_publishShowsInPublicListWithCodingFlag(adminClient):
    postingId = publishedPosting(adminClient)
    listing = adminClient.get("/postings").json()
    assert listing["total"] == 1
    assert listing["items"][0]["has_coding_test"] is True
    detail = adminClient.get(f"/postings/{postingId}").json()
    assert detail["release_at"].endswith("10:00:00+09:00")


def test_codingToggleOff(adminClient):
    criteria = postingBody()["criteria"]
    criteria["coding_enabled"] = False
    postingId = publishedPosting(adminClient, criteria=criteria)
    assert adminClient.get(f"/postings/{postingId}").json()["has_coding_test"] is False


def test_weightSumMustBe100(adminClient):
    body = postingBody()
    body["criteria"]["weights"]["logic"] = 20
    res = adminClient.post("/admin/postings", json=body)
    assert res.status_code == 400
    assert res.json()["code"] == "WEIGHT_SUM"


def test_preparingJobCannotPublish(adminClient):
    postingId = adminClient.post("/admin/postings", json=postingBody(job_code="BACKEND")).json()["posting_id"]
    assert adminClient.post(f"/admin/postings/{postingId}/publish").json()["code"] == "JOB_NOT_OPEN"


def test_pastCloseCannotPublish(adminClient):
    body = postingBody(close_at=(now() - timedelta(hours=1)).isoformat(), open_at=(now() - timedelta(days=2)).isoformat())
    postingId = adminClient.post("/admin/postings", json=body).json()["posting_id"]
    assert adminClient.post(f"/admin/postings/{postingId}/publish").status_code == 400


def test_publishedEditRecordsRevisionAndLocksPeriod(adminClient, sessionFactory):
    postingId = publishedPosting(adminClient)
    res = adminClient.patch(f"/admin/postings/{postingId}", json={"title": "AI/AX 엔지니어 (경력)", "duties": "바뀐 업무"})
    assert res.status_code == 200
    summaries = {r["summary"] for r in adminClient.get(f"/postings/{postingId}").json()["revisions"]}
    assert "제목: AI/AX 엔지니어 → AI/AX 엔지니어 (경력)" in summaries
    assert "주요 업무 내용이 수정되었습니다" in summaries
    res = adminClient.patch(f"/admin/postings/{postingId}", json={"close_at": (now() + timedelta(days=30)).isoformat()})
    assert res.json()["code"] == "FIELD_LOCKED_AFTER_PUBLISH"
    with sessionFactory() as db:
        assert db.query(PostingRevision).count() == 2


def test_criteriaLockedAfterFirstAttempt(adminClient, sessionFactory):
    postingId = publishedPosting(adminClient)
    with sessionFactory() as db:
        uid = db.query(User).first().id
        db.add(Application(user_id=uid, posting_id=postingId, attempt_status="interviewing", attempt_consumed_at=now()))
        db.commit()
    criteria = postingBody()["criteria"]
    criteria["pass_score"] = 80
    res = adminClient.patch(f"/admin/postings/{postingId}", json={"criteria": criteria})
    assert res.status_code == 409
    assert res.json()["code"] == "CRITERIA_LOCKED"
    assert adminClient.get(f"/admin/postings/{postingId}").json()["criteria"]["locked"] is True


def test_closeMarksNotTaken(adminClient, sessionFactory):
    postingId = publishedPosting(adminClient)
    with sessionFactory() as db:
        uid = db.query(User).first().id
        db.add(Application(user_id=uid, posting_id=postingId, attempt_status="ready"))
        db.commit()
    res = adminClient.post(f"/admin/postings/{postingId}/close")
    assert res.status_code == 200
    assert res.json()["not_taken"] == 1
    assert adminClient.get("/postings").json()["total"] == 0
    assert adminClient.patch(f"/admin/postings/{postingId}", json={"title": "x"}).json()["code"] == "POSTING_CLOSED"
