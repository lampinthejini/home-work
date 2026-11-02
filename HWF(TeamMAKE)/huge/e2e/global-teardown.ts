// 테스트 뒤: 남은 E2E 지원자를 지우고, E2E 공고를 마감·삭제하고, 전용 관리자 비밀번호를 아무도 모르는 값으로 바꿔 둔다.
// E2E_KEEP=1 이면 지원자·공고를 남겨 둔다 (브라우저에서 실제 관리자 계정으로 녹화·메모를 직접 확인할 때).
import { existsSync, rmSync } from "node:fs";

import { request } from "@playwright/test";

import { BASE_URL, purgeE2eApplicants, randomPassword, readState, setE2eAdminPassword, STATE_FILE } from "./helpers";

export default async function globalTeardown() {
    if (!existsSync(STATE_FILE)) return;
    const state = readState();
    const keep = process.env.E2E_KEEP === "1";
    const ctx = await request.newContext({ baseURL: BASE_URL });
    try {
        if (!keep) {
            const purged = purgeE2eApplicants();
            if (purged) console.log(`남은 E2E 지원자 ${purged}명을 지웠습니다`);
            const login = await ctx.post("/api/auth/login", { data: { email: state.adminEmail, password: state.adminPassword } });
            if (login.status() === 200) {
                await ctx.post(`/api/admin/postings/${state.postingId}/close`);
                await ctx.delete(`/api/admin/postings/${state.postingId}`);
            }
        }
    } finally {
        await ctx.dispose();
        setE2eAdminPassword(randomPassword());
        rmSync(STATE_FILE, { force: true });
    }
}
