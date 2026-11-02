from conftest import ADMIN_PASSWORD, APPLICANT_PASSWORD, login, signup

AGREE = {"age_14_plus": True, "terms": True, "privacy": True}


def test_signupThenLoginRedirectsToJobs(client):
    signup(client)
    body = login(client, "kim@example.com", APPLICANT_PASSWORD)
    assert body["role"] == "applicant"
    assert body["redirect"] == "/jobs"
    assert client.get("/auth/me").json()["email"] == "kim@example.com"


def test_duplicateEmailRejected(client):
    signup(client)
    res = client.post("/auth/signup", json={"name": "다른", "email": "KIM@example.com", "password": APPLICANT_PASSWORD,
                                            "phone": "010-1111-2222", "agreements": AGREE})
    assert res.status_code == 409
    assert res.json()["code"] == "EMAIL_TAKEN"


def test_weakPasswordRejected(client):
    res = client.post("/auth/signup", json={"name": "김", "email": "a@b.co", "password": "short", "phone": "010-1111-2222",
                                            "agreements": AGREE})
    assert res.status_code == 400
    assert res.json()["code"] == "PASSWORD_POLICY"


def test_unknownFieldRejected(client):
    res = client.post("/auth/login", json={"email": "a@b.co", "password": "x", "role": "admin"})
    assert res.status_code == 422


def test_wrongPasswordFiveTimesLocksAccount(client):
    signup(client)
    for _ in range(4):
        assert client.post("/auth/login", json={"email": "kim@example.com", "password": "Wrong#Pass2026"}).status_code == 401
    res = client.post("/auth/login", json={"email": "kim@example.com", "password": "Wrong#Pass2026"})
    assert res.status_code == 423
    res = client.post("/auth/login", json={"email": "kim@example.com", "password": APPLICANT_PASSWORD})
    assert res.status_code == 423


def test_externalNextIsIgnored(client):
    signup(client)
    res = client.post("/auth/login", json={"email": "kim@example.com", "password": APPLICANT_PASSWORD, "next": "//evil.example"})
    assert res.json()["redirect"] == "/jobs"
    res = client.post("/auth/login", json={"email": "kim@example.com", "password": APPLICANT_PASSWORD, "next": "/mypage"})
    assert res.json()["redirect"] == "/mypage"


def test_applicantCannotUseAdminApi(client):
    signup(client)
    login(client, "kim@example.com", APPLICANT_PASSWORD)
    assert client.get("/admin/postings").status_code == 403


def test_adminMustChangeInitialPassword(client, sessionFactory):
    from app.models import User

    with sessionFactory() as db:
        admin = db.query(User).filter_by(role="admin").one()
        admin.must_change_password = True
        db.commit()
    body = login(client, "admin@huge.local", ADMIN_PASSWORD)
    assert body["redirect"] == "/password/change"
    assert client.get("/admin/postings").json()["code"] == "PASSWORD_CHANGE_REQUIRED"
    res = client.post("/auth/password-change", json={"current_password": ADMIN_PASSWORD, "new_password": "Brand#New2026"})
    assert res.status_code == 204
    assert client.get("/admin/postings").status_code == 200


def test_logoutDropsSession(client):
    signup(client)
    login(client, "kim@example.com", APPLICANT_PASSWORD)
    assert client.post("/auth/logout").status_code == 204
    assert client.get("/auth/me").status_code == 401
