// E2E 공용 도우미: 실행 중인 Docker 스택(sh scripts/up.sh)에 붙는다. 앱 코드는 바꾸지 않는다.
import { execFileSync } from "node:child_process";
import { randomBytes } from "node:crypto";
import { readFileSync } from "node:fs";
import path from "node:path";

import { expect, request, type APIRequestContext, type Page } from "@playwright/test";

export const BASE_URL = process.env.E2E_BASE_URL ?? "http://127.0.0.1:8080";
export const MAILPIT_URL = process.env.E2E_MAILPIT_URL ?? "http://127.0.0.1:8025";
export const API_CONTAINER = process.env.E2E_API_CONTAINER ?? "huge-app-api-1";
export const E2E_ADMIN_EMAIL = "e2e-admin@test.local";
export const STATE_FILE = path.join(__dirname, ".state.json");
const DEFAULT_WEIGHTS = { expertise: 30, logic: 25, relevance: 20, delivery: 10, culture_fit: 15 };

export type E2eState = {
    adminEmail: string; adminPassword: string;
    postingId: string; postingTitle: string; // 코딩테스트 끔
    codingPostingId: string; codingPostingTitle: string; // 코딩테스트 켬
    questionWatermark: number; // 시작할 때 가장 큰 질문 번호 (이보다 뒤에 생긴 AI 질문 후보는 테스트가 만든 것)
};

export function readState(): E2eState {
    return JSON.parse(readFileSync(STATE_FILE, "utf-8")) as E2eState;
}

/** 비밀번호 규칙(대·소문자·숫자·특수문자, 이메일 아이디 미포함)을 만족하는 무작위 비밀번호 */
export function randomPassword(): string {
    return `E2e!${randomBytes(9).toString("base64url")}9a`;
}

export function uniqueEmail(prefix: string): string {
    return `${prefix}-${Date.now().toString(36)}${randomBytes(2).toString("hex")}@test.local`;
}

/**
 * 테스트 전용 관리자 계정의 비밀번호를 정한다(없으면 만든다).
 * 실제 관리자 비밀번호를 몰라도 되도록 api 컨테이너 안에서 앱의 해시 함수로 직접 저장한다.
 * 비밀번호는 명령줄이 아니라 환경변수로 넘겨 프로세스 목록에 남지 않게 한다.
 */
export function setE2eAdminPassword(password: string): void {
    const script = [
        "import os",
        "from app.db import SessionLocal",
        "from app.models import LoginSession, User",
        "from app.security import hashPassword",
        "db = SessionLocal()",
        `email = ${JSON.stringify(E2E_ADMIN_EMAIL)}`,
        "u = db.query(User).filter_by(email=email).first()",
        "if u is None:",
        "    u = User(email=email, name='E2E 관리자', role='admin', password_hash='-', must_change_password=False)",
        "    db.add(u)",
        "    db.flush()",
        "u.password_hash = hashPassword(os.environ['E2E_PW'])",
        "u.must_change_password = False",
        "u.failed_logins = 0",
        "u.locked_until = None",
        "db.query(LoginSession).filter(LoginSession.user_id == u.id).delete()",
        "db.commit()",
    ].join("\n");
    execFileSync("docker", ["exec", "-e", `E2E_PW=${password}`, API_CONTAINER, "python", "-c", script], {
        env: { ...process.env, MSYS_NO_PATHCONV: "1" },
        stdio: ["ignore", "ignore", "pipe"],
    });
}

/**
 * 테스트가 중간에 실패해 남은 E2E 지원자(e2e-auth-*, e2e-exam-* @test.local)를 앱의 탈퇴 처리로 지운다.
 * 같은 삭제 경로(파일·Redis·DB, deletion_logs)를 타므로 E2E 공고도 지울 수 있게 된다.
 */
