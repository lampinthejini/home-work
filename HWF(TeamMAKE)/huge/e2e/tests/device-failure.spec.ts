// 면접 연결 준비 중 장치 예외 (논의사항 E1): "연결하고 있습니다…"에서 멈추지 않고 장애 중단으로 처리한다.
import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

import { apiAs, randomPassword, readState, signupByApi, uniqueEmail } from "../helpers";
import { applyAndStartInterview } from "./flow";

let admin: APIRequestContext;

test.beforeAll(async () => {
    const state = readState();
    admin = await apiAs(state.adminEmail, state.adminPassword);
});

test.afterAll(async () => {
    await admin?.dispose();
});

// 환경 점검도 같은 브라우저 기능을 쓰므로 면접 화면(/exam/{id})에서만 실패시킨다.
// 화면 이동이 페이지를 다시 읽지 않을 수 있어 경로는 부를 때 확인한다.
const FAIL_ON_EXAM = {
    mic: () => {
        const original = AudioWorklet.prototype.addModule;
        AudioWorklet.prototype.addModule = function (...args: Parameters<typeof original>) {
            if (/^\/exam\/[^/]+$/.test(location.pathname)) return Promise.reject(new Error("e2e: worklet"));
            return original.apply(this, args);
        };
    },
    camera: () => {
        const Original = window.MediaRecorder;
        window.MediaRecorder = new Proxy(Original, {
            construct(target, args: ConstructorParameters<typeof MediaRecorder>) {
                if (/^\/exam\/[^/]+$/.test(location.pathname)) throw new DOMException("e2e: recorder", "NotSupportedError");
                return new target(...args);
            },
        });
    },
    // 환경 점검을 우회한 경우: 면접 화면에서만 녹화 기능이 없다
    noRecorder: () => {
        const Original = window.MediaRecorder;
        Object.defineProperty(window, "MediaRecorder", {
            configurable: true,
            get: () => (/^\/exam\/[^/]+$/.test(location.pathname) ? undefined : Original),
        });
    },
};

async function expectDeviceFault(page: Page, device: keyof typeof FAIL_ON_EXAM) {
    const email = uniqueEmail("e2e-exam");
    const password = randomPassword();
    await signupByApi(email, password, "장치오류테스트");
    await page.addInitScript(FAIL_ON_EXAM[device]);

    const applicationId = await applyAndStartInterview(page, email, password, { waitFirstQuestion: false });

    await expect(page.getByRole("alertdialog", { name: "카메라나 마이크에 문제가 생겨 면접이 멈췄습니다." })).toBeVisible({ timeout: 30_000 });
    const detail = await (await admin.get(`/api/admin/applicants/${applicationId}`)).json() as { attempt_status: string };
    expect(detail.attempt_status).toBe("interrupted");

    // 장애 중단은 자리를 10분 맡아 둔다(TRD 5-3). 다음 테스트가 들어갈 수 있게 동의를 철회해 돌려준다
    expect((await page.request.post(`/api/applications/${applicationId}/consent/withdraw`)).ok()).toBe(true);
}

test("지원자: 마이크 녹음기를 열 수 없으면 장애 중단", async ({ page }) => {
    await expectDeviceFault(page, "mic");
});

test("지원자: 카메라 녹화기를 만들 수 없으면 장애 중단", async ({ page }) => {
    await expectDeviceFault(page, "camera");
});

test("지원자: 면접 화면에 녹화 기능이 없으면 녹화 없이 진행하지 않고 장애 중단", async ({ page }) => {
    await expectDeviceFault(page, "noRecorder");
});

test("지원자: 카메라 녹화를 할 수 없는 브라우저는 환경 점검을 통과하지 못한다", async ({ page }) => {
    const email = uniqueEmail("e2e-exam");
    const password = randomPassword();
    await signupByApi(email, password, "장치오류테스트");
    await page.addInitScript(() => {
        const Original = window.MediaRecorder;
        window.MediaRecorder = new Proxy(Original, {
            construct(target, args: ConstructorParameters<typeof MediaRecorder>) {
                if (location.pathname.endsWith("/precheck")) throw new DOMException("e2e: recorder", "NotSupportedError");
                return new target(...args);
            },
        });
    });

    await applyAndStartInterview(page, email, password, { stopAtPrecheck: true });

    await expect(page.getByText("이 브라우저에서는 카메라 녹화를 할 수 없습니다.")).toBeVisible({ timeout: 30_000 });
    await page.getByRole("button", { name: "▶ 테스트음 재생" }).click();
    await page.getByRole("button", { name: "들립니다" }).click();
    await page.waitForTimeout(3000);
    await expect(page.getByRole("button", { name: "다음: 시작 안내 ▶" })).toBeDisabled();
});

test("지원자: 마이크를 여는 도중 면접 화면을 벗어나면 면접 연결을 만들지 않는다", async ({ page }) => {
    const email = uniqueEmail("e2e-exam");
    const password = randomPassword();
    await signupByApi(email, password, "장치오류테스트");

    let sockets = 0;
    await page.routeWebSocket(/\/ws\/interview\//, (ws) => {
        sockets += 1;
        ws.connectToServer();
    });
    // 면접 화면에서 addModule 을 붙잡아 두었다가 화면을 벗어난 뒤에 끝낸다
    await page.addInitScript(() => {
        const original = AudioWorklet.prototype.addModule;
        const gate = window as unknown as { workletHeld?: boolean; releaseWorklet?: () => void };
        AudioWorklet.prototype.addModule = async function (...args: Parameters<typeof original>) {
            if (/^\/exam\/[^/]+$/.test(location.pathname)) {
                await new Promise<void>((resolve) => {
                    gate.workletHeld = true;
                    gate.releaseWorklet = resolve;
                });
            }
            return original.apply(this, args);
        };
    });

    const applicationId = await applyAndStartInterview(page, email, password, { waitFirstQuestion: false });
    await page.waitForFunction(() => (window as unknown as { workletHeld?: boolean }).workletHeld === true);

    // 페이지를 다시 읽으면 스크립트가 통째로 사라져 재현되지 않으므로 앱 안에서 이동한다
    await page.evaluate(() => (window as unknown as { next: { router: { push(href: string): void } } }).next.router.push("/mypage"));
    await expect(page).toHaveURL(/\/mypage/);
    await page.evaluate(() => (window as unknown as { releaseWorklet: () => void }).releaseWorklet());
    await page.waitForTimeout(2000);
    expect(sockets).toBe(0);

    expect((await page.request.post(`/api/applications/${applicationId}/consent/withdraw`)).ok()).toBe(true);
});
