"""로그인 실패 IP 차단: 계정과 무관하게 같은 IP 5회 실패면 막고, 관리자 해제 또는 24시간 뒤 풀린다."""

from dataclasses import replace
from datetime import timedelta
from types import SimpleNamespace

import pytest
from conftest import ADMIN_PASSWORD, APPLICANT_PASSWORD, signup

from app.crypto import ipHash
from app.models import AuditLog, LoginBlock, User
from app.services import login_block
from app.timeutil import now

IP = "203.0.113.7"
OTHER_IP = "198.51.100.9"
ADMIN = "admin@huge.local"
WRONG = "Wrong#Pass2026"


@pytest.fixture(autouse=True)
def trustHeader(monkeypatch):
    """시험에서는 frontend 를 거친 요청처럼 X-Forwarded-For 로 IP 를 정한다."""
    monkeypatch.setattr(login_block, "isTrustedProxy", lambda _peer: True)


def attempt(client, email="kim@example.com", password=WRONG, ip=IP):
    return client.post("/auth/login", json={"email": email, "password": password}, headers={"X-Forwarded-For": ip})


def failFiveTimes(client, ip=IP):
    results = [attempt(client, email=f"nobody{i}@example.com", ip=ip) for i in range(5)]
    return results[-1]


def rowOf(db, ip=IP):
    return db.get(LoginBlock, ipHash(ip))


def test_fiveFailuresBlockRegardlessOfAccount(client):
    signup(client)
    res = failFiveTimes(client)
    assert res.status_code == 429 and res.json()["code"] == "LOGIN_BLOCKED"
    right = attempt(client, password=APPLICANT_PASSWORD)  # 맞는 비밀번호도 막힌다
    assert right.status_code == 429 and right.json()["message"] == res.json()["message"]


def test_otherIpIsNotAffected(client):
    signup(client)
    failFiveTimes(client)
    assert attempt(client, password=APPLICANT_PASSWORD, ip=OTHER_IP).status_code == 200


def test_applicantAccountCannotBeLockedOnPurpose(client):
    signup(client)
    for i in range(12):
        assert attempt(client, ip=f"192.0.2.{i}").status_code == 401
    assert attempt(client, password=APPLICANT_PASSWORD, ip=OTHER_IP).status_code == 200


def test_responsesDoNotRevealWhetherAccountExists(client):
    signup(client)
    known = [attempt(client, ip=IP) for _ in range(5)]
    unknown = [attempt(client, email="ghost@example.com", ip=OTHER_IP) for _ in range(5)]
    assert [r.status_code for r in known] == [r.status_code for r in unknown] == [401, 401, 401, 401, 429]
    assert known[0].json() == unknown[0].json()


def test_successDoesNotClearFailures(client):
    signup(client)
    for _ in range(4):
        attempt(client)
    assert attempt(client, password=APPLICANT_PASSWORD).status_code == 200
    assert attempt(client).status_code == 429


def test_oldFailuresFallOutOfWindow(client, sessionFactory):
    for _ in range(4):
        attempt(client)
    with sessionFactory() as db:
        rowOf(db).window_started_at = now() - timedelta(minutes=61)
        db.commit()
    assert attempt(client).status_code == 401
    with sessionFactory() as db:
        assert rowOf(db).fail_count == 1


def test_blockReleasesItselfAfterADay(client, sessionFactory):
    signup(client)
    failFiveTimes(client)
    with sessionFactory() as db:
        assert timedelta(hours=23) < rowOf(db).blocked_until.replace(tzinfo=None) - now().replace(tzinfo=None) <= timedelta(hours=24)
        rowOf(db).blocked_until = now() - timedelta(seconds=1)
        db.commit()
    assert attempt(client, password=APPLICANT_PASSWORD).status_code == 200
    assert attempt(client).status_code == 401  # 새로 센다


def test_adminPassesBlockOnlyWithRightPassword(client, sessionFactory):
    failFiveTimes(client)
    assert attempt(client, email=ADMIN).status_code == 429
    with sessionFactory() as db:
        assert db.query(User).filter_by(email=ADMIN).one().failed_logins == 1  # 틀린 시도는 그대로 센다
    assert attempt(client, email=ADMIN, password=ADMIN_PASSWORD).status_code == 200


def test_adminAccountStillLocksForTenMinutes(client, sessionFactory):
    for i in range(5):
        attempt(client, email=ADMIN, ip=f"192.0.2.{i}")
    res = attempt(client, email=ADMIN, password=ADMIN_PASSWORD, ip=OTHER_IP)
    plain = attempt(client, email="ghost@example.com", ip="192.0.2.100")
    assert res.status_code == 401 and res.json() == plain.json()  # 잠김을 따로 알리지 않는다
    with sessionFactory() as db:
        db.query(User).filter_by(email=ADMIN).one().locked_until = now() - timedelta(seconds=1)
        db.commit()
    assert attempt(client, email=ADMIN, password=ADMIN_PASSWORD, ip=OTHER_IP).status_code == 200


