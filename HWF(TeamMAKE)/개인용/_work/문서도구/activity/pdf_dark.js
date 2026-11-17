// dark/doc.html → PDF (argv[2]), 첫 쪽·한 쪽 미리보기 PNG 도 남긴다
const path = require("path");
const { pathToFileURL } = require("url");
const { chromium } = require(path.join("C:/big21/hw-repo/HWF(TeamMAKE)/huge/e2e/node_modules", "playwright"));

(async () => {
    const browser = await chromium.launch();
    const page = await browser.newPage();
    await page.goto(pathToFileURL(path.join(__dirname, "dark", "doc.html")).href);
    await page.pdf({ path: process.argv[2], printBackground: true, preferCSSPageSize: true });
    await page.setViewportSize({ width: 1400, height: 990 });
    await page.screenshot({ path: path.join(__dirname, "dark", "cover.png") });
    await page.locator("section").nth(4).screenshot({ path: path.join(__dirname, "dark", "p4.png") });
    await browser.close();
})();
