// 지원 → 동의 → 이력서(직접 작성) → 환경 점검 → AI 면접(가짜 카메라·마이크) → 녹화 업로드
// → 화면 이탈 1회 경고 · 2회 응시 취소 (기술아키텍처 "Playwright E2E(장애·이탈)")
// → 관리자: 녹화 재생 · 메모 쓰기/고치기/지우기 → 지원자 탈퇴(데이터 정리)
import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

import { apiAs, loginByUi, randomPassword, readState, signupByApi, uniqueEmail } from "../helpers";
import { applyAndStartInterview, isFullscreen } from "./flow";

type Detail = { attempt_status: string; recordings: { segment_no: number; media_url: string; size_bytes: number }[] };

test.describe.configure({ mode: "serial" });

const email = uniqueEmail("e2e-exam");
const password = randomPassword();
let applicationId = "";
let admin: APIRequestContext;

test.beforeAll(async () => {
    await signupByApi(email, password);
    const state = readState();
    admin = await apiAs(state.adminEmail, state.adminPassword);
});

test.afterAll(async () => {
    await admin?.dispose();
});

async function exitFullscreen(page: Page) {
    await page.evaluate(async () => { if (document.fullscreenElement) await document.exitFullscreen(); });
}

test("지원자: 지원부터 면접 중 화면 이탈 2회 취소까지", async ({ page }) => {
    applicationId = await applyAndStartInterview(page, email, password);

    await test.step("카메라 녹화 조각(10초)이 서버에 올라간다", async () => {
        await expect.poll(async () => {
            const d = await (await admin.get(`/api/admin/applicants/${applicationId}`)).json() as Detail;
            return d.recordings.reduce((sum, r) => sum + r.size_bytes, 0);
        }, { timeout: 60_000, intervals: [3000] }).toBeGreaterThan(0);
    });

    await test.step("화면 이탈 1회: 경고 후 돌아가기", async () => {
        await exitFullscreen(page);
        const warn = page.getByRole("alertdialog", { name: "화면 이탈이 감지되었습니다 (1 / 2)" });
        await expect(warn).toBeVisible();
        await warn.getByRole("button", { name: "확인하고 돌아가기" }).click();
        await expect(warn).toBeHidden();
        await expect.poll(() => isFullscreen(page)).toBe(true);
    });

    await test.step("화면 이탈 2회: 응시 취소", async () => {
        // 탭 전환 한 번에 여러 신호가 오는 것을 하나로 묶는 유예(1.5초)가 지난 뒤 다시 이탈한다
        await page.waitForTimeout(2500);
        await exitFullscreen(page);
        await expect(page.getByRole("alertdialog", { name: "응시가 취소되었습니다." })).toBeVisible();
        await expect.poll(async () => {
            const d = await (await admin.get(`/api/admin/applicants/${applicationId}`)).json() as Detail;
            return d.attempt_status;
        }).toBe("cancelled");
    });
});

test("관리자: 녹화 재생과 메모", async ({ page }) => {
    test.skip(!applicationId, "앞 테스트가 지원을 만들지 못했습니다");
    const state = readState();
    await loginByUi(page, state.adminEmail, state.adminPassword);
    await expect(page).toHaveURL(/\/admin\/postings/);
    await page.goto(`/admin/applicants/${applicationId}`);

    await test.step("장애·이탈 기록 탭: 녹화 재생", async () => {
        await page.getByRole("tab", { name: "장애·이탈 기록" }).click();
        const video = page.getByLabel("접속 구간 1 녹화");
        await expect(video).toBeVisible();
        const media = page.waitForResponse((r) => r.url().includes(`/api/admin/media/recordings/${applicationId}/1`));
        await video.evaluate((v: HTMLVideoElement) => { v.muted = true; void v.play(); });
        const res = await media;
        expect(res.status()).toBe(200);
        expect(res.headers()["content-type"]).toContain("video/webm");
        // 메타데이터를 읽었고(재생 가능), 오류가 없다
        await expect.poll(() => video.evaluate((v: HTMLVideoElement) => ({ ready: v.readyState >= 1, error: v.error?.code ?? 0 })))
            .toEqual({ ready: true, error: 0 });
    });

    await test.step("메모 쓰기 → 고치기 → 지우기", async () => {
        await page.getByRole("tab", { name: /^메모/ }).click();
        await page.getByLabel("새 메모").fill("E2E 메모: 화면 이탈 2회로 취소됨");
        await page.getByRole("button", { name: "저장" }).click();
        await expect(page.getByText("E2E 메모: 화면 이탈 2회로 취소됨")).toBeVisible();
        await expect(page.getByRole("tab", { name: "메모 1" })).toBeVisible();

        await page.getByRole("button", { name: "수정" }).click();
        await page.getByLabel("메모 고치기").fill("E2E 메모(수정): 녹화 확인 완료");
        await page.getByRole("button", { name: "저장" }).last().click();
        await expect(page.getByText("E2E 메모(수정): 녹화 확인 완료")).toBeVisible();

        await page.getByRole("button", { name: "삭제" }).click();
        await page.getByRole("dialog", { name: "메모를 삭제할까요?" }).getByRole("button", { name: "삭제" }).click();
        await expect(page.getByText("아직 작성한 메모가 없습니다")).toBeVisible();
    });
});

test("지원자: 탈퇴하면 지원 데이터도 지워진다", async ({ page }) => {
    test.skip(!applicationId, "앞 테스트가 지원을 만들지 못했습니다");
    test.skip(process.env.E2E_KEEP === "1", "E2E_KEEP=1: 브라우저 확인용으로 지원 데이터를 남겨 둡니다");
    await loginByUi(page, email, password);
    await expect(page).toHaveURL(/\/jobs/);
    await page.goto("/mypage?tab=account");
    await page.getByRole("button", { name: "회원 탈퇴" }).click();
    const dialog = page.getByRole("dialog", { name: "정말 탈퇴할까요?" });
    await dialog.getByRole("textbox", { name: "비밀번호", exact: true }).fill(password);
    await dialog.getByLabel("확인을 위해 '탈퇴'를 입력해 주세요").fill("탈퇴");
    await dialog.getByRole("button", { name: "탈퇴" }).click();
    await expect(page).not.toHaveURL(/\/mypage/);
    await expect.poll(async () => (await admin.get(`/api/admin/applicants/${applicationId}`)).status()).toBe(404);
});
