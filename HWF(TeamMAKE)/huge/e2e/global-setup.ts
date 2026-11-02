// 테스트 전: 전용 관리자 비밀번호를 새로 정하고, 코딩테스트가 꺼진 E2E 공고를 하나 게시한다.
import { writeFileSync } from "node:fs";

import { request } from "@playwright/test";

import { BASE_URL, E2E_ADMIN_EMAIL, randomPassword, setE2eAdminPassword, STATE_FILE, type E2eState } from "./helpers";

const DEFAULT_WEIGHTS = { expertise: 30, logic: 25, relevance: 20, delivery: 10, culture_fit: 15 };

export default async function globalSetup() {
    const health = await fetch(`${BASE_URL}/api/auth/me`).catch(() => null);
    if (!health) throw new Error(`${BASE_URL} 에 연결하지 못했습니다. 먼저 sh scripts/up.sh 로 띄워 주세요.`);

    const adminPassword = randomPassword();
    setE2eAdminPassword(adminPassword);

    const ctx = await request.newContext({ baseURL: BASE_URL });
    const login = await ctx.post("/api/auth/login", { data: { email: E2E_ADMIN_EMAIL, password: adminPassword } });
    if (login.status() !== 200) throw new Error(`E2E 관리자 로그인 실패: ${login.status()} ${await login.text()}`);

    const postingTitle = `[E2E] AI 면접 확인용 ${new Date().toISOString().slice(0, 16)}`;
    const openAt = new Date(Date.now() - 60 * 60_000);
    const closeAt = new Date(Date.now() + 24 * 60 * 60_000);
    const created = await ctx.post("/api/admin/postings", {
        data: {
            title: postingTitle, job_code: "AI_AX", company_name: "E2E", company_intro: "E2E 자동 테스트용 공고입니다.",
            duties: "LLM 기반 서비스 개발", requirements: "Python 개발 경험", preferred: "", employment_type: "full_time",
            location: "서울", headcount: 1, open_at: openAt.toISOString(), close_at: closeAt.toISOString(), contact_email: E2E_ADMIN_EMAIL,
            criteria: { weights: DEFAULT_WEIGHTS, coding_enabled: false, coding_ratio: 30, pass_score: 70 },
        },
    });
    if (created.status() !== 201) throw new Error(`E2E 공고 만들기 실패: ${created.status()} ${await created.text()}`);
    const postingId = ((await created.json()) as { posting_id: string }).posting_id;
    const published = await ctx.post(`/api/admin/postings/${postingId}/publish`);
    if (published.status() !== 200) throw new Error(`E2E 공고 게시 실패: ${published.status()} ${await published.text()}`);
    await ctx.dispose();

    const state: E2eState = { adminEmail: E2E_ADMIN_EMAIL, adminPassword, postingId, postingTitle };
    writeFileSync(STATE_FILE, JSON.stringify(state), "utf-8");
}
