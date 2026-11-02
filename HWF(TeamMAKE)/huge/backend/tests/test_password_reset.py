"""비밀번호 찾기·재설정 (화면정의서 S-C03, API 명세서 3장, 테이블 정의서 5장 pw_reset)."""

import pytest
from conftest import APPLICANT_PASSWORD, login, signup

from app import worker
from app.security import tokenHash
from app.services import admission

NEW_PASSWORD = "Fresh#Pass2027"


@pytest.fixture()
def mails(monkeypatch):
    sent = []
    monkeypatch.setattr(worker, "queueResetMail", lambda email, link: sent.append((email, link)))
    return sent


def tokenOf(link: str) -> str:
    return link.split("token=")[1]


def test_unknownEmailLooksTheSameAndSendsNothing(client, mails):
    res = client.post("/auth/password-reset", json={"email": "nobody@example.com"})
    assert res.status_code == 202 and mails == []


def test_resetLinkChangesPasswordOnceAndDropsSessions(client, mails):
    signup(client)
    login(client, "kim@example.com", APPLICANT_PASSWORD)
    assert client.post("/auth/password-reset", json={"email": " KIM@example.com "}).status_code == 202
    assert len(mails) == 1 and mails[0][0] == "kim@example.com" and "/password/reset?token=" in mails[0][1]
    token = tokenOf(mails[0][1])
    assert admission.redisClient().exists(f"pw_reset:{tokenHash(token)}")
    assert not admission.redisClient().exists(f"pw_reset:{token}")  # 원래 토큰이 아니라 해시로 키를 만든다

    res = client.post("/auth/password-reset/confirm", json={"token": token, "new_password": NEW_PASSWORD})
    assert res.status_code == 204, res.text
    assert client.get("/auth/me").status_code == 401  # 다른 로그인은 모두 끊는다
    login(client, "kim@example.com", NEW_PASSWORD)
    again = client.post("/auth/password-reset/confirm", json={"token": token, "new_password": "Other#Pass2028"})
    assert again.status_code == 400 and again.json()["code"] == "TOKEN_EXPIRED"


def test_policyFailureKeepsToken(client, mails):
    signup(client)
    client.post("/auth/password-reset", json={"email": "kim@example.com"})
    token = tokenOf(mails[0][1])
    weak = client.post("/auth/password-reset/confirm", json={"token": token, "new_password": "short"})
    assert weak.status_code == 400 and weak.json()["code"] == "PASSWORD_POLICY"
    assert client.post("/auth/password-reset/confirm", json={"token": token, "new_password": NEW_PASSWORD}).status_code == 204


def test_unknownOrExpiredTokenRejected(client, mails):
    signup(client)
    client.post("/auth/password-reset", json={"email": "kim@example.com"})
    admission.redisClient().flushall()  # 30분이 지나 Redis 에서 사라진 것과 같다
    res = client.post("/auth/password-reset/confirm", json={"token": tokenOf(mails[0][1]), "new_password": NEW_PASSWORD})
    assert res.status_code == 400 and res.json()["code"] == "TOKEN_EXPIRED"
    assert client.post("/auth/password-reset/confirm", json={"token": "x", "new_password": NEW_PASSWORD}).status_code == 400


def test_repeatedRequestsSendOneMailPerMinute(client, mails):
    signup(client)
    for _ in range(3):
        assert client.post("/auth/password-reset", json={"email": "kim@example.com"}).status_code == 202
    assert len(mails) == 1


def test_newerLinkReplacesOlder(client, mails, monkeypatch):
    signup(client)
    client.post("/auth/password-reset", json={"email": "kim@example.com"})
    admission.redisClient().delete(f"pw_reset_wait:{tokenHash('kim@example.com')}")  # 1분 지남
    client.post("/auth/password-reset", json={"email": "kim@example.com"})
    first, second = tokenOf(mails[0][1]), tokenOf(mails[1][1])
    assert client.post("/auth/password-reset/confirm", json={"token": first, "new_password": NEW_PASSWORD}).status_code == 400
    assert client.post("/auth/password-reset/confirm", json={"token": second, "new_password": NEW_PASSWORD}).status_code == 204
