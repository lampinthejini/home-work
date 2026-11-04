import { expect, test } from "@playwright/test";

import { apiAs, loginByUi, randomPassword, readState, signupByApi, uniqueEmail } from "../helpers";

// teardown 이 e2e-exam-* 지원자를 정리하므로 같은 접두어를 쓴다
const email = uniqueEmail("e2e-exam");
const password = randomPassword();

const CONSENT = {
    consent_version: "v1.7",
    items: { data_collection: true, ai_decision: true, share_with_admin: true, retention: true, exam_rules: true },
};
const RESUME_TEXT = "Name Hong Gildong. Education Hankuk University Computer Science. Career Backend developer at Ganada Electronics. Skills Python Java SQL.";
const PDF = Buffer.from(`%PDF-1.4
1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj
2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj
3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 900 200]/Contents 4 0 R/Resources<</Font<</F1<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>>>>>>>endobj
4 0 obj<</Length ${RESUME_TEXT.length + 34}>>stream
BT /F1 10 Tf 20 100 Td (${RESUME_TEXT}) Tj ET
endstream endobj
trailer<</Root 1 0 R>>
%%EOF`);

test("지원자: 이력서 PDF 를 별도 프로세스로 읽어 정리하고, 깨진 PDF 는 거부한다", async () => {
    test.setTimeout(180_000);
    const state = readState();
    await signupByApi(email, password, "업로드시험");
    const ctx = await apiAs(email, password);
    const applied = await ctx.post("/api/applications", { data: { posting_id: state.postingId } });
    expect(applied.ok(), await applied.text()).toBeTruthy();
    const applicationId = (await applied.json()).application_id;
    const url = `/api/applications/${applicationId}/resume/upload`;

    const broken = await ctx.post(url, { multipart: { file: { name: "broken.pdf", mimeType: "application/pdf", buffer: Buffer.from("%PDF-1.7 not really a pdf") } } });
    expect(broken.status()).toBe(400);
    expect((await broken.json()).code).toBe("PDF_BROKEN");

    const accepted = await ctx.post(url, { multipart: { file: { name: "resume.pdf", mimeType: "application/pdf", buffer: PDF } } });
    expect(accepted.status(), await accepted.text()).toBe(202);
    expect((await accepted.json()).pages).toEqual({ text: 1, scanned: 0 });

    await expect.poll(async () => {
        const res = await ctx.get(`/api/applications/${applicationId}/resume/extract-status`);
        return (await res.json()).stage;
    }, { timeout: 150_000, intervals: [2_000] }).toBe("done");
    await ctx.dispose();
});

test("지원자: 못 읽는 파일은 이유를 알려 주고 직접 입력으로 넘어간다", async ({ browser }) => {
    const state = readState();
    const manualEmail = uniqueEmail("e2e-exam");
    await signupByApi(manualEmail, password, "직접입력");
    const ctx = await apiAs(manualEmail, password);
    const applied = await ctx.post("/api/applications", { data: { posting_id: state.postingId } });
    const applicationId = (await applied.json()).application_id;
    const consent = await ctx.post(`/api/applications/${applicationId}/consent`, { data: CONSENT });
    expect(consent.status(), await consent.text()).toBe(201);
    await ctx.dispose();

    const context = await browser.newContext();
    const page = await context.newPage();
    await loginByUi(page, manualEmail, password);
    await expect(page).not.toHaveURL(/\/login/);
    await page.goto(`/apply/${applicationId}/resume`);
    await page.getByText("파일 업로드", { exact: false }).first().click();

    await page.locator("input[type='file']").setInputFiles({ name: "broken.pdf", mimeType: "application/pdf", buffer: Buffer.from("%PDF-1.7 not really a pdf") });
    const dialog = page.getByRole("dialog");
    await expect(dialog.getByText("파일이 손상되어 열 수 없습니다")).toBeVisible();
    await dialog.getByRole("button", { name: "직접 입력" }).click();
    await expect(page).toHaveURL(/\/resume\/confirm/);
    await context.close();
});
