// 코딩테스트 이어가기·시간 초과 (COD-04, TC-081·085): 저장된 코드와 남은 시간부터 이어 가고, 시간이 끝나면 서버가 마지막 저장 코드로 자동 제출한다.
// 면접 10문항과 60분을 기다리지 않도록, 장애 중단된 지원 건을 '코딩 중 끊긴 건, 남은 45초'로 바꿔 이어간다.
import { expect, test, type APIRequestContext, type WebSocketRoute } from "@playwright/test";

import { apiAs, randomPassword, readSavedCode, readState, seedInterruptedCoding, signupByApi, uniqueEmail } from "../helpers";
import { applyAndStartInterview, getEditorCode, passPrecheck, setEditorCode } from "./flow";

let admin: APIRequestContext;

test.beforeAll(async () => {
    const state = readState();
    admin = await apiAs(state.adminEmail, state.adminPassword);
});

test.afterAll(async () => {
    await admin?.dispose();
});

test("끊긴 코딩테스트는 저장된 코드부터 이어 가고, 시간이 끝나면 자동 제출된다", async ({ page }) => {
    const email = uniqueEmail("e2e-exam");
    const password = randomPassword();
    await signupByApi(email, password);
    const sockets: { page: WebSocketRoute; server: WebSocketRoute }[] = [];
    await page.routeWebSocket(/\/ws\/interview\//, (ws) => {
        sockets.push({ page: ws, server: ws.connectToServer() });
    });
    const applicationId = await applyAndStartInterview(page, email, password, { coding: true });
    const detail = async () =>
        (await (await admin.get(`/api/admin/applicants/${applicationId}`)).json()) as { attempt_status: string };

    const live = sockets.at(-1)!;
    await live.server.close();
    await live.page.close({ code: 4000, reason: "e2e network cut" });
    await expect.poll(async () => (await detail()).attempt_status, { timeout: 90_000, intervals: [3000] }).toBe("interrupted");

    const savedBeforeCut = "# 끊기기 전에 저장한 코드";
    seedInterruptedCoding(applicationId, 45, savedBeforeCut);
    await page.goto(`/exam/${applicationId}/resume`);
    await expect(page.getByText("코딩테스트를 마지막으로 저장된 코드와 남은 시간부터 이어갑니다.")).toBeVisible();
    await passPrecheck(page);
    await page.getByRole("button", { name: "이어서 시작 (전체 화면)" }).click();
    await expect(page).toHaveURL(new RegExp(`/exam/${applicationId}$`));

    await test.step("안내 화면 없이 저장된 코드와 남은 시간부터 이어 간다", async () => {
        expect(await getEditorCode(page, 1)).toBe(savedBeforeCut);
        await expect(page.getByText("AI 면접이 끝났습니다")).toHaveCount(0);
    });

    const marker = "# e2e 자동 저장 확인";
    await setEditorCode(page, 1, `${marker}\nprint(1)\n`);

    await expect(page.getByRole("heading", { name: "✓ 응시가 완료되었습니다." })).toBeVisible({ timeout: 90_000 });
    await expect(page.getByText("시간이 끝나 마지막으로 저장된 코드를 제출했습니다.")).toBeVisible();

    await expect.poll(async () => {
        const s = await (await page.request.get(`/api/applications/${applicationId}/interview/state`)).json() as { attempt_status: string; end_detail: string | null };
        return `${s.attempt_status}/${s.end_detail}`;
    }).toBe("completed/coding_timeout");
    expect(readSavedCode(applicationId, 1)).toContain(marker);
});
