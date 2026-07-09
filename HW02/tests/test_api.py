from fastapi.testclient import TestClient

from contact_app.main import app
from tests.conftest import DEFAULT_PASSWORD, login, signup


# ---- 15-1. 인증 ----

def test_tc01_signup_creates_default_categories(client, make_username):
    username = make_username()
    res = signup(client, username)
    assert res.status_code == 201
    assert res.json() == {"id": res.json()["id"], "username": username}

    login(client, username)
    categories = client.get("/categories").json()
    assert [c["name"] for c in categories] == ["가족", "친구", "기타"]


def test_tc02_duplicate_signup_returns_409(client, make_username):
    username = make_username()
    signup(client, username)
    res = signup(client, username)
    assert res.status_code == 409


def test_tc03_invalid_signup_format_returns_422(client, make_username):
    res = client.post(
        "/auth/signup",
        json={"username": "AB", "password": "pass1234", "password_confirm": "pass1234"},
    )
    assert res.status_code == 422


def test_tc04_login_success_sets_cookie(client, make_username):
    username = make_username()
    signup(client, username)
    res = login(client, username)
    assert res.status_code == 200
    assert "session_id" in res.cookies


def test_tc05_login_failure_returns_same_message(client, make_username):
    username = make_username()
    signup(client, username)

    wrong_password = client.post(
        "/auth/login", json={"username": username, "password": "wrongpass"}
    )
    nonexistent_user = client.post(
        "/auth/login", json={"username": "nosuchuser0000", "password": DEFAULT_PASSWORD}
    )

    assert wrong_password.status_code == 401
    assert nonexistent_user.status_code == 401
    assert wrong_password.json()["detail"] == nonexistent_user.json()["detail"]


def test_tc06_protected_endpoint_without_login_returns_401(client):
    res = client.get("/auth/me")
    assert res.status_code == 401


def test_tc07_logout_then_reuse_cookie_returns_401(client, make_username):
    username = make_username()
    signup(client, username)
    login(client, username)

    logout_res = client.post("/auth/logout")
    assert logout_res.status_code == 200

    me_res = client.get("/auth/me")
    assert me_res.status_code == 401


def test_tc08_session_persists_across_new_process_like_client(make_username):
    username = make_username()
    c1 = TestClient(app)
    signup(c1, username)
    login(c1, username)
    session_cookie = c1.cookies.get("session_id")

    c2 = TestClient(app)
    c2.cookies.set("session_id", session_cookie)
    res = c2.get("/auth/me")
    assert res.status_code == 200
    assert res.json()["username"] == username


# ---- 15-2. 연락처 ----

def test_tc09_create_contact_success(registered_user):
    client, _ = registered_user
    before_total = client.get("/contacts").json()["total"]

    category_id = client.get("/categories").json()[0]["id"]
    res = client.post(
        "/contacts",
        json={"name": "윤아", "phone": "01012345678", "addr": "서울시", "category_id": category_id},
    )
    assert res.status_code == 201

    after_total = client.get("/contacts").json()["total"]
    assert after_total == before_total + 1


def test_tc10_invalid_contact_format_returns_422(registered_user):
    client, _ = registered_user
    category_id = client.get("/categories").json()[0]["id"]

    res = client.post(
        "/contacts",
        json={"name": "너무긴이름입니다", "phone": "0101234", "addr": "", "category_id": category_id},
    )
    assert res.status_code == 422


def test_tc11_missing_or_foreign_category_id_returns_404(make_username):
    my_client = TestClient(app)
    my_username = make_username()
    signup(my_client, my_username)
    login(my_client, my_username)

    res = my_client.post(
        "/contacts",
        json={"name": "abc", "phone": "01099999999", "addr": "", "category_id": 999999},
    )
    assert res.status_code == 404

    other_client = TestClient(app)
    other_username = make_username()
    signup(other_client, other_username)
    login(other_client, other_username)
    other_category_id = other_client.get("/categories").json()[0]["id"]

    res = my_client.post(
        "/contacts",
        json={"name": "abc", "phone": "01099999998", "addr": "", "category_id": other_category_id},
    )
    assert res.status_code == 404


def test_tc12_duplicate_phone_within_same_user_returns_409(registered_user):
    client, _ = registered_user
    category_id = client.get("/categories").json()[0]["id"]
    payload = {"name": "abc", "phone": "01011112222", "addr": "", "category_id": category_id}

    first = client.post("/contacts", json=payload)
    second = client.post("/contacts", json=payload)
    assert first.status_code == 201
    assert second.status_code == 409


