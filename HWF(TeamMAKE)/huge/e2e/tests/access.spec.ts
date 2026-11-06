// 권한: 로그인 안 함 · 다른 지원자의 지원 건 · 지원자의 관리자 경로 (TC-012~015)
import { expect, request, test } from "@playwright/test";

import { apiAs, BASE_URL, loginByUi, randomPassword, readState, signupByApi, uniqueEmail } from "../helpers";

test("로그인하지 않으면 전용 화면은 로그인으로 보내고 API 는 401 이다", async ({ page }) => {
    await page.goto("/mypage");
    await expect(page).toHaveURL(/\/login\?next=(%2F|\/)mypage/);
    await page.goto("/admin/postings");
    await expect(page).toHaveURL(/\/login\?next=(%2F|\/)admin(%2F|\/)postings/);

    const anonymous = await request.newContext({ baseURL: BASE_URL });
    expect((await anonymous.get("/api/me/applications")).status()).toBe(401);
    await anonymous.dispose();
});

test("다른 지원자의 지원 건은 화면도 API 도 없는 것처럼 404 이다", async ({ page }) => {
    const ownerEmail = uniqueEmail("e2e-exam");
    const strangerEmail = uniqueEmail("e2e-exam");
    const password = randomPassword();
    await signupByApi(ownerEmail, password);
    await signupByApi(strangerEmail, password);

    const owner = await apiAs(ownerEmail, password);
    const created = await owner.post("/api/applications", { data: { posting_id: readState().postingId } });
    expect(created.ok(), await created.text()).toBe(true);
    const applicationId = ((await created.json()) as { application_id: string }).application_id;

    const stranger = await apiAs(strangerEmail, password);
    expect((await stranger.get(`/api/applications/${applicationId}`)).status()).toBe(404);
    expect((await stranger.get(`/api/me/results/${applicationId}`)).status()).toBe(404);
    expect((await stranger.post(`/api/applications/${applicationId}/consent/withdraw`)).status()).toBe(404);
    // 남의 철회 요청이 실제 지원 건을 건드리지 않았다
    expect((await owner.get(`/api/applications/${applicationId}`)).status()).toBe(200);

    await loginByUi(page, strangerEmail, password);
    await expect(page).toHaveURL(/\/jobs/);
    await page.goto(`/apply/${applicationId}/consent`);
    await expect(page.getByRole("heading", { name: "찾을 수 없는 페이지입니다" })).toBeVisible();

    await owner.dispose();
    await stranger.dispose();
});

test("지원자가 관리자 경로에 가면 API 는 403, 화면은 공고 목록과 안내다", async ({ page }) => {
    const email = uniqueEmail("e2e-exam");
    const password = randomPassword();
    await signupByApi(email, password);

    const applicant = await apiAs(email, password);
    expect((await applicant.get("/api/admin/postings")).status()).toBe(403);
    await applicant.dispose();

    await loginByUi(page, email, password);
    await expect(page).toHaveURL(/\/jobs/);
    await page.goto("/admin/postings");
    await expect(page).toHaveURL(/\/jobs/);
    await expect(page.locator("span").filter({ hasText: "접근 권한이 없습니다" })).toBeVisible(); // 토스트 (화면 낭독용 사본과 구분)
});
