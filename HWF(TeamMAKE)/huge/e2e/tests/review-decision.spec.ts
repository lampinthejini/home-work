// 자동 채점을 끝내지 못한 건: 관리자가 사유를 쓰고 직접 결정하면 지원자에게 '담당자가 정한 결과'로 공개된다 (CONFLICTS U8)
import { expect, test } from "@playwright/test";

import { apiAs, loginByUi, randomPassword, readState, releaseResultNow, seedNeedsReview, signupByApi, uniqueEmail } from "../helpers";

// teardown 이 e2e-exam-* 지원자를 정리하므로 같은 접두어를 쓴다
const email = uniqueEmail("e2e-exam");
const password = randomPassword();

test("관리자: 평가 지연 건을 직접 결정하고, 지원자는 담당자 결정임을 본다", async ({ browser, page }) => {
    const state = readState();
    await signupByApi(email, password, "직접결정");
    const applicationId = seedNeedsReview(email, state.postingId);

    const adminContext = await browser.newContext();
    const adminPage = await adminContext.newPage();
    await loginByUi(adminPage, state.adminEmail, state.adminPassword);
    await expect(adminPage).toHaveURL(/\/admin\/postings/);
    await adminPage.goto(`/admin/applicants/${applicationId}`);
    await expect(adminPage.getByText("평가 지연", { exact: true })).toBeVisible();
    await expect(adminPage.getByText(/까지 결정하지 않으면 재채점 실패 시 평가 미완료로 불합격 처리됩니다/)).toBeVisible();

    const passButton = adminPage.getByRole("button", { name: "1차 합격으로 결정" });
    await expect(passButton).toBeDisabled(); // 사유 없이는 못 정한다
    await adminPage.getByLabel("결정 사유").fill("이력서와 응시 자료를 직접 확인하고 합격으로 판단했습니다");
    await passButton.click();
    await adminPage.getByRole("button", { name: "결정", exact: true }).click();
    await expect(adminPage.getByText("담당자 결정")).toBeVisible();
    await expect(adminPage.getByText("1차 합격", { exact: true })).toBeVisible();
    await expect(adminPage.getByText("총점")).toHaveCount(0); // 채점하지 않았으니 점수를 보이지 않는다
    await adminContext.close();

    const admin = await apiAs(state.adminEmail, state.adminPassword);
    const again = await admin.post(`/api/admin/analysis/${applicationId}/decision`, { data: { decision: "fail", reason: "결정을 바꾸려는 시도입니다" } });
    expect(again.status()).toBe(409);
    await admin.dispose();

    releaseResultNow(applicationId);
    await loginByUi(page, email, password);
    await expect(page).not.toHaveURL(/\/login/);
    await page.goto(`/mypage/results/${applicationId}`);
    await expect(page.getByRole("heading", { name: "1차 합격" })).toBeVisible();
    await expect(page.getByText("담당자가 응시 자료를 확인하고 결과를 정했습니다")).toBeVisible();
    await expect(page.getByText("AI가 생성한 결과입니다")).toHaveCount(0);
});
