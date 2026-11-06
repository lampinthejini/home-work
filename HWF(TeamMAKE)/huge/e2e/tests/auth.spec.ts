// 회원가입 · 로그인 · 로그아웃 · 비밀번호 찾기(재설정 메일은 Mailpit) — 화면정의서 S-C01~S-C03
import { expect, request, test } from "@playwright/test";

import { BASE_URL, loginByUi, randomPassword, signupByApi, uniqueEmail, waitForMail } from "../helpers";

test("회원가입 → 로그인 → 비밀번호 찾기 메일 → 새 비밀번호로 로그인 → 탈퇴", async ({ page }) => {
    const email = uniqueEmail("e2e-auth");
    const password = randomPassword();

    await test.step("회원가입", async () => {
        await page.goto("/signup");
        await page.getByLabel("이름").fill("이투이");
        await page.getByLabel("이메일(아이디)").fill(email);
        await page.getByRole("textbox", { name: "비밀번호", exact: true }).fill(password);
        await page.getByLabel("비밀번호 확인").fill(password);
        await page.getByLabel("휴대전화").fill("01012345678");
        await expect(page.getByLabel("휴대전화")).toHaveValue("010-1234-5678");
        const submit = page.getByRole("button", { name: "가입하기" });
        await expect(submit).toBeDisabled();
        await page.getByLabel("전체 동의").check();
        await submit.click();
        await expect(page).toHaveURL(/\/login\?joined=1/);
        await expect(page.getByText("가입이 완료되었습니다")).toBeVisible();
    });

    await test.step("틀린 비밀번호는 거부, 맞으면 로그인", async () => {
        await loginByUi(page, email, `${password}x`);
        await expect(page.getByRole("alert").filter({ hasText: "이메일 또는 비밀번호가 올바르지 않습니다" })).toBeVisible();
        await loginByUi(page, email, password);
        await expect(page).toHaveURL(/\/jobs/);
        await page.context().clearCookies();
    });

    const newPassword = randomPassword();
    let resetUrl = "";
    await test.step("비밀번호 찾기 → Mailpit 에 재설정 메일 1통", async () => {
        await page.goto("/password/forgot");
        await page.getByLabel("이메일").fill(email);
        await page.getByRole("button", { name: "재설정 링크 받기" }).click();
        await expect(page.getByText("가입된 계정이면 재설정 링크를 보냈습니다")).toBeVisible();
        // 1분 안에 다시 눌러도 메일은 한 통만 간다 (메일 폭탄 방지)
        await page.getByRole("button", { name: "다시 보내기" }).click();
        const mail = await waitForMail(email);
        expect(mail.subject).toBe("비밀번호 재설정 안내");
        resetUrl = mail.text.match(/https?:\/\/\S+\/password\/reset\?token=[\w-]+/)?.[0] ?? "";
        expect(resetUrl).not.toBe("");
        await page.waitForTimeout(3000);
        expect((await waitForMail(email)).count).toBe(1);
    });

    await test.step("메일 링크로 새 비밀번호 정하기", async () => {
        await page.goto(resetUrl);
        await page.getByRole("textbox", { name: "새 비밀번호", exact: true }).fill(newPassword);
        await page.getByLabel("새 비밀번호 확인").fill(newPassword);
        await page.getByRole("button", { name: "변경하기" }).click();
        await expect(page).toHaveURL(/\/login\?reset=1/);
    });

    await test.step("같은 링크는 다시 못 쓴다", async () => {
        await page.goto(resetUrl);
        const again = randomPassword();
        await page.getByRole("textbox", { name: "새 비밀번호", exact: true }).fill(again);
        await page.getByLabel("새 비밀번호 확인").fill(again);
        await page.getByRole("button", { name: "변경하기" }).click();
        await expect(page.getByRole("heading", { name: "링크가 만료되었습니다(30분)" })).toBeVisible();
    });

    await test.step("옛 비밀번호 거부 · 새 비밀번호 로그인", async () => {
        const api = await request.newContext({ baseURL: BASE_URL });
        expect((await api.post("/api/auth/login", { data: { email, password } })).status()).toBe(401);
        await api.dispose();
        await loginByUi(page, email, newPassword);
        await expect(page).toHaveURL(/\/jobs/);
    });

    await test.step("회원 탈퇴 → 다시 로그인 불가", async () => {
        await page.goto("/mypage?tab=account");
        await page.getByRole("button", { name: "회원 탈퇴" }).click();
        const dialog = page.getByRole("dialog", { name: "정말 탈퇴할까요?" });
        await dialog.getByRole("textbox", { name: "비밀번호", exact: true }).fill(newPassword);
        await dialog.getByLabel("확인을 위해 '탈퇴'를 입력해 주세요").fill("탈퇴");
        await dialog.getByRole("button", { name: "탈퇴" }).click();
        await expect(page).not.toHaveURL(/\/mypage/);
        const api = await request.newContext({ baseURL: BASE_URL });
        expect((await api.post("/api/auth/login", { data: { email, password: newPassword } })).status()).toBe(401);
        await api.dispose();
    });
});

test("로그인하면 가려던 화면(next)으로 가고, 이미 로그인했으면 /login 에서 홈으로 간다", async ({ page }) => {
    const email = uniqueEmail("e2e-auth");
    const password = randomPassword();
    await signupByApi(email, password, "이동시험");

    await page.goto("/login?next=/mypage");
    await page.getByLabel("이메일").fill(email);
    await page.locator("input[autocomplete='current-password']").fill(password);
    await page.getByRole("button", { name: "로그인" }).click();
    await expect(page).toHaveURL(/\/mypage$/);
    // 뒤늦은 이동이 덮어쓰지 않는지 잠시 더 본다
    await page.waitForTimeout(2000);
    await expect(page).toHaveURL(/\/mypage$/);

    await page.goto("/login");
    await expect(page).toHaveURL(/\/jobs$/);
});
