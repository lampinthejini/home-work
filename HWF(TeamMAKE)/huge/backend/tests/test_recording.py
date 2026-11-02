"""카메라 녹화 (API 명세서 6장 POST /interview/{sid}/recording · 2-6 미디어, 테이블 정의서 4-10, 녹화 3일 삭제)."""

from datetime import timedelta

import pytest
from test_api_apply import applyReady, asApplicant

from app.domain import status as st
from app.models import Application, AuditLog, DeletionLog, InterviewSession, Recording
from app.services import recording, retention, storage
from app.timeutil import now

WEBM_HEAD = b"\x1a\x45\xdf\xa3" + b"head"


@pytest.fixture()
def bucket(monkeypatch):
    objects: dict[str, bytes] = {}
    monkeypatch.setattr(storage, "putObject", lambda key, data, contentType="": objects.__setitem__(key, data))
    monkeypatch.setattr(storage, "getObject", lambda key: (objects[key], "video/webm"))
    monkeypatch.setattr(storage, "listKeys", lambda prefix: sorted(k for k in objects if k.startswith(prefix)))

    def deletePrefix(prefix):
        keys = [k for k in objects if k.startswith(prefix)]
        for k in keys:
            del objects[k]
        return len(keys)
    monkeypatch.setattr(storage, "deletePrefix", deletePrefix)
    return objects


def started(adminClient, sessionFactory):
    """시작 API 를 거친 것처럼 진행 중 + 세션 1개 (녹화 구간 1)."""
    client, postingId = asApplicant(adminClient)
    appId = applyReady(client, postingId)
    with sessionFactory() as db:
        app = db.get(Application, appId)
        app.attempt_status = st.INTERVIEWING
        row = InterviewSession(application_id=appId, user_id=app.user_id, recording_segment=1)
        db.add(row)
        db.commit()
        return client, appId, row.id


def upload(client, sid, chunk, data, segment=1, phase="interview"):
    return client.post(f"/interview/{sid}/recording", data={"segment_no": segment, "chunk_no": chunk, "phase": phase},
                       files={"file": ("c.webm", data, "video/webm")})


def test_chunksStoredInOrderAndRetriesIgnored(adminClient, sessionFactory, bucket):
    client, appId, sid = started(adminClient, sessionFactory)
    assert upload(client, sid, 0, WEBM_HEAD).status_code == 204
    assert upload(client, sid, 1, b"second").status_code == 204
    assert upload(client, sid, 1, b"second").status_code == 204  # 다시 올린 조각은 한 번만 센다
    with sessionFactory() as db:
        rec = db.query(Recording).one()
        assert (rec.segment_no, rec.last_chunk_no, rec.size_bytes) == (1, 1, len(WEBM_HEAD) + len(b"second"))
        app = db.get(Application, appId)
        assert asKstDate(rec.expires_at) == asKstDate(app.posting.close_at + timedelta(days=3))
    assert sorted(bucket) == [f"recordings/{appId}/1/00000.webm", f"recordings/{appId}/1/00001.webm"]


def asKstDate(value):
    from app.timeutil import asKst
    return asKst(value).replace(microsecond=0)


def test_rejectsWrongSegmentNonWebmAndForeignSession(adminClient, sessionFactory, bucket):
    client, appId, sid = started(adminClient, sessionFactory)
    assert upload(client, sid, 0, WEBM_HEAD, segment=2).status_code == 409
    assert upload(client, sid, 0, b"<html>").status_code == 400  # 첫 조각은 WebM 머리글로 시작해야 한다
    assert upload(client, sid, 0, b"\x1a\x45\xdf\xa3" + b"x" * (6 * 1024 * 1024)).status_code == 413
    assert upload(client, "nope", 0, WEBM_HEAD).status_code == 404
    with sessionFactory() as db:
        db.get(Application, appId).attempt_status = st.COMPLETED
        db.get(Application, appId).completed_at = now() - timedelta(minutes=5)
        db.commit()
    assert upload(client, sid, 0, WEBM_HEAD).status_code == 409  # 끝난 지 오래된 응시는 받지 않는다
    assert bucket == {}


