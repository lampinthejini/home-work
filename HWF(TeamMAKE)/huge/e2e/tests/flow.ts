// 여러 테스트가 같이 쓰는 지원자 흐름: 로그인 → 지원 → 동의 → 이력서 → 환경 점검 → 면접 시작 → 첫 질문
import { expect, test, type Page } from "@playwright/test";

import { loginByUi, readState } from "../helpers";

/** 환경 점검 5개 통과. 카메라·마이크는 가짜 장치, 스피커는 '들립니다'를 누른다 (처음 점검·이어가기 재점검 공통) */
export async function passPrecheck(page: Page): Promise<void> {
    await page.getByRole("button", { name: "▶ 테스트음 재생" }).click();
    await page.getByRole("button", { name: "들립니다" }).click();
    await expect(page.getByText("5개 항목을 모두 통과했습니다")).toBeVisible({ timeout: 60_000 });
}

export async function isFullscreen(page: Page): Promise<boolean> {
    return page.evaluate(() => !!document.fullscreenElement);
}

/** E2E 공고에 지원해 면접을 시작하고, 첫 질문의 '답변 완료' 버튼이 보일 때까지 간다. 지원 ID 를 돌려준다 */
export async function applyAndStartInterview(page: Page, email: string, password: string): Promise<string> {
    const state = readState();
    let applicationId = "";
    await loginByUi(page, email, password);
    await expect(page).toHaveURL(/\/jobs/);

    await test.step("공고 상세에서 지원하기", async () => {
        await page.goto(`/jobs/${state.postingId}`);
        await expect(page.getByText(state.postingTitle).first()).toBeVisible();
        await page.getByRole("button", { name: "지원하기" }).click();
        await expect(page).toHaveURL(/\/apply\/[\w-]+\/consent/);
        applicationId = page.url().match(/\/apply\/([\w-]+)\//)![1];
    });

    await test.step("동의 5개", async () => {
        const next = page.getByRole("button", { name: "동의하고 다음 ▶" });
        await expect(next).toBeDisabled();
        await page.getByLabel("전체 동의").check();
        await next.click();
        await expect(page).toHaveURL(/\/resume$/);
    });

    await test.step("이력서 직접 작성 → 제출", async () => {
        await page.getByRole("radio", { name: /직접 작성/ }).click();
        await page.getByRole("button", { name: "다음 ▶" }).click();
        await expect(page).toHaveURL(/\/resume\/confirm/);
        await page.getByLabel("성명").fill("이투이");
        await page.locator("#field-education").getByRole("button", { name: "+ 추가" }).click();
        await page.locator("#field-education").getByLabel("학교").fill("한국대학교");
        await page.locator("#field-education").getByLabel("전공").fill("컴퓨터공학");
        await page.getByRole("button", { name: "이력서 제출 ▶" }).click();
        await page.getByRole("dialog").getByRole("button", { name: "제출하기" }).click();
        await expect(page).toHaveURL(/\/precheck/);
    });

    await test.step("환경 점검 5개 통과 (가짜 카메라·마이크)", async () => {
        await passPrecheck(page);
        await page.getByRole("button", { name: "다음: 시작 안내 ▶" }).click();
        await expect(page).toHaveURL(/\/rules/);
    });

    await test.step("시작 안내 → 전체 화면으로 면접 시작", async () => {
        await page.getByLabel("위 응시 규칙을 모두 확인했습니다.").check();
        await page.getByRole("button", { name: /면접 시작/ }).click();
        await expect(page).toHaveURL(new RegExp(`/exam/${applicationId}$`));
        await expect.poll(() => isFullscreen(page)).toBe(true);
    });

    await test.step("첫 질문이 나오고 답변을 녹음한다", async () => {
        // 질문 10개를 RAG + LLM 으로 만드는 동안 '준비 중' 화면이 나올 수 있다
        await expect(page.getByLabel(/질문 1 \/ \d+/)).toBeVisible({ timeout: 4 * 60_000 });
        await expect(page.getByRole("button", { name: "답변 완료" })).toBeVisible({ timeout: 90_000 });
    });

    return applicationId;
}
