"""처리되지 않은 서버 오류도 {code, message} 한 모양으로 답한다 (API 명세서 2장·11장, 논의사항 E9)."""

from fastapi.testclient import TestClient

from app.db import getDb
from app.main import app


def brokenDb():
    raise RuntimeError("secret-internal-detail")


def test_unexpectedErrorReturnsCommonShape():
    app.dependency_overrides[getDb] = brokenDb
    try:
        # 수명 주기(DB·저장소 연결)는 필요 없어 with 없이 부른다. 예외를 테스트로 다시 던지지 않게 한다
        client = TestClient(app, raise_server_exceptions=False, base_url="http://127.0.0.1:8000")
        res = client.post("/auth/login", json={"email": "kim@example.com", "password": "x"})
    finally:
        app.dependency_overrides.pop(getDb, None)
    assert res.status_code == 500
    assert res.json() == {"code": "SERVER_ERROR", "message": "잠시 후 다시 시도해 주세요."}
    assert "secret-internal-detail" not in res.text