def test_exemptIpIsNeverBlocked(client, monkeypatch, sessionFactory):
    monkeypatch.setattr(login_block, "ENV", replace(login_block.ENV, loginExemptIps="203.0.113.0/24, 10.0.0.1"))
    signup(client)
    assert failFiveTimes(client).status_code == 401
    assert attempt(client, password=APPLICANT_PASSWORD).status_code == 200
    with sessionFactory() as db:
        assert rowOf(db) is None


def test_exemptDoesNotCoverOtherIps(monkeypatch):
    monkeypatch.setattr(login_block, "ENV", replace(login_block.ENV, loginExemptIps="10.0.0.1,잘못된값"))
    assert login_block.isExempt("10.0.0.1")
    assert not login_block.isExempt("10.0.0.2") and not login_block.isExempt("unknown")


def request(peer, forwarded=None):
    return SimpleNamespace(client=SimpleNamespace(host=peer), headers={"x-forwarded-for": forwarded} if forwarded else {})


def test_clientIpTrustsHeaderOnlyFromProxy(monkeypatch):
    monkeypatch.setattr(login_block, "isTrustedProxy", lambda peer: peer == "172.18.0.3")
    assert login_block.clientIp(request("172.18.0.1", "1.2.3.4")) == "172.18.0.1"  # api 포트로 바로 온 요청
    assert login_block.clientIp(request("172.18.0.3", "1.2.3.4")) == "1.2.3.4"
    assert login_block.clientIp(request("172.18.0.3", "9.9.9.9, 1.2.3.4")) == "1.2.3.4"  # 가장 가까운 프록시가 적은 값
    assert login_block.clientIp(request("172.18.0.3", "::ffff:172.18.0.1")) == "172.18.0.1"
    assert login_block.clientIp(request("172.18.0.3", "garbage")) == "unknown"
    assert login_block.clientIp(request("172.18.0.3")) == "172.18.0.3"  # 앞단 프록시 없는 이 PC 안 접속


def test_rawIpIsNotStored(client, sessionFactory):
    failFiveTimes(client)
    with sessionFactory() as db:
        row = rowOf(db)
        assert IP not in row.ip_hash and len(row.ip_hash) == 64
        audit = db.query(AuditLog).filter_by(action="login_block.block").one()
        assert IP not in str(audit.detail) and audit.target == row.code


def test_adminSeesAndReleasesBlock(client, adminClient, sessionFactory):
    failFiveTimes(client)
    with sessionFactory() as db:
        code = rowOf(db).code
    blocks = adminClient.get("/admin/ops-status").json()["login_blocks"]
    assert [b["code"] for b in blocks] == [code] and blocks[0]["fail_count"] == 5
    assert IP not in str(blocks)
    assert adminClient.post("/admin/login-blocks/NOSUCH/release").status_code == 404
    assert adminClient.post(f"/admin/login-blocks/{code}/release").status_code == 204
    assert adminClient.get("/admin/ops-status").json()["login_blocks"] == []
    with sessionFactory() as db:
        assert db.query(AuditLog).filter_by(action="login_block.release", target=code).count() == 1


def test_applicantCannotRelease(client):
    signup(client)
    assert attempt(client, password=APPLICANT_PASSWORD, ip=OTHER_IP).status_code == 200
    assert client.post("/admin/login-blocks/ABC123/release").status_code == 403


def test_expiredRowsArePurged(client, sessionFactory):
    failFiveTimes(client)
    attempt(client, ip=OTHER_IP)
    third = "192.0.2.50"
    attempt(client, ip=third)
    with sessionFactory() as db:
        rowOf(db).blocked_until = now() - timedelta(seconds=1)
        rowOf(db, OTHER_IP).window_started_at = now() - timedelta(minutes=61)
        assert login_block.purgeExpired(db) == 2
        db.commit()
        assert rowOf(db) is None and rowOf(db, OTHER_IP) is None and rowOf(db, third) is not None


def test_messageGivesCodeAndNoEmail(client, sessionFactory):
    message = failFiveTimes(client).json()["message"]
    with sessionFactory() as db:
        code = rowOf(db).code
    assert code in message and "담당자에게 알려 주세요" in message
    assert "@" not in message


def test_contactEmailSettingIsGone(adminClient):
    assert adminClient.put("/admin/settings/login_contact_email", json={"value": "help@example.com"}).status_code == 404
    assert "login_contact_email" not in adminClient.get("/admin/settings").json()
