// 장애 중단 → 이어가기 (기술아키텍처 "Playwright E2E(장애·이탈)", TRD 7-2)
// 면접 중 인터넷이 끊기면 '장애 중단(interrupted)' — 화면 이탈과 달리 지원자 잘못이 아니므로 감점·취소 없이
// 마이페이지에서 재점검 후 끊긴 질문부터 다시 진행한다.
import { expect, test, type APIRequestContext, type WebSocketRoute } from "@playwright/test";

import { apiAs, randomPassword, readState, signupByApi, uniqueEmail } from "../helpers";
import { applyAndStartInterview, isFullscreen, passPrecheck } from "./flow";

// teardown 이 e2e-exam-* 지원자를 정리하므로 같은 접두어를 쓴다
const email = uniqueEmail("e2e-exam");
const password = randomPassword();
let admin: APIRequestContext;

test.beforeAll(async () => {
    await signupByApi(email, password, "장애테스트");
    const state = readState();
    admin = await apiAs(state.adminEmail, state.adminPassword);
});

test.afterAll(async () => {
    await admin?.dispose();
});

test("지원자: 면접 중 연결이 끊기면 장애 중단, 마이페이지에서 이어간다", async ({ page }) => {
    // setOffline 만으로는 이미 열린 WebSocket 이 끊기지 않는다(Chromium). 그래서 면접 WebSocket 을 중간에서 이어 주다가
    // 끊을 때 양쪽을 닫는다. 이어 주는 동안은 메시지를 그대로 전달한다 (connectToServer 기본 동작)
    const sockets: { page: WebSocketRoute; server: WebSocketRoute }[] = [];
    await page.routeWebSocket(/\/ws\/interview\//, (ws) => {
        sockets.push({ page: ws, server: ws.connectToServer() });
    });

    const applicationId = await applyAndStartInterview(page, email, password);
    const attemptStatus = async () =>
        ((await (await admin.get(`/api/admin/applicants/${applicationId}`)).json()) as { attempt_status: string }).attempt_status;

    await test.step("인터넷이 끊기면 '연결이 끊겼습니다' 안내, 이어가기 버튼은 꺼져 있다", async () => {
        await page.context().setOffline(true);
        const live = sockets.at(-1)!;
        await live.server.close();
        await live.page.close({ code: 4000, reason: "e2e network cut" });
        const paused = page.getByRole("alertdialog", { name: "연결이 끊겼습니다." });
        // 소켓이 닫히고 약 17초 뒤 서버 상태를 확인한다. 오프라인이라 서버를 못 읽어도 같은 안내가 나온다 (서버는 15초 뒤 장애로 판정)
        await expect(paused).toBeVisible({ timeout: 90_000 });
        await expect(paused.getByText("연결 안 됨")).toBeVisible();
        await expect(paused.getByRole("button", { name: "마이페이지에서 이어가기" })).toBeDisabled();
    });

    await test.step("서버도 장애 중단으로 기록한다 (취소가 아님)", async () => {
        await expect.poll(attemptStatus, { timeout: 90_000, intervals: [3000] }).toBe("interrupted");
    });

    await test.step("다시 연결되면 버튼이 켜지고 마이페이지로 간다", async () => {
        await page.context().setOffline(false);
        const paused = page.getByRole("alertdialog", { name: "연결이 끊겼습니다." });
        await expect(paused.getByText("다시 연결됨")).toBeVisible();
        // 오프라인일 때는 꺼진 button, 온라인이 되면 /mypage 로 가는 link 로 바뀐다
        await paused.getByRole("link", { name: "마이페이지에서 이어가기" }).click();
        await expect(page).toHaveURL(/\/mypage/);
    });

    await test.step("마이페이지 → 면접 이어가기 → 재점검", async () => {
        // 위쪽 안내 띠와 지원 카드에 같은 버튼이 두 개 있다
        await page.getByRole("link", { name: "면접 이어가기" }).first().click();
        await expect(page).toHaveURL(new RegExp(`/exam/${applicationId}/resume$`));
        await expect(page.getByText("시스템 장애로 확인되었습니다.")).toBeVisible();
        await expect(page.getByText("1번 질문부터 처음부터 다시 시작합니다. 감점은 없습니다.")).toBeVisible();
        await passPrecheck(page);
    });

    await test.step("이어서 시작하면 끊긴 1번 질문부터 다시 진행된다", async () => {
        await page.getByRole("button", { name: "이어서 시작 (전체 화면)" }).click();
        await expect(page).toHaveURL(new RegExp(`/exam/${applicationId}$`));
        await expect.poll(() => isFullscreen(page)).toBe(true);
        await expect(page.getByLabel(/질문 1 \/ \d+/)).toBeVisible({ timeout: 90_000 });
        await expect(page.getByRole("button", { name: "답변 완료" })).toBeVisible({ timeout: 90_000 });
        await expect.poll(attemptStatus).toBe("interviewing");
    });
});