export function purgeE2eApplicants(): number {
    const script = [
        "import asyncio",
        "from app.db import SessionLocal",
        "from app.models import User",
        "from app.services import withdrawal",
        "db = SessionLocal()",
        "users = [u for u in db.query(User).filter(User.role == 'applicant', User.email.like('%@test.local')).all()",
        "         if u.email.startswith(('e2e-auth-', 'e2e-exam-'))]",
        "for u in users:",
        "    asyncio.run(withdrawal.withdrawAccount(db, u))",
        "print(len(users))",
    ].join("\n");
    const out = execFileSync("docker", ["exec", API_CONTAINER, "python", "-c", script], {
        env: { ...process.env, MSYS_NO_PATHCONV: "1" },
        stdio: ["ignore", "pipe", "pipe"],
    });
    return Number(out.toString().trim().split("\n").pop());
}

/** 지금 가장 큰 질문 번호. 테스트 뒤 이보다 큰 AI 질문 후보만 지운다 */
export function questionWatermark(): number {
    const script = [
        "from sqlalchemy import func",
        "from app.db import SessionLocal",
        "from app.models import Question",
        "print(SessionLocal().query(func.max(Question.id)).scalar() or 0)",
    ].join("\n");
    const out = execFileSync("docker", ["exec", API_CONTAINER, "python", "-c", script], {
        env: { ...process.env, MSYS_NO_PATHCONV: "1" },
        stdio: ["ignore", "pipe", "pipe"],
    });
    return Number(out.toString().trim().split("\n").pop());
}

/**
 * 테스트 중에 생긴 AI 질문 후보(검토 대기)를 지운다. 공고 게시 때 만든 '공고 기반' 후보와 면접 때 만든 'AI 생성' 후보가
 * E2E 공고로 만들어져 질문 관리에 쌓이지 않게 한다 (회사 질문은 공고를 지우면 함께 지워지지만 직무·인성 질문은 남는다).
 * 관리자가 이미 [추가]·[제외]한 질문이나 엑셀·예비 질문은 건드리지 않는다.
 */
export function purgeE2eQuestions(after: number): number {
    const script = [
        "import os",
        "from app.db import SessionLocal",
        "from app.models import AuditLog, InterviewQuestion, Question",
        "db = SessionLocal()",
        "used = db.query(InterviewQuestion.source_question_id).filter(InterviewQuestion.source_question_id.isnot(None))",
        "rows = db.query(Question).filter(Question.id > int(os.environ['E2E_AFTER']), Question.source == 'generated',",
        "                                 Question.status == 'pending', Question.id.notin_(used)).all()",
        "for q in rows:",
        "    db.delete(q)",
        "if rows:",
        "    db.add(AuditLog(action='question.e2e_cleanup', target='questions', detail={'deleted': [q.id for q in rows]}))",
        "db.commit()",
        "print(len(rows))",
    ].join("\n");
    const out = execFileSync("docker", ["exec", "-e", `E2E_AFTER=${after}`, API_CONTAINER, "python", "-c", script], {
        env: { ...process.env, MSYS_NO_PATHCONV: "1" },
        stdio: ["ignore", "pipe", "pipe"],
    });
    return Number(out.toString().trim().split("\n").pop());
}

/**
 * 결과 공개 시각을 '지금'으로 앞당기고 5분 점검(huge.sweep)을 바로 한 번 돌린다.
 * 공개 시각은 마감 다음 날 10:00 이라 기다릴 수 없어서, 이 지원 건의 시각만 바꾼다 (freezegun 과 같은 목적).
 * 공개·알림·메일은 앱의 실제 점검 코드가 한다.
 */
export function releaseResultNow(applicationId: string): void {
    const script = [
        "import os",
        "from datetime import timedelta",
        "from app.db import SessionLocal",
        "from app.models import Application",
        "from app.timeutil import now",
        "from app.worker import sweepTask",
        "db = SessionLocal()",
        "app = db.get(Application, os.environ['E2E_APP'])",
        "assert app.analysis_status == 'decided', app.analysis_status",
        "app.release_at = now() - timedelta(minutes=1)",
        "db.commit()",
        "db.close()",
        "print(sweepTask())",
    ].join("\n");
    execFileSync("docker", ["exec", "-e", `E2E_APP=${applicationId}`, API_CONTAINER, "python", "-c", script], {
        env: { ...process.env, MSYS_NO_PATHCONV: "1" },
        stdio: ["ignore", "ignore", "pipe"],
    });
}

