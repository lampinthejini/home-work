// 테스트 뒤: 남은 E2E 지원자를 지우고, E2E 공고를 마감·삭제하고, 테스트 중에 생긴 AI 질문 후보를 지우고, 전용 관리자 비밀번호를 아무도 모르는 값으로 바꿔 둔다.
// E2E_KEEP=1 이면 지원자·공고를 남겨 둔다 (브라우저에서 실제 관리자 계정으로 녹화·메모를 직접 확인할 때).
import { existsSync, rmSync } from "node:fs";

import { request } from "@playwright/test";

import { BASE_URL, purgeE2eApplicants, purgeE2eQuestions, randomPassword, readState, setE2eAdminPassword, STATE_FILE } from "./helpers";

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
                // 공고 두 개와 테스트가 따로 만든 공고(제목이 [E2E] 로 시작)를 모두 지운다
                const list = await (await ctx.get("/api/admin/postings")).json() as { items: { posting_id: string; title: string }[] };
                for (const posting of list.items.filter((p) => p.title.startsWith("[E2E]"))) {
                    await ctx.post(`/api/admin/postings/${posting.posting_id}/close`);
                    await ctx.delete(`/api/admin/postings/${posting.posting_id}`);
                }
            }
            // 게시·면접 때 생긴 AI 질문 후보(검토 대기)를 지운다. 게시 뒤 후보 만들기는 뒤에서 돌아 늦게 끝날 수 있다
            if (typeof state.questionWatermark === "number") {
                await new Promise((resolve) => setTimeout(resolve, 5_000));
                const removed = purgeE2eQuestions(state.questionWatermark);
                if (removed) console.log(`E2E 가 만든 질문 후보 ${removed}개를 지웠습니다`);
            }
        }
    } finally {
        await ctx.dispose();
        setE2eAdminPassword(randomPassword());
        rmSync(STATE_FILE, { force: true });
    }
}
