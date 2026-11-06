// 끝까지 응시: 기본 질문 10개 + 꼬리질문 → (코딩테스트) → 응시 완료 → AI 채점 → 결과 공개 → 지원자 결과 화면·메일
// 실제 LLM 이 질문을 만들고 채점하므로 한 테스트에 10분 안팎이 걸린다. 빠른 묶음(npm test)에서는 빠지고
// npm run test:full 에서 돈다 (@slow).
import { readFileSync } from "node:fs";
import path from "node:path";

import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

import { apiAs, BASE_URL, loginByUi, randomPassword, readProblemKeys, readState, releaseResultNow, signupByApi, uniqueEmail, waitForMail } from "../helpers";
import { setEditorCode, answerAllQuestions, applyAndStartInterview } from "./flow";

type Result = { decision: "pass" | "fail"; total_score: string; pass_score: string; interview_score: string | null; coding_score: string | null };
type Detail = {
    attempt_status: string; analysis_status: string; review_reason: string | null; release_status: string;
    result: Result | null; coding: { problem_no: number; passed: number | null; total: number | null }[];
};

// 숨겨진 테스트까지 모두 통과하는 정답. 문제는 지원 건마다 다르므로 배정된 문제 키로 찾는다 (backend/tests/test_coding_bank.py 가 정답을 검증한다)
const SOLUTIONS = JSON.parse(readFileSync(path.join(__dirname, "..", "..", "backend", "tests", "coding_solutions.json"), "utf-8")) as Record<string, string>;

let admin: APIRequestContext;

test.beforeAll(async () => {
    const state = readState();
    admin = await apiAs(state.adminEmail, state.adminPassword);
});

test.afterAll(async () => {
    await admin?.dispose();
});

async function detail(applicationId: string): Promise<Detail> {
    return (await admin.get(`/api/admin/applicants/${applicationId}`)).json() as Promise<Detail>;
}

async function waitForDecision(applicationId: string): Promise<Detail> {
    let last: Detail | null = null;
    // 채점은 worker-eval 이 한 번에 하나씩 한다 (실측 70~181초). 확인 필요(needs_review)가 되면 바로 실패로 본다
    await expect.poll(async () => {
        last = await detail(applicationId);
        if (last.analysis_status === "needs_review") return `needs_review:${last.review_reason}`;
        return last.analysis_status;
    }, { timeout: 15 * 60_000, intervals: [10_000] }).toBe("decided");
    return last!;
}

/**
 * 점수와 판정은 코드가 계산한다 (ai-architecture v1.4, domain/scoring.py):
 * 총점 = 코딩 없으면 면접 점수, 있으면 면접 × (100 − 코딩 비율 30)% + 코딩 × 30%. 총점 ≥ 합격 기준이면 합격.
 */
function expectScoreRules(result: Result, codingRatio: number | null) {
    const total = Number(result.total_score);
    const interview = Number(result.interview_score);
    expect(total).toBeGreaterThanOrEqual(0);
    expect(total).toBeLessThanOrEqual(100);
    const expected = codingRatio === null ? interview : (interview * (100 - codingRatio) + Number(result.coding_score) * codingRatio) / 100;
    expect(Math.abs(total - expected)).toBeLessThanOrEqual(0.01); // 소수 둘째 자리 반올림
    expect(result.decision).toBe(total >= Number(result.pass_score) ? "pass" : "fail");
}

/** 공개 시각을 앞당겨 공개하고, 지원자 결과 화면·알림 메일을 확인한다 */
async function checkReleasedResult(page: Page, applicationId: string, email: string, result: Result) {
    await test.step("공개 전에는 지원자가 결과를 볼 수 없다", async () => {
        await page.goto(`/mypage/results/${applicationId}`);
        await expect(page.getByRole("heading", { name: "아직 결과가 공개되지 않았습니다." })).toBeVisible();
    });

    await test.step("공개 시각이 되면 결과 공개 · 알림 메일", async () => {
        releaseResultNow(applicationId);
        await expect.poll(async () => (await detail(applicationId)).release_status).toBe("released");
        const mail = await waitForMail(email, 60_000);
        expect(mail.subject).toContain("1차 결과가 공개되었습니다");
    });

    await test.step("지원자 결과 화면: 판정만 보이고 점수는 보이지 않는다", async () => {
        await page.goto(`/mypage/results/${applicationId}`);
        await expect(page.getByRole("heading", { level: 1, name: result.decision === "pass" ? "1차 합격" : "1차 불합격" })).toBeVisible();
        // 점수·근거는 지원자에게 주지 않는다 (RPT-03·04)
        await expect(page.getByText(result.total_score, { exact: true })).toHaveCount(0);
    });
}