/** 쿠키를 들고 다니는 API 클라이언트 (화면과 같은 출처 /api) */
export async function apiAs(email: string, password: string): Promise<APIRequestContext> {
    const ctx = await request.newContext({ baseURL: BASE_URL });
    const res = await ctx.post("/api/auth/login", { data: { email, password } });
    expect(res.status(), `login ${email}`).toBe(200);
    return ctx;
}

export async function signupByApi(email: string, password: string, name = "이투이"): Promise<void> {
    const ctx = await request.newContext({ baseURL: BASE_URL });
    const res = await ctx.post("/api/auth/signup", {
        data: { name, email, password, phone: "010-1234-5678", agreements: { age_14_plus: true, terms: true, privacy: true } },
    });
    expect(res.status(), await res.text()).toBe(201);
    await ctx.dispose();
}

export async function loginByUi(page: Page, email: string, password: string): Promise<void> {
    await page.goto("/login");
    await page.getByLabel("이메일").fill(email);
    await page.locator("input[autocomplete='current-password']").fill(password);
    await page.getByRole("button", { name: "로그인" }).click();
}

type MailSummary = { ID: string; Subject: string };

/** Mailpit 에서 받는 사람 기준 메일을 기다린다 */
export async function waitForMail(to: string, timeoutMs = 30_000): Promise<{ subject: string; text: string; count: number }> {
    const ctx = await request.newContext({ baseURL: MAILPIT_URL });
    try {
        let found: MailSummary[] = [];
        await expect.poll(async () => {
            const res = await ctx.get("/api/v1/search", { params: { query: `to:${to}` } });
            found = ((await res.json()) as { messages: MailSummary[] }).messages;
            return found.length;
        }, { timeout: timeoutMs, message: `mail to ${to}` }).toBeGreaterThan(0);
        const msg = await (await ctx.get(`/api/v1/message/${found[0].ID}`)).json() as { Subject: string; Text: string };
        return { subject: msg.Subject, text: msg.Text, count: found.length };
    } finally {
        await ctx.dispose();
    }
}

/**
 * 채점을 끝내지 못한 '확인 필요' 지원 건을 바로 만든다. 실제로 만들려면 AI 를 멈추고 30분을 기다려야 해서 상태만 넣는다.
 * 돌려주는 값은 지원 번호.
 */
export function seedNeedsReview(email: string, postingId: string): string {
    const script = [
        "import os",
        "from app.db import SessionLocal",
        "from app.models import Application, EvaluationCriteria, User",
        "from app.timeutil import now",
        "db = SessionLocal()",
        "user = db.query(User).filter_by(email=os.environ['E2E_EMAIL']).one()",
        "criteria = db.query(EvaluationCriteria).filter_by(posting_id=os.environ['E2E_POSTING']).order_by(EvaluationCriteria.version.desc()).first()",
        "app = Application(user_id=user.id, posting_id=os.environ['E2E_POSTING'], attempt_status='completed', submitted_at=now(), completed_at=now(),",
        "                  criteria_version=criteria.version, analysis_status='needs_review', review_reason='analysis_timeout')",
        "db.add(app)",
        "db.commit()",
        "print(app.id)",
        "db.close()",
    ].join("\n");
    return execFileSync("docker", ["exec", "-e", `E2E_EMAIL=${email}`, "-e", `E2E_POSTING=${postingId}`, API_CONTAINER, "python", "-c", script], {
        env: { ...process.env, MSYS_NO_PATHCONV: "1" },
        stdio: ["ignore", "pipe", "pipe"],
    }).toString().trim();
}

