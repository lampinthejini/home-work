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

/**
 * E2E 공고에 지원해 면접을 시작하고, 첫 질문의 '답변 완료' 버튼이 보일 때까지 간다. 지원 ID 를 돌려준다.
 * coding: true 면 코딩테스트가 켜진 공고에 지원한다.
 */
export async function applyAndStartInterview(page: Page, email: string, password: string, { coding = false } = {}): Promise<string> {
    const state = readState();
    const postingId = coding ? state.codingPostingId : state.postingId;
    const postingTitle = coding ? state.codingPostingTitle : state.postingTitle;
    let applicationId = "";
    await loginByUi(page, email, password);
    await expect(page).toHaveURL(/\/jobs/);

    await test.step("공고 상세에서 지원하기", async () => {
        await page.goto(`/jobs/${postingId}`);
        await expect(page.getByText(postingTitle).first()).toBeVisible();
        await page.getByRole("button", { name: "지원하기" }).click();
        await expect(page).toHaveURL(/\/apply\/[\w-]+\/consent/);
        applicationId = page.url().match(/\/apply\/([\w-]+)\//)![1];
    });

    await test.step("동의 5개", async () => {
        await expect(page.getByText("카메라 녹화(영상과 마이크 소리)")).toBeVisible();
        await expect(page.getByText(/2회 응시 취소 · 연결이 끊기면 이어가기 3회까지/)).toBeVisible();
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

/**
 * 지금 질문부터 마지막 질문까지 답한다. 기본 질문 10개 + 꼬리질문(AI 가 정함, 최대 4개).
 * 각 답변은 answerMs 동안 가짜 마이크(answer.wav)로 말한 뒤 [답변 완료]를 누른다.
 * 끝나면 'done'(응시 완료 화면) 또는 'coding'(코딩테스트 안내 화면)과 답한 횟수를 돌려준다.
 */
export async function answerAllQuestions(page: Page, { answerMs = 8000, maxAnswers = 16 } = {}): Promise<{ end: "done" | "coding"; answers: number }> {
    const answerButton = page.getByRole("button", { name: "답변 완료" });
    const done = page.getByRole("heading", { name: "✓ 응시가 완료되었습니다." });
    const codingStart = page.getByRole("button", { name: "코딩테스트 시작" });
    let answers = 0;
    for (;;) {
        // 다음 질문은 STT 마무리 + 꼬리질문 판단(LLM) + 질문 읽기(TTS)를 거쳐 나온다
        await expect(answerButton.or(done).or(codingStart)).toBeVisible({ timeout: 3 * 60_000 });
        if (await done.isVisible()) return { end: "done", answers };
        if (await codingStart.isVisible()) return { end: "coding", answers };
        if (answers >= maxAnswers) throw new Error(`답변을 ${answers}번 했는데도 면접이 끝나지 않았습니다`);
        const progress = await page.locator(".progress-dots").getAttribute("aria-label");
        await page.waitForTimeout(answerMs);
        await answerButton.click();
        answers += 1;
        await expect(answerButton).toBeHidden();
        test.info().annotations.push({ type: "answer", description: `${answers}번째 답변 (${progress})` });
    }
}
