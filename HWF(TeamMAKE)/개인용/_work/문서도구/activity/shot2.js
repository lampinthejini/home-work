// html/*.html 의 SVG → (인자로 받은 폴더)/*.png
const path = require("path");
const fs = require("fs");
const { pathToFileURL } = require("url");
const { chromium } = require(path.join("C:/big21/hw-repo/HWF(TeamMAKE)/huge/e2e/node_modules", "playwright"));

const src = path.join(__dirname, "html");
const outDir = process.argv[2];

(async () => {
    fs.mkdirSync(outDir, { recursive: true });
    const browser = await chromium.launch();
    const page = await browser.newPage({ deviceScaleFactor: 1.5 });
    for (const f of fs.readdirSync(src).filter((x) => x.endsWith(".html"))) {
        await page.goto(pathToFileURL(path.join(src, f)).href);
        await page.locator("svg").screenshot({ path: path.join(outDir, f.replace(".html", ".png")) });
        console.log(f);
    }
    await browser.close();
})();