/** 평가 항목 기본 비율로 공고를 만들어 게시한다. 공고 번호를 돌려준다 */
export async function publishPosting(ctx: APIRequestContext, title: string, codingEnabled: boolean): Promise<string> {
    const openAt = new Date(Date.now() - 60 * 60_000);
    const closeAt = new Date(Date.now() + 24 * 60 * 60_000);
    const created = await ctx.post("/api/admin/postings", {
        data: {
            title, job_code: "AI_AX", company_name: "E2E", company_intro: "E2E 자동 테스트용 공고입니다.",
            duties: "LLM 기반 서비스 개발", requirements: "Python 개발 경험", preferred: "", employment_type: "full_time",
            location: "서울", headcount: 1, open_at: openAt.toISOString(), close_at: closeAt.toISOString(), contact_email: E2E_ADMIN_EMAIL,
            criteria: { weights: DEFAULT_WEIGHTS, coding_enabled: codingEnabled, coding_ratio: 30, pass_score: 70 },
        },
    });
    if (created.status() !== 201) throw new Error(`E2E 공고 만들기 실패: ${created.status()} ${await created.text()}`);
    const postingId = ((await created.json()) as { posting_id: string }).posting_id;
    const published = await ctx.post(`/api/admin/postings/${postingId}/publish`);
    if (published.status() !== 200) throw new Error(`E2E 공고 게시 실패: ${published.status()} ${await published.text()}`);
    return postingId;
}

/**
 * 장애 중단 상태인 지원 건을 '코딩테스트 중 끊긴 건, 남은 시간 N초'로 바꾼다.
 * 60분을 기다리거나 면접 10문항을 끝까지 답하지 않고 자동 제출을 확인하기 위해서다. 이어가기·자동 제출은 앱 코드가 한다.
 */
export function seedInterruptedCoding(applicationId: string, remainingSec: number, savedCode: string): void {
    const script = [
        "import os",
        "from app.db import SessionLocal",
        "from app.models import Application, CodingSubmission",
        "from app.services import admission, coding_bank",
        "db = SessionLocal()",
        "app = db.get(Application, os.environ['E2E_APP'])",
        "assert app.attempt_status == 'interrupted', app.attempt_status",
        "app.phase = 'coding'",
        "app.coding_remaining_sec = int(os.environ['E2E_SEC'])",
        "app.coding_started_at = None",
        "for no, key in enumerate(coding_bank.pickProblems(app.id), start=1):",
        "    db.add(CodingSubmission(application_id=app.id, problem_no=no, problem_key=key, code=os.environ['E2E_CODE'] if no == 1 else coding_bank.PROBLEMS[key]['starter']))",
        "db.commit()",
        "admission.release(db, app)",
        "db.close()",
    ].join("\n");
    execFileSync("docker", ["exec", "-e", `E2E_APP=${applicationId}`, "-e", `E2E_SEC=${remainingSec}`, "-e", `E2E_CODE=${savedCode}`, API_CONTAINER, "python", "-c", script], {
        env: { ...process.env, MSYS_NO_PATHCONV: "1" },
        stdio: ["ignore", "ignore", "pipe"],
    });
}

/** 이 지원 건에 배정된 문제 키 (문제 번호 순) */
export function readProblemKeys(applicationId: string): string[] {
    const script = [
        "import json, os",
        "from app.db import SessionLocal",
        "from app.models import CodingSubmission",
        "db = SessionLocal()",
        "rows = db.query(CodingSubmission).filter_by(application_id=os.environ['E2E_APP']).order_by(CodingSubmission.problem_no).all()",
        "print(json.dumps([r.problem_key for r in rows]))",
    ].join("\n");
    return JSON.parse(execFileSync("docker", ["exec", "-e", `E2E_APP=${applicationId}`, API_CONTAINER, "python", "-c", script], {
        env: { ...process.env, MSYS_NO_PATHCONV: "1" },
        stdio: ["ignore", "pipe", "pipe"],
    }).toString()) as string[];
}

/** 서버에 저장된 코드를 읽는다 */
export function readSavedCode(applicationId: string, problemNo: number): string {
    const script = [
        "import os, sys",
        "from app.db import SessionLocal",
        "from app.models import CodingSubmission",
        "db = SessionLocal()",
        "row = db.query(CodingSubmission).filter_by(application_id=os.environ['E2E_APP'], problem_no=int(os.environ['E2E_NO'])).one()",
        "sys.stdout.buffer.write(row.code.encode('utf-8'))",
    ].join("\n");
    return execFileSync("docker", ["exec", "-e", `E2E_APP=${applicationId}`, "-e", `E2E_NO=${problemNo}`, API_CONTAINER, "python", "-c", script], {
        env: { ...process.env, MSYS_NO_PATHCONV: "1" },
        stdio: ["ignore", "pipe", "pipe"],
    }).toString("utf-8");
}