def test_tc13_same_phone_different_users_both_succeed(client, make_username):
    user_a = make_username()
    signup(client, user_a)
    login(client, user_a)
    category_a = client.get("/categories").json()[0]["id"]
    res_a = client.post(
        "/contacts",
        json={"name": "abc", "phone": "01033334444", "addr": "", "category_id": category_a},
    )
    assert res_a.status_code == 201

    user_b = make_username()
    signup(client, user_b)
    login(client, user_b)
    category_b = client.get("/categories").json()[0]["id"]
    res_b = client.post(
        "/contacts",
        json={"name": "def", "phone": "01033334444", "addr": "", "category_id": category_b},
    )
    assert res_b.status_code == 201


def test_tc14_search_by_name_returns_all_matches(registered_user):
    client, _ = registered_user
    category_id = client.get("/categories").json()[0]["id"]
    client.post(
        "/contacts",
        json={"name": "동명", "phone": "01055556666", "addr": "", "category_id": category_id},
    )
    client.post(
        "/contacts",
        json={"name": "동명", "phone": "01055556667", "addr": "", "category_id": category_id},
    )

    res = client.get("/contacts", params={"name": "동명"})
    assert res.status_code == 200
    body = res.json()
    assert body["total"] == 2
    ids = {item["id"] for item in body["items"]}
    assert len(ids) == 2


def test_tc15_search_with_no_results_returns_empty_200(registered_user):
    client, _ = registered_user
    res = client.get("/contacts", params={"name": "존재하지않는이름"})
    assert res.status_code == 200
    assert res.json() == {"total": 0, "items": []}


def test_tc16_other_users_data_is_isolated(client, make_username):
    user_a = make_username()
    signup(client, user_a)
    login(client, user_a)
    category_a = client.get("/categories").json()[0]["id"]
    contact_res = client.post(
        "/contacts",
        json={"name": "abc", "phone": "01077778888", "addr": "", "category_id": category_a},
    )
    contact_id = contact_res.json()["id"]

    user_b = make_username()
    signup(client, user_b)
    login(client, user_b)

    list_res = client.get("/contacts")
    assert all(item["id"] != contact_id for item in list_res.json()["items"])

    patch_res = client.patch(f"/contacts/{contact_id}", json={"addr": "hacked"})
    assert patch_res.status_code == 404


def test_tc17_partial_update_only_changes_given_field(registered_user):
    client, _ = registered_user
    category_id = client.get("/categories").json()[0]["id"]
    create_res = client.post(
        "/contacts",
        json={"name": "abc", "phone": "01044443333", "addr": "서울시", "category_id": category_id},
    )
    contact_id = create_res.json()["id"]

    patch_res = client.patch(f"/contacts/{contact_id}", json={"addr": "제주시"})
    assert patch_res.status_code == 200
    body = patch_res.json()
    assert body["addr"] == "제주시"
    assert body["name"] == "abc"
    assert body["phone"] == "01044443333"


def test_tc18_update_or_delete_others_contact_returns_404(client, make_username):
    user_a = make_username()
    signup(client, user_a)
    login(client, user_a)
    category_a = client.get("/categories").json()[0]["id"]
    contact_id = client.post(
        "/contacts",
        json={"name": "abc", "phone": "01022221111", "addr": "", "category_id": category_a},
    ).json()["id"]

    user_b = make_username()
    signup(client, user_b)
    login(client, user_b)

    assert client.patch(f"/contacts/{contact_id}", json={"addr": "x"}).status_code == 404
    assert client.delete(f"/contacts/{contact_id}").status_code == 404


# ---- 15-3. 카테고리 ----

def test_tc19_default_categories_after_signup(registered_user):
    client, _ = registered_user
    res = client.get("/categories")
    assert res.status_code == 200
    assert [c["name"] for c in res.json()] == ["가족", "친구", "기타"]


def test_tc20_create_category_success_and_duplicate_conflict(registered_user):
    client, _ = registered_user
    res = client.post("/categories", json={"name": "동호회"})
    assert res.status_code == 201

    dup_res = client.post("/categories", json={"name": "동호회"})
    assert dup_res.status_code == 409


