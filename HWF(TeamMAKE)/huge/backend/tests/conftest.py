"""API 테스트: SQLite 메모리 DB + fakeredis. 외부 AI·저장소는 부르지 않는다."""

import base64
import os

os.environ["DATABASE_URL"] = "sqlite://"
os.environ["APP_PROFILE"] = "dev"
os.environ["TRUSTED_PROXY_HOST"] = ""  # 시험에는 frontend 가 없다. 이름 찾기로 로그인마다 몇 초씩 기다리지 않게 한다
os.environ["APP_ENCRYPTION_KEY"] = base64.b64encode(b"t" * 32).decode()  # 시험 전용 키

from datetime import timedelta  # noqa: E402

import fakeredis  # noqa: E402
import pytest  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from fastapi.exceptions import RequestValidationError  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine, event  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from app import db as dbModule  # noqa: E402
from app import worker  # noqa: E402
from app.db import Base, getDb  # noqa: E402
from app.errors import ApiError, apiErrorHandler, validationErrorHandler  # noqa: E402
from app.models import User  # noqa: E402
from app.routers import admin, admin_ops, admin_questions, applications, auth, interview, me, postings  # noqa: E402
from app.security import hashPassword  # noqa: E402
from app.services import admission, question_compose  # noqa: E402
from app.services.postings import seedJobCodes  # noqa: E402
from app.timeutil import now  # noqa: E402

ADMIN_PASSWORD = "Admin#Pass2026"
APPLICANT_PASSWORD = "Apply#Pass2026"


@pytest.fixture()
def sessionFactory(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    # PostgreSQL 처럼 외래 키를 검사한다 (삭제·연결 오류를 테스트에서 잡기 위해)
    event.listen(engine, "connect", lambda conn, _record: conn.execute("PRAGMA foreign_keys=ON"))
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setattr(dbModule, "SessionLocal", factory)
    monkeypatch.setattr(admission, "_redis", fakeredis.FakeRedis())
    monkeypatch.setattr(question_compose, "scheduleCompose", lambda applicationId: None)
    monkeypatch.setattr(worker, "enqueueEvaluation", lambda applicationId, attempt=1, countdown=0: None)
    monkeypatch.setattr(worker, "queueMail", lambda notificationId, countdown=0: None)
    with factory() as db:
        seedJobCodes(db)
        db.add(User(email="admin@huge.local", password_hash=hashPassword(ADMIN_PASSWORD), name="관리자", role="admin"))
        db.commit()
    return factory


@pytest.fixture()
def client(sessionFactory):
    app = FastAPI()
    app.add_exception_handler(ApiError, apiErrorHandler)
    app.add_exception_handler(RequestValidationError, validationErrorHandler)
    for module in (auth, postings, applications, interview, me, admin_ops, admin_questions, admin):
        app.include_router(module.router)

    def overrideDb():
        db = sessionFactory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[getDb] = overrideDb
    return TestClient(app, base_url="http://127.0.0.1:8000")


def login(client, email, password):
    res = client.post("/auth/login", json={"email": email, "password": password})
    assert res.status_code == 200, res.text
    return res.json()


@pytest.fixture()
def adminClient(client):
    login(client, "admin@huge.local", ADMIN_PASSWORD)
    return client


def signup(client, email="kim@example.com"):
    res = client.post("/auth/signup", json={
        "name": "김지원", "email": email, "password": APPLICANT_PASSWORD, "phone": "010-1234-5678",
        "agreements": {"age_14_plus": True, "terms": True, "privacy": True}})
    assert res.status_code == 201, res.text


def postingBody(**overrides):
    body = {
        "title": "AI/AX 엔지니어", "job_code": "AI_AX", "company_name": "(주)휴지테크", "company_intro": "소개",
        "duties": "업무", "requirements": "요건", "preferred": "", "employment_type": "full_time", "location": "서울",
        "headcount": 2, "open_at": (now() - timedelta(days=1)).isoformat(), "close_at": (now() + timedelta(days=7)).isoformat(),
        "contact_email": "recruit@example.com",
        "criteria": {"weights": {"expertise": 30, "logic": 25, "relevance": 20, "delivery": 10, "culture_fit": 15},
                     "coding_enabled": True, "coding_ratio": 30, "pass_score": 70},
    }
    body.update(overrides)
    return body


def publishedPosting(adminClient, **overrides) -> str:
    res = adminClient.post("/admin/postings", json=postingBody(**overrides))
    assert res.status_code == 201, res.text
    postingId = res.json()["posting_id"]
    res = adminClient.post(f"/admin/postings/{postingId}/publish")
    assert res.status_code == 200, res.text
    return postingId
