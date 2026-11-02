from datetime import timedelta

from conftest import APPLICANT_PASSWORD, login, publishedPosting, signup

from app.models import Application, InterviewSession, SessionEvent, User
from app.routers import interview as interviewRouter
from app.services import admission
from app.timeutil import now

CONSENT = {"consent_version": "v1.3", "items": {"data_collection": True, "ai_decision": True, "share_with_admin": True,
                                                "retention": True, "exam_rules": True}}
RESUME = {"method": "manual", "resume": {
    "name": "김지원",
    "education": [{"school": "한국대학교", "major": "컴퓨터공학", "degree": "학사", "start": "2018-03", "end": "2024-02"}],
    "skills": ["Python", "PyTorch"]}}
PRECHECK = {"browser": {"name": "chrome", "version": "141"}, "devices": {"mic": True, "camera": True, "speaker": True},
            "network_mbps": "20"}


def applyReady(client, postingId):
    appId = client.post("/applications", json={"posting_id": postingId}).json()["application_id"]
    assert client.post(f"/applications/{appId}/consent", json=CONSENT).status_code == 201
    res = client.post(f"/applications/{appId}/resume", json=RESUME)
    assert res.status_code == 200, res.text
    return appId


def asApplicant(adminClient):
    postingId = publishedPosting(adminClient)
    adminClient.post("/auth/logout")
    signup(adminClient)
    login(adminClient, "kim@example.com", APPLICANT_PASSWORD)
    return adminClient, postingId


def test_applyConsentResumeMakesReady(adminClient):
    client, postingId = asApplicant(adminClient)
    appId = applyReady(client, postingId)
    assert client.get(f"/applications/{appId}").json()["attempt_status"] == "ready"
    assert client.get("/me/applications").json()["items"][0]["next_action"] == "precheck"


def test_resumeBeforeConsentRejected(adminClient):
    client, postingId = asApplicant(adminClient)
    appId = client.post("/applications", json={"posting_id": postingId}).json()["application_id"]
    assert client.post(f"/applications/{appId}/resume", json=RESUME).json()["code"] == "CONSENT_REQUIRED"


def test_partialConsentRejected(adminClient):
    client, postingId = asApplicant(adminClient)
    appId = client.post("/applications", json={"posting_id": postingId}).json()["application_id"]
    body = {"consent_version": "v1.3", "items": {**CONSENT["items"], "retention": False}}
    assert client.post(f"/applications/{appId}/consent", json=body).json()["code"] == "AGREEMENT_REQUIRED"


def test_resumeRequiresNameAndEducationOrCareer(adminClient):
    client, postingId = asApplicant(adminClient)
    appId = client.post("/applications", json={"posting_id": postingId}).json()["application_id"]
    client.post(f"/applications/{appId}/consent", json=CONSENT)
    res = client.post(f"/applications/{appId}/resume", json={"method": "manual", "resume": {"name": "김지원"}})
    assert res.status_code == 422
    assert res.json()["code"] == "RESUME_REQUIRED_MISSING"


def test_secondApplicationRejectedAndResumeLocked(adminClient):
    client, postingId = asApplicant(adminClient)
    appId = applyReady(client, postingId)
    assert client.post("/applications", json={"posting_id": postingId}).json()["code"] == "ALREADY_APPLIED"
    assert client.post(f"/applications/{appId}/resume", json=RESUME).json()["code"] == "RESUME_LOCKED"


def test_otherUsersApplicationIsNotFound(adminClient):
    client, postingId = asApplicant(adminClient)
    appId = applyReady(client, postingId)
    client.post("/auth/logout")
    signup(client, "lee@example.com")
    login(client, "lee@example.com", APPLICANT_PASSWORD)
    assert client.get(f"/applications/{appId}").status_code == 404
    assert client.get(f"/applications/{appId}/interview/state").status_code == 404


def test_startNeedsPrecheck(adminClient):
    client, postingId = asApplicant(adminClient)
    appId = applyReady(client, postingId)
    assert client.post(f"/applications/{appId}/interview/start").json()["code"] == "PRECHECK_REQUIRED"


def test_capacityFullThenStartsWhenSeatFree(adminClient, sessionFactory):
    client, postingId = asApplicant(adminClient)
    appId = applyReady(client, postingId)
    with sessionFactory() as db:
        db.get(Application, appId).precheck_valid_until = now() + timedelta(minutes=15)
        db.commit()
    admission.redisClient().set(admission.ACTIVE_KEY, 1)  # 개발 환경 N=1 이 이미 찼다
    res = client.post(f"/applications/{appId}/interview/start")
    assert res.status_code == 429
    assert res.json()["code"] == "CAPACITY_FULL"
    admission.redisClient().set(admission.ACTIVE_KEY, 0)
    res = client.post(f"/applications/{appId}/interview/start")
    assert res.status_code == 200, res.text
    assert res.json()["ws_url"].startswith("ws://127.0.0.1:8000/ws/interview/")
    assert int(admission.redisClient().get(admission.ACTIVE_KEY)) == 1
    assert client.get(f"/applications/{appId}/interview/state").json()["attempt_status"] == "interviewing"
    assert client.post(f"/applications/{appId}/interview/start").json()["code"] == "NOT_READY"


def test_precheckFailsWhenAiDown(adminClient, monkeypatch):
    async def down(*_a, **_k):
        return False

    monkeypatch.setattr(interviewRouter.llm, "health", down)
    monkeypatch.setattr(interviewRouter.speech, "serviceHealthy", down)
    client, postingId = asApplicant(adminClient)
    appId = applyReady(client, postingId)
    res = client.post(f"/applications/{appId}/precheck", json=PRECHECK)
    assert res.json()["passed"] is False
    assert res.json()["checks"]["ai_server"] == "fail"


def test_websocketRejectsForeignOrigin(adminClient):
    from starlette.websockets import WebSocketDisconnect

    client, _ = asApplicant(adminClient)
    try:
        with client.websocket_connect("/ws/interview/none", headers={"origin": "http://evil.example"}):
            raise AssertionError("connected")
    except WebSocketDisconnect as exc:
        assert exc.code == 4401


def test_beaconAcceptsTextPlainAndGarbage(adminClient, sessionFactory):
    client, postingId = asApplicant(adminClient)
    appId = applyReady(client, postingId)
    with sessionFactory() as db:
        uid = db.query(User).filter_by(email="kim@example.com").one().id
        row = InterviewSession(application_id=appId, user_id=uid)
        db.add(row)
        db.commit()
        sid = row.id
    res = client.post(f"/interview/{sid}/events", content='{"type":"unload","detail":"pagehide"}', headers={"content-type": "text/plain"})
    assert res.status_code == 204
    assert client.post(f"/interview/{sid}/events", content="not json").status_code == 204
    with sessionFactory() as db:
        assert {e.type for e in db.query(SessionEvent)} == {"unload", "beacon_unparsed"}
