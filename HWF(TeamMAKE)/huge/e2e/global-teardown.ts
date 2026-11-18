// 테스트 뒤: 남은 E2E 지원자를 지우고, E2E 공고를 마감·삭제하고, 테스트 중에 생긴 AI 질문 후보를 지우고, 전용 관리자 비밀번호를 아무도 모르는 값으로 바꿔 둔다.
// E2E_KEEP=1 이면 지원자·공고를 남겨 둔다 (브라우저에서 실제 관리자 계정으로 녹화·메모를 직접 확인할 때).
import { existsSync, rmSync } from "node:fs";

import { request } from "@playwright/test";

import { BASE_URL, finishedCandidatePostings, purgeE2eApplicants, purgeE2eQuestions, questionCount, randomPassword, readState, setE2eAdminPassword, STATE_FILE } from "./helpers";

export default async function globalTeardown() {
    if (!existsSync(STATE_FILE)) return;
    const state = readState();
    const keep = process.env.E2E_KEEP === "1";
    const ctx = await request.newContext({ baseURL: BASE_URL });
    let leftover: string | null = null;
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
            // 게시·면접 때 생긴 질문(예비 질문으로 바로 들어감, C-20)을 지운다. 게시 뒤 후보 만들기는 뒤에서 돌아 늦게 끝날 수 있다
            if (typeof state.questionWatermark === "number") {
                // 짧게 돌리면 게시 뒤 후보 만들기(공고마다 약 1~2분)가 아직 돌고 있어, 지운 뒤에 질문이 다시 생긴다. 끝날 때까지(최대 3분) 기다린다
                const setupPostings = [state.postingId, state.codingPostingId];
                for (let waited = 0; waited < 180_000 && finishedCandidatePostings(setupPostings) < setupPostings.length; waited += 5_000) {
                    await new Promise((resolve) => setTimeout(resolve, 5_000));
                }
                await new Promise((resolve) => setTimeout(resolve, 5_000));
                const removed = purgeE2eQuestions(state.questionWatermark);
                if (removed) console.log(`E2E 가 만든 질문 후보 ${removed}개를 지웠습니다`);
            }
            // 뒷정리가 제대로 됐는지: 질문 DB 개수가 시작할 때와 같아야 한다 (2026-11-18 추가)
            if (typeof state.questionCount === "number") {
                const after = questionCount();
                if (after !== state.questionCount) leftover = `질문 DB 가 시작 때 ${state.questionCount}개에서 ${after}개로 바뀌었습니다 — 뒷정리를 확인하세요`;
                else console.log(`뒷정리 확인: 질문 DB ${after}개 (시작 때와 같음)`);
            }
        }
    } finally {
        await ctx.dispose();
        setE2eAdminPassword(randomPassword());
        rmSync(STATE_FILE, { force: true });
    }
    if (leftover) throw new Error(leftover);
}
