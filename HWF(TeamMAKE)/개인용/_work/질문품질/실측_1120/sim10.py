"""모의 지원자 10명: 공고 게시 → 가입·지원·동의·이력서·자기소개서 제출 → 서류 평가 → 면접 질문 생성까지 실제 API 로 돌린다.
결과(지원 id 목록)는 sim_state.json 에 남긴다. 관리자는 e2e-admin 계정의 임시 비밀번호로 쓴다(끝나면 바꿔 둔다)."""

import json
import os
import secrets
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone

import httpx

BASE = "http://127.0.0.1:8080/api"
HERE = os.path.dirname(os.path.abspath(__file__))
ADMIN = "e2e-admin@test.local"
ENVX = {**os.environ, "MSYS_NO_PATHCONV": "1"}


def setAdminPassword(pw: str) -> None:
    script = "\n".join([
        "import os", "from app.db import SessionLocal", "from app.models import LoginSession, User",
        "from app.security import hashPassword", "db = SessionLocal()",
        f"u = db.query(User).filter_by(email={ADMIN!r}).first()",
        "if u is None:",
        "    u = User(email=" + repr(ADMIN) + ", name='E2E 관리자', role='admin', password_hash='-', must_change_password=False)",
        "    db.add(u); db.flush()",
        "u.password_hash = hashPassword(os.environ['PW']); u.must_change_password = False; u.failed_logins = 0; u.locked_until = None",
        "db.query(LoginSession).filter(LoginSession.user_id == u.id).delete()", "db.commit()"])
    subprocess.run(["docker", "exec", "-e", f"PW={pw}", "huge-app-api-1", "python", "-c", script], check=True, env=ENVX)


def pw() -> str:
    return f"Sim!{secrets.token_urlsafe(9)}9a"


def check(r: httpx.Response, ok=(200, 201, 204)) -> dict:
    if r.status_code not in ok:
        raise RuntimeError(f"{r.request.method} {r.request.url.path} → {r.status_code} {r.text[:300]}")
    return r.json() if r.content else {}


PERSONAS = json.load(open(os.path.join(HERE, "personas.json"), encoding="utf-8"))


def main() -> None:
    adminPw = pw()
    setAdminPassword(adminPw)
    admin = httpx.Client(base_url=BASE, timeout=60)
    check(admin.post("/auth/login", json={"email": ADMIN, "password": adminPw}))
    now = datetime.now(timezone.utc)
    posting = check(admin.post("/admin/postings", json={
        "title": "[모의] AI/AX 엔지니어 (신입·경력)", "job_code": "AI_AX",
        "company_intro": "생성형 AI 로 기업 업무를 자동화하는 솔루션 회사입니다.",
        "duties": "LLM 기반 서비스 설계·개발\nRAG 파이프라인 구축과 성능 평가\n사내 AI 도입 컨설팅(AX)",
        "requirements": "Python 개발 경험\n머신러닝·딥러닝 기본 지식", "preferred": "LangChain·벡터 DB 사용 경험",
        "employment_type": "full_time", "location": "서울 강남구", "headcount": 2,
        "open_at": (now - timedelta(hours=1)).isoformat(), "close_at": (now + timedelta(days=7)).isoformat(),
        "contact_email": ADMIN,
        "criteria": {"weights": {"expertise": 30, "logic": 25, "relevance": 25, "delivery": 5, "culture_fit": 15}, "coding_enabled": False, "coding_ratio": 30, "pass_score": 70, "screening_required_skills": ["Python"]},
    }))
    postingId = posting["posting_id"]
    check(admin.post(f"/admin/postings/{postingId}/publish"))
    print("공고", postingId, flush=True)

    state = {"posting_id": postingId, "apps": []}
    for i, p in enumerate(PERSONAS, 1):
        c = httpx.Client(base_url=BASE, timeout=60)
        email, password = f"sim-{i:02d}-{secrets.token_hex(2)}@test.local", pw()
        check(c.post("/auth/signup", json={"name": p["resume"]["name"], "email": email, "password": password,
                                           "phone": f"010-5{i:03d}-{1000 + i}",
                                           "agreements": {"age_14_plus": True, "terms": True, "privacy": True}}))
        check(c.post("/auth/login", json={"email": email, "password": password}))
        appId = check(c.post("/applications", json={"posting_id": postingId}))["application_id"]
        version = check(c.get(f"/applications/{appId}"))["consent_version"]
        check(c.post(f"/applications/{appId}/consent", json={"consent_version": version, "items": {
            "data_collection": True, "ai_decision": True, "share_with_admin": True, "retention": True, "exam_rules": True}}))
        check(c.post(f"/applications/{appId}/resume", json={"method": "manual", "resume": p["resume"]}))
        check(c.post(f"/applications/{appId}/submit", json={"cover_text": p["cover"]}))
        state["apps"].append({"no": i, "label": p["label"], "name": p["resume"]["name"], "application_id": appId})
        print(f"{i:02d} 제출 {p['label']} {appId}", flush=True)
        c.close()
    json.dump(state, open(os.path.join(HERE, "sim_state.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    # 서류 평가 → (합격이면) 질문 만들기. 상태는 관리자 API 로 본다
    ids = ",".join(a["application_id"] for a in state["apps"])
    probe = "\n".join([
        "import os", "from app.db import SessionLocal", "from app.models import Application",
        "rows = SessionLocal().query(Application).filter(Application.id.in_(os.environ['IDS'].split(','))).all()",
        "print(' '.join(f'{a.attempt_status}/{a.questions_status}' for a in rows))"])
    started = time.monotonic()
    while time.monotonic() - started < 70 * 60:
        time.sleep(30)
        out = subprocess.run(["docker", "exec", "-e", f"IDS={ids}", "huge-app-api-1", "python", "-c", probe],
                             capture_output=True, text=True, env=ENVX).stdout.strip()
        print(f"{int(time.monotonic() - started)}s {out}", flush=True)
        st = out.split()
        if st and all(s.startswith("screen_rejected") or s.endswith(("/ready", "/failed")) for s in st):
            break
    setAdminPassword(pw())  # 아무도 모르는 값으로
    print("끝", flush=True)


if __name__ == "__main__":
    sys.exit(main())