test.describe("@slow 끝까지 응시", () => {
    test.describe.configure({ timeout: 30 * 60_000 });

    test("코딩테스트 없는 공고: 마지막 질문 뒤 바로 응시 완료 → 채점 → 결과 공개", async ({ page, browser }) => {
        const email = uniqueEmail("e2e-exam");
        const password = randomPassword();
        await signupByApi(email, password, "완주테스트");
        const applicationId = await applyAndStartInterview(page, email, password);

        await test.step("기본 질문 10개 + 꼬리질문에 모두 답한다", async () => {
            const { end, answers } = await answerAllQuestions(page);
            expect(end).toBe("done"); // 코딩테스트 단계를 건너뛴다
            expect(answers).toBeGreaterThanOrEqual(10);
            expect(answers).toBeLessThanOrEqual(14);
            await expect(page.getByText("AI 면접 ✓ 완료")).toBeVisible();
            await expect(page.getByText("코딩테스트 ✓ 제출 완료")).toHaveCount(0);
            await expect.poll(async () => (await detail(applicationId)).attempt_status).toBe("completed");
        });

        const decided = await test.step("AI 채점이 끝나고 코드가 합불을 정한다", async () => {
            const d = await waitForDecision(applicationId);
            expect(d.result).not.toBeNull();
            expect(d.result!.coding_score).toBeNull();
            expectScoreRules(d.result!, null);
            return d;
        });

        await test.step("관리자 상세: 리포트가 보인다", async () => {
            // 지원자 창과 쿠키가 섞이지 않게 관리자는 새 브라우저 컨텍스트에서 로그인한다
            const state = readState();
            const adminContext = await browser.newContext({ baseURL: BASE_URL, viewport: { width: 1440, height: 900 } });
            const adminPage = await adminContext.newPage();
            await loginByUi(adminPage, state.adminEmail, state.adminPassword);
            await expect(adminPage).toHaveURL(/\/admin\/postings/);
            await adminPage.goto(`/admin/applicants/${applicationId}`);
            await expect(adminPage.getByRole("heading", { name: "항목별 점수" })).toBeVisible();
            await adminContext.close();
        });

        await checkReleasedResult(page, applicationId, email, decided.result!);
    });

    test("코딩테스트 있는 공고: 면접 → 코딩 2문항 실행·제출 → 채점(코딩 점수 포함) → 결과 공개", async ({ page }) => {
        const email = uniqueEmail("e2e-exam");
        const password = randomPassword();
        await signupByApi(email, password, "코딩테스트");
        const applicationId = await applyAndStartInterview(page, email, password, { coding: true });

        await test.step("면접 질문에 모두 답하면 코딩테스트 안내가 나온다", async () => {
            const { end, answers } = await answerAllQuestions(page);
            expect(end).toBe("coding");
            expect(answers).toBeGreaterThanOrEqual(10);
            await expect(page.getByRole("heading", { name: "✓ AI 면접이 끝났습니다. 수고하셨습니다." })).toBeVisible();
            await page.getByRole("button", { name: "코딩테스트 시작" }).click();
            await expect(page.getByRole("heading", { name: /^문제 1\./ })).toBeVisible();
        });

        for (const no of [1, 2]) {
            await test.step(`문제 ${no}: 코드 작성 → [실행] 공개 예시 통과`, async () => {
                await page.getByRole("tab", { name: new RegExp(`^문제 ${no} ·`) }).click();
                await expect(page.getByRole("heading", { name: new RegExp(`^문제 ${no}\\.`) })).toBeVisible();
                await setEditorCode(page, no, SOLUTIONS[readProblemKeys(applicationId)[no - 1]]);
                await page.getByRole("button", { name: "▶ 실행" }).click();
                const result = page.locator(".result");
                // 실행은 격리 상자(worker-sandbox)에서 돈다
                await expect(result.getByText("실행 완료")).toBeVisible({ timeout: 60_000 });
                await expect(result).toContainText("예시 1 ✓ 통과");
                await expect(result).toContainText("예시 2 ✓ 통과");
            });
        }

        await test.step("최종 제출 → 응시 완료", async () => {
            await page.getByRole("button", { name: "최종 제출" }).click();
            const dialog = page.getByRole("dialog", { name: "최종 제출" });
            await expect(dialog.getByText("⚠ 작성한 코드가 없습니다")).toHaveCount(0);
            await dialog.getByRole("button", { name: "제출하기" }).click();
            await expect(page.getByRole("heading", { name: "✓ 응시가 완료되었습니다." })).toBeVisible();
            await expect(page.getByText("코딩테스트 ✓ 제출 완료")).toBeVisible();
        });

        const decided = await test.step("숨겨진 테스트 채점 + AI 채점 → 코딩 점수가 들어간 총점으로 합불", async () => {
            const d = await waitForDecision(applicationId);
            expect(d.coding.map((c) => [c.problem_no, c.passed === c.total && (c.total ?? 0) > 0])).toEqual([[1, true], [2, true]]);
            expect(d.result!.coding_score).not.toBeNull();
            expect(Number(d.result!.coding_score)).toBe(100);
            expectScoreRules(d.result!, 30);
            return d;
        });

        await checkReleasedResult(page, applicationId, email, decided.result!);
    });
});
