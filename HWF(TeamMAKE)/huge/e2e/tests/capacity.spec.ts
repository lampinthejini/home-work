// 동시 면접 상한 (INT-08, TC-057·058): 자리가 없으면 응시 횟수를 쓰지 않고 안내만 하고, 자리가 나면 다시 시도로 들어간다.
import { expect, test, type APIRequestContext } from "@playwright/test";

import { apiAs, randomPassword, readState, signupByApi, uniqueEmail } from "../helpers";
import { applyAndStartInterview } from "./flow";

const LIMIT_URL = "/api/admin/settings/max_concurrent_interviews";
let admin: APIRequestContext;
let originalLimit: number;

test.beforeAll(async () => {
    const state = readState();
    admin = await apiAs(state.adminEmail, state.adminPassword);
    originalLimit = ((await (await admin.get("/api/admin/settings")).json()) as { max_concurrent_interviews: number }).max_concurrent_interviews;
    expect((await admin.put(LIMIT_URL, { data: { value: 1 } })).ok()).toBe(true);
});

test.afterAll(async () => {
    await admin.put(LIMIT_URL, { data: { value: originalLimit } });
    await admin.dispose();
});

test("자리가 없으면 안내 모달만 뜨고, 자리가 나면 다시 시도로 시작한다", async ({ page, browser }) => {
    const password = randomPassword();
    const firstEmail = uniqueEmail("e2e-exam");
    const secondEmail = uniqueEmail("e2e-exam");
    await signupByApi(firstEmail, password);
    await signupByApi(secondEmail, password);

    const secondContext = await browser.newContext({
        baseURL: test.info().project.use.baseURL, permissions: ["camera", "microphone"],
        viewport: { width: 1440, height: 900 }, locale: "ko-KR", timezoneId: "Asia/Seoul",
    });
    const second = await secondContext.newPage();
    const status = async (id: string) =>
        ((await (await admin.get(`/api/admin/applicants/${id}`)).json()) as { attempt_status: string }).attempt_status;

    const secondId = await applyAndStartInterview(second, secondEmail, password, { stopAtRules: true });
    const firstId = await applyAndStartInterview(page, firstEmail, password, { waitFirstQuestion: false });
    await expect.poll(() => status(firstId)).toBe("interviewing");

    const modal = second.getByRole("dialog", { name: "지금은 면접을 시작할 수 없습니다" });

    await test.step("두 번째 지원자는 429 와 안내 모달을 받고 상태가 그대로다", async () => {
        await second.getByLabel("위 응시 규칙을 모두 확인했습니다.").check();
        const refused = second.waitForResponse((r) => r.url().endsWith("/interview/start"));
        await second.getByRole("button", { name: /면접 시작/ }).click();
        expect((await refused).status()).toBe(429);
        await expect(modal).toBeVisible();
        await expect(modal).not.toContainText("찼");
        expect(await status(secondId)).toBe("ready");
    });

    await test.step("다시 시도는 10초 동안 꺼져 있고 남은 초를 보여 준다", async () => {
        await expect(modal.getByRole("button", { name: /다시 시도 \(\d+\)/ })).toBeDisabled();
        await expect(modal.getByRole("button", { name: "다시 시도", exact: true })).toBeEnabled({ timeout: 15_000 });
        await expect(second).toHaveURL(/\/rules/); // 저절로 들어가지 않는다
    });

    await test.step("자리가 나면 다시 시도로 면접이 시작된다", async () => {
        expect((await page.request.post(`/api/applications/${firstId}/consent/withdraw`)).ok()).toBe(true);
        await modal.getByRole("button", { name: "다시 시도", exact: true }).click();
        await expect(second).toHaveURL(new RegExp(`/exam/${secondId}$`));
        await expect.poll(() => status(secondId)).toBe("interviewing");
    });

    expect((await second.request.post(`/api/applications/${secondId}/consent/withdraw`)).ok()).toBe(true);
    await secondContext.close();
});