def test_lastChunkAcceptedRightAfterFinish(adminClient, sessionFactory, bucket):
    client, appId, sid = started(adminClient, sessionFactory)
    with sessionFactory() as db:
        app = db.get(Application, appId)
        app.attempt_status = st.COMPLETED
        app.completed_at = now()
        db.commit()
    assert upload(client, sid, 0, WEBM_HEAD, phase="coding").status_code == 204
    with sessionFactory() as db:  # 응시가 끝났으면 보관 기한은 끝난 시각 + 3일
        rec = db.query(Recording).one()
        assert asKstDate(rec.expires_at) == asKstDate(db.get(Application, appId).completed_at + timedelta(days=3))


def test_adminPlaysRecordingWithAuditAndExpiry(adminClient, sessionFactory, bucket):
    from conftest import ADMIN_PASSWORD, login
    client, appId, sid = started(adminClient, sessionFactory)
    upload(client, sid, 0, WEBM_HEAD)
    upload(client, sid, 1, b"tail")
    client.post("/auth/logout")
    login(client, "admin@huge.local", ADMIN_PASSWORD)
    detail = client.get(f"/admin/applicants/{appId}").json()
    assert detail["recordings"][0]["media_url"] == f"/api/admin/media/recordings/{appId}/1"
    assert detail["recording_until"]
    res = client.get(f"/admin/media/recordings/{appId}/1")
    assert res.status_code == 200 and res.content == WEBM_HEAD + b"tail" and res.headers["content-type"] == "video/webm"
    with sessionFactory() as db:
        assert db.query(AuditLog).filter_by(action="recording.play", target=appId).count() == 1
        db.query(Recording).one().expires_at = now() - timedelta(minutes=1)
        db.commit()
    expired = client.get(f"/admin/media/recordings/{appId}/1")
    assert expired.status_code == 410 and expired.json()["code"] == "MEDIA_EXPIRED"
    assert client.get(f"/admin/media/recordings/{appId}/9").status_code == 404


def test_applicantCannotPlayRecording(adminClient, sessionFactory, bucket):
    client, appId, sid = started(adminClient, sessionFactory)
    upload(client, sid, 0, WEBM_HEAD)
    assert client.get(f"/admin/media/recordings/{appId}/1").status_code == 403


def test_purgeRecordingsAfterThreeDays(adminClient, sessionFactory, bucket):
    client, appId, sid = started(adminClient, sessionFactory)
    upload(client, sid, 0, WEBM_HEAD)
    with sessionFactory() as db:
        assert retention.purgeRecordings(db) == 0
        db.query(Recording).one().expires_at = now() - timedelta(minutes=1)
        db.commit()
        assert retention.purgeRecordings(db) == 1
        assert db.query(Recording).count() == 0
        assert db.get(Application, appId) is not None  # 녹화만 지운다
        log = db.query(DeletionLog).one()
        assert (log.application_id, log.cause, log.scope, log.deleted_items["files"]) == (appId, "retention", "recording", 1)
    assert bucket == {}


def test_storageFailureIsRecordedAndCountedAsServerSide(adminClient, sessionFactory, bucket, monkeypatch):
    from app.models import SessionEvent
    client, appId, sid = started(adminClient, sessionFactory)
    with sessionFactory() as db:  # 화면이 원인을 보내도 믿지 않는다. 서버가 남긴 기록으로만 판단
        assert recording.uploadFailureReason(db, db.get(Application, appId)) == "upload_failed"

    def down(key, data, contentType=""):
        raise RuntimeError("s3 down")
    monkeypatch.setattr(storage, "putObject", down)
    res = upload(client, sid, 0, WEBM_HEAD)
    assert res.status_code == 503 and res.json()["code"] == "STORAGE_UNAVAILABLE"
    with sessionFactory() as db:
        assert db.query(SessionEvent).filter_by(application_id=appId, type="upload_error").count() == 1
        assert recording.uploadFailureReason(db, db.get(Application, appId)) == "server_error"
