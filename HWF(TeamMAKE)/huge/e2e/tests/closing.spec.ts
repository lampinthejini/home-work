// 공고 마감 (INT-10, TC-073~075): 진행 중 면접은 바로 끝나고, 시작 전·장애 중단 지원자는 더 진행할 수 없다.
// 다른 테스트에 영향이 없도록 공고를 따로 만들어 마감한다. 공고는 global-teardown 이 지운다.
import { expect, test, type APIRequestContext, type WebSocketRoute } from "@playwright/test";

import { apiAs, publishPosting, randomPassword, readState, signupByApi, uniqueEmail } from "../helpers";
import { applyAndStartInterview, passPrecheck } from "./flow";

let admin: APIRequestContext;

test.beforeAll(async () => {
    const state = readState();
    admin = await apiAs(state.adminEmail, state.adminPassword);
});

test.afterAll(async () => {
    await admin?.dispose();
});

async function ownPosting(title: string) {
    const fullTitle = `[E2E] ${title} ${Date.now()}`;
    return { id: await publishPosting(admin, fullTitle, false), title: fullTitle };
}

const status = async (id: string) =>
    ((await (await admin.get(`/api/admin/applicants/${id}`)).json()) as { attempt_status: string }).attempt_status;

test("마감하면 진행 중 면접은 바로 끝나고, 시작 전 지원자는 시작할 수 없다", async ({ page, browser }) => {
    const posting = await ownPosting("마감 확인");
    const password = randomPassword();
    const liveEmail = uniqueEmail("e2e-exam");
    const waitingEmail = uniqueEmail("e2e-exam");
    await signupByApi(liveEmail, password);
    await signupByApi(waitingEmail, password);

    const waitingContext = await browser.newContext({
        baseURL: test.info().project.use.baseURL, permissions: ["camera", "microphone"],
        viewport: { width: 1440, height: 900 }, locale: "ko-KR", timezoneId: "Asia/Seoul",
    });
    const waiting = await waitingContext.newPage();
    const waitingId = await applyAndStartInterview(waiting, waitingEmail, password, { posting, stopAtRules: true });
    const liveId = await applyAndStartInterview(page, liveEmail, password, { posting });

    expect((await admin.post(`/api/admin/postings/${posting.id}/close`)).ok()).toBe(true);

    await test.step("진행 중 면접: 마감 안내, 이탈 경고 없음, 응시 종료(마감)", async () => {
        await expect(page.getByRole("alertdialog", { name: "마감이 되어 면접을 진행할 수 없습니다." })).toBeVisible();
        await expect(page.getByRole("alertdialog", { name: /화면 이탈이 감지되었습니다/ })).toHaveCount(0);
        await expect.poll(() => status(liveId)).toBe("ended_closed");
    });

    await test.step("시작 전 지원자: 시작하면 409 와 마감 문구, 미응시(마감)", async () => {
        await waiting.getByLabel("위 응시 규칙을 모두 확인했습니다.").check();
        const refused = waiting.waitForResponse((r) => r.url().endsWith("/interview/start"));
        await waiting.getByRole("button", { name: /면접 시작/ }).click();
        const response = await refused;
        expect(response.status()).toBe(409);
        expect(((await response.json()) as { code: string }).code).toBe("POSTING_CLOSED");
        await expect(waiting.locator("span").filter({ hasText: "마감 시각이 지났습니다." })).toBeVisible(); // 토스트 (화면 낭독용 사본과 구분)
        expect(await status(waitingId)).toBe("not_taken_closed");
    });

    await waitingContext.close();
});

test("장애 중단 상태에서 마감되면 이어가기가 마감 안내로 바뀐다", async ({ page }) => {
    const posting = await ownPosting("마감 이어가기");
    const email = uniqueEmail("e2e-exam");
    const password = randomPassword();
    await signupByApi(email, password);

    const sockets: { page: WebSocketRoute; server: WebSocketRoute }[] = [];
    await page.routeWebSocket(/\/ws\/interview\//, (ws) => {
        sockets.push({ page: ws, server: ws.connectToServer() });
    });
    const applicationId = await applyAndStartInterview(page, email, password, { posting });

    const live = sockets.at(-1)!;
    await live.server.close();
    await live.page.close({ code: 4000, reason: "e2e network cut" });
    await expect.poll(() => status(applicationId), { timeout: 90_000, intervals: [3000] }).toBe("interrupted");

    await page.goto(`/exam/${applicationId}/resume`);
    await passPrecheck(page);
    expect((await admin.post(`/api/admin/postings/${posting.id}/close`)).ok()).toBe(true);
    await page.getByRole("button", { name: "이어서 시작 (전체 화면)" }).click();

    await expect(page.getByRole("heading", { name: "마감이 되어 면접을 진행할 수 없습니다." })).toBeVisible();
    expect(await status(applicationId)).toBe("ended_closed");
});
