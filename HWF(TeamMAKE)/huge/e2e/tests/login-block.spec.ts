import { expect, test, type Page } from "@playwright/test";

import { loginByUi, randomPassword, readState, signupByApi, uniqueEmail } from "../helpers";

// teardown 이 e2e-exam-* 지원자를 정리하므로 같은 접두어를 쓴다
const email = uniqueEmail("e2e-exam");
const password = randomPassword();

// 이 PC 의 접속은 차단 제외라, 헤더로 외부 IP 를 흉내 낸다. 테스트마다 다른 IP 를 쓴다
const outsideIp = `203.0.113.${Math.floor(Math.random() * 250) + 1}`;

async function tryLogin(page: Page, loginEmail: string, loginPassword: string): Promise<void> {
    await page.getByLabel("이메일").fill(loginEmail);
    await page.locator("input[autocomplete='current-password']").fill(loginPassword);
    await page.getByRole("button", { name: "로그인", exact: true }).click();
}

test("지원자: 같은 IP 에서 5번 틀리면 차단되고, 관리자가 해제하면 다시 로그인한다", async ({ browser }) => {
    const state = readState();
    await signupByApi(email, password, "차단시험");

    const outside = await browser.newContext({ extraHTTPHeaders: { "X-Forwarded-For": outsideIp } });
    const page = await outside.newPage();
    await page.goto("/login");
    const alert = page.getByRole("alert");
    for (let i = 0; i < 4; i++) {
        await tryLogin(page, `nobody${i}@example.com`, "Wrong#Pass2026");
        await expect(alert.filter({ hasText: "이메일 또는 비밀번호가 올바르지 않습니다" })).toBeVisible();
    }
    await tryLogin(page, "nobody4@example.com", "Wrong#Pass2026");
    const blocked = alert.filter({ hasText: "문의 코드" });
    await expect(blocked).toBeVisible();
    const code = /문의 코드 ([0-9A-F]{6})/.exec((await blocked.textContent()) ?? "")?.[1];
    expect(code).toBeTruthy();

    // 맞는 비밀번호도 막힌다
    await tryLogin(page, email, password);
    await expect(blocked).toBeVisible();
    await expect(page).toHaveURL(/\/login/);

    // 막힌 곳에서도 관리자는 맞는 비밀번호로 들어온다
    const adminOutside = await browser.newContext({ extraHTTPHeaders: { "X-Forwarded-For": outsideIp } });
    const adminPage = await adminOutside.newPage();
    await loginByUi(adminPage, state.adminEmail, state.adminPassword);
    await expect(adminPage).toHaveURL(/\/admin\/postings/);

    await adminPage.goto("/admin/dashboard");
    const row = adminPage.locator("div.row").filter({ hasText: `문의 코드 ${code}` });
    await expect(row).toBeVisible();
    await row.getByRole("button", { name: "해제" }).click();
    await expect(row).toHaveCount(0);

    await tryLogin(page, email, password);
    await expect(page).toHaveURL(/\/jobs/);

    await outside.close();
    await adminOutside.close();
});

test("이 PC(차단 제외)에서는 여러 번 틀려도 막히지 않는다", async ({ page }) => {
    await page.goto("/login");
    for (let i = 0; i < 6; i++) {
        await tryLogin(page, `nobody${i}@example.com`, "Wrong#Pass2026");
        await expect(page.getByRole("alert").filter({ hasText: "이메일 또는 비밀번호가 올바르지 않습니다" })).toBeVisible();
    }
});
