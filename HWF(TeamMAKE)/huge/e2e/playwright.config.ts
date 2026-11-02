import path from "node:path";

import { defineConfig } from "@playwright/test";

import { BASE_URL } from "./helpers";

// 실제 Docker 스택에 붙는 E2E. AI(STT·TTS·LLM)도 진짜로 돌아서 느리므로 한 번에 하나씩 순서대로 돈다.
// 카메라·마이크는 Chromium 가짜 장치를 쓰고, 마이크 소리는 fixtures/answer.wav(TTS 로 만든 한국어 답변)를 되풀이한다.
const FAKE_AUDIO = path.join(__dirname, "fixtures", "answer.wav");

export default defineConfig({
    testDir: "./tests",
    fullyParallel: false,
    workers: 1,
    retries: 0,
    timeout: 6 * 60_000,
    expect: { timeout: 15_000 },
    reporter: [["list"], ["html", { open: "never" }]],
    globalSetup: "./global-setup.ts",
    globalTeardown: "./global-teardown.ts",
    use: {
        baseURL: BASE_URL,
        actionTimeout: 20_000,
        navigationTimeout: 30_000,
        locale: "ko-KR",
        timezoneId: "Asia/Seoul",
        viewport: { width: 1440, height: 900 },
        permissions: ["camera", "microphone"],
        trace: "retain-on-failure",
        screenshot: "only-on-failure",
        video: "retain-on-failure",
        launchOptions: {
            args: [
                "--use-fake-ui-for-media-stream",
                "--use-fake-device-for-media-stream",
                `--use-file-for-fake-audio-capture=${FAKE_AUDIO}`,
                "--autoplay-policy=no-user-gesture-required",
            ],
        },
    },
    projects: [{ name: "chromium", use: { browserName: "chromium" } }],
});
