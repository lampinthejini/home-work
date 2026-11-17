// html/*.html → 개인용/가이드/*.pdf (프로젝트 e2e 의 Playwright 크롬 사용)
const path = require("path");
const fs = require("fs");
const { chromium } = require(path.join("C:/big21/hw-repo/HWF(TeamMAKE)/huge/e2e/node_modules", "playwright"));

const htmlDir = path.join(__dirname, "html");
const outDir = "C:/big21/hw-repo/HWF(TeamMAKE)/개인용/가이드";

(async () => {
    const browser = await chromium.launch();
    const page = await browser.newPage();
    for (const f of fs.readdirSync(htmlDir).filter((x) => x.endsWith(".html"))) {
        await page.goto("file:///" + path.join(htmlDir, f).replace(/\\/g, "/"));
        const out = path.join(outDir, f.replace(".html", ".pdf"));
        await page.pdf({
            path: out, format: "A4", printBackground: true, preferCSSPageSize: true,
            displayHeaderFooter: true, headerTemplate: "<div></div>",
            footerTemplate: '<div style="width:100%;font-size:8px;color:#8a94a6;text-align:center;font-family:Malgun Gothic">'
                + f.replace(".html", "").replace(/_/g, " ") + ' · <span class="pageNumber"></span> / <span class="totalPages"></span></div>',
        });
        console.log(out);
    }
    await browser.close();
})();
