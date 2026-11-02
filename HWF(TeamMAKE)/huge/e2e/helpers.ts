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

export type E2eState = { adminEmail: string; adminPassword: string; postingId: string; postingTitle: string };

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