def test_tc21_new_category_not_visible_to_other_account(client, make_username):
    user_a = make_username()
    signup(client, user_a)
    login(client, user_a)
    client.post("/categories", json={"name": "동호회"})

    user_b = make_username()
    signup(client, user_b)
    login(client, user_b)
    names = [c["name"] for c in client.get("/categories").json()]
    assert "동호회" not in names


def test_tc22_rename_category_updates_contact_display_name(registered_user):
    client, _ = registered_user
    category_id = client.get("/categories").json()[0]["id"]
    contact_id = client.post(
        "/contacts",
        json={"name": "abc", "phone": "01066667777", "addr": "", "category_id": category_id},
    ).json()["id"]

    rename_res = client.patch(f"/categories/{category_id}", json={"name": "베프"})
    assert rename_res.status_code == 200

    contacts = client.get("/contacts").json()["items"]
    updated = next(c for c in contacts if c["id"] == contact_id)
    assert updated["category_name"] == "베프"


def test_tc23_delete_unused_category_returns_204(registered_user):
    client, _ = registered_user
    category_id = client.post("/categories", json={"name": "임시"}).json()["id"]
    res = client.delete(f"/categories/{category_id}")
    assert res.status_code == 204


def test_tc24_delete_category_in_use_returns_409(registered_user):
    client, _ = registered_user
    category_id = client.get("/categories").json()[0]["id"]
    client.post(
        "/contacts",
        json={"name": "abc", "phone": "01098765432", "addr": "", "category_id": category_id},
    )

    res = client.delete(f"/categories/{category_id}")
    assert res.status_code == 409
    assert "건 있어 삭제할 수 없습니다" in res.json()["detail"]


# ---- 15-4. 통합 ----

def test_tc25_full_flow(client, make_username):
    username = make_username()
    assert signup(client, username).status_code == 201
    assert login(client, username).status_code == 200

    category_id = client.get("/categories").json()[0]["id"]
    create_res = client.post(
        "/contacts",
        json={"name": "abc", "phone": "01012312312", "addr": "", "category_id": category_id},
    )
    assert create_res.status_code == 201
    contact_id = create_res.json()["id"]

    assert client.patch(f"/contacts/{contact_id}", json={"addr": "부산시"}).status_code == 200
    assert client.delete(f"/contacts/{contact_id}").status_code == 204
    assert client.post("/auth/logout").status_code == 200
    assert client.get("/auth/me").status_code == 401


def test_tc26_full_isolation_between_two_accounts(client, make_username):
    user_a = make_username()
    signup(client, user_a)
    login(client, user_a)
    category_a = client.get("/categories").json()[0]["id"]
    contact_a = client.post(
        "/contacts",
        json={"name": "aaa", "phone": "01011119999", "addr": "", "category_id": category_a},
    ).json()["id"]

    user_b = make_username()
    signup(client, user_b)
    login(client, user_b)

    assert all(item["id"] != contact_a for item in client.get("/contacts").json()["items"])
    assert client.get("/contacts", params={"name": "aaa"}).json()["total"] == 0
    assert client.patch(f"/contacts/{contact_a}", json={"addr": "x"}).status_code == 404
    assert client.delete(f"/contacts/{contact_a}").status_code == 404


def test_tc27_failure_cases_never_return_500(client, make_username):
    username = make_username()
    signup(client, username)
    login(client, username)

    responses = [
        client.post("/auth/signup", json={"username": username, "password": "pass1234", "password_confirm": "pass1234"}),
        client.post("/auth/login", json={"username": username, "password": "wrong"}),
        client.post("/contacts", json={"name": "abc", "phone": "bad", "addr": "", "category_id": 1}),
        client.post("/contacts", json={"name": "abc", "phone": "01000001111", "addr": "", "category_id": 999999}),
        client.patch("/contacts/999999", json={"addr": "x"}),
        client.delete("/contacts/999999"),
        client.patch("/categories/999999", json={"name": "x"}),
        client.delete("/categories/999999"),
    ]

    for res in responses:
        assert res.status_code != 500
        assert res.status_code in (401, 404, 409, 422)


def test_tc28_double_submit_second_request_is_rejected(registered_user):
    client, _ = registered_user
    category_id = client.get("/categories").json()[0]["id"]
    payload = {"name": "abc", "phone": "01043214321", "addr": "", "category_id": category_id}

    first = client.post("/contacts", json=payload)
    second = client.post("/contacts", json=payload)

    assert first.status_code == 201
    assert second.status_code == 409
