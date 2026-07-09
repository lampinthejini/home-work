import uuid

import pytest
from fastapi.testclient import TestClient

from contact_app.main import app

DEFAULT_PASSWORD = "pass1234"


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def make_username():
    def _make(prefix="u"):
        return f"{prefix}{uuid.uuid4().hex[:10]}"

    return _make


def signup(client, username, password=DEFAULT_PASSWORD):
    return client.post(
        "/auth/signup",
        json={"username": username, "password": password, "password_confirm": password},
    )


def login(client, username, password=DEFAULT_PASSWORD):
    return client.post("/auth/login", json={"username": username, "password": password})


@pytest.fixture
def registered_user(client, make_username):
    username = make_username()
    signup(client, username)
    login(client, username)
    return client, username
