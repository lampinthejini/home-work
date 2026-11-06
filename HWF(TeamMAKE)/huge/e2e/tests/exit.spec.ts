// 지원자가 스스로 떠날 때 (TC-064·065): 뒤로가기는 막기만 하고, 새로고침·창 닫기는 이어가기 없이 응시 종료다.
import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

import { apiAs, loginByUi, randomPassword, readState, signupByApi, uniqueEmail } from "../helpers";
import { applyAndStartInterview } from "./flow";

let admin: APIRequestContext;

test.beforeAll(async () => {
    const state = readState();
    admin = await apiAs(state.adminEmail, state.adminPassword);
});

test.afterAll(async () => {
    await admin?.dispose();
});

type Detail = { attempt_status: string };

/** 끝난 이유는 지원자용 상태 API 가 알려 준다. 끊긴 지 15초 뒤 판정한다 */
async function expectEndedByUnload(applicationId: string, email: string, password: string) {
    const applicant = await apiAs(email, password);
    await expect.poll(async () => {
        const s = await (await applicant.get(`/api/applications/${applicationId}/interview/state`)).json() as { attempt_status: string; end_detail: string | null };
        return `${s.attempt_status}/${s.end_detail}`;
    }, { timeout: 60_000, intervals: [2000] }).toBe("ended/unload");
    await applicant.dispose();
}

async function expectNoResume(page: Page) {
    await page.goto("/mypage");
    await expect(page.getByText("응시 종료").first()).toBeVisible();
    await expect(page.getByRole("link", { name: "면접 이어가기" })).toHaveCount(0);
}

test("뒤로가기는 화면을 그대로 두고, 새로고침하면 이어가기 없이 응시 종료다", async ({ page }) => {
    const email = uniqueEmail("e2e-exam");
    const password = randomPassword();
    await signupByApi(email, password);
    page.on("dialog", (dialog) => void dialog.accept()); // 새로고침 확인 창
    const applicationId = await applyAndStartInterview(page, email, password);

    await test.step("뒤로가기: 화면 그대로, 안내만, 이탈 아님", async () => {
        await page.evaluate(() => history.back());
        await expect(page.locator("span").filter({ hasText: "응시 중에는 이전 화면으로 갈 수 없습니다" })).toBeVisible(); // 토스트 (화면 낭독용 사본과 구분)
        await expect(page).toHaveURL(new RegExp(`/exam/${applicationId}$`));
        await expect(page.getByRole("alertdialog", { name: /화면 이탈이 감지되었습니다/ })).toHaveCount(0);
        const d = await (await admin.get(`/api/admin/applicants/${applicationId}`)).json() as Detail;
        expect(d.attempt_status).toBe("interviewing");
    });

    await test.step("새로고침: 응시 종료", async () => {
        await page.reload();
        await expectEndedByUnload(applicationId, email, password);
        await expectNoResume(page);
    });
});

test("창을 닫으면 이어가기 없이 응시 종료다", async ({ page, browser }) => {
    const email = uniqueEmail("e2e-exam");
    const password = randomPassword();
    await signupByApi(email, password);
    page.on("dialog", (dialog) => void dialog.accept()); // 나가기 확인 창
    const applicationId = await applyAndStartInterview(page, email, password);

    await page.close({ runBeforeUnload: true });
    await expectEndedByUnload(applicationId, email, password);

    const context = await browser.newContext({ baseURL: test.info().project.use.baseURL });
    const again = await context.newPage();
    await loginByUi(again, email, password);
    await expect(again).toHaveURL(/\/jobs/);
    await expectNoResume(again);
    await context.close();
});
