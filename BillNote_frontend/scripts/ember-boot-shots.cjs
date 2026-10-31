const { chromium } = require('playwright');
const fs = require('fs');
const EXE = 'C:/Users/Administrator/AppData/Local/ms-playwright/chromium-1248/chrome-win64/chrome.exe';
const BASE = 'http://127.0.0.1:3015';
const OUT = 'C:/Users/Administrator/Downloads';

const CASES = [
  { name: 'desktop-zh', width: 1440, height: 900, locale: 'zh-CN' },
  { name: 'desktop-en', width: 1440, height: 900, locale: 'en-US' },
  { name: 'mobile-zh', width: 390, height: 844, locale: 'zh-CN' },
];

(async () => {
  const browser = await chromium.launch({ executablePath: EXE, args: ['--no-sandbox'] });
  const results = [];
  for (const c of CASES) {
    const ctx = await browser.newContext({ viewport: { width: c.width, height: c.height }, deviceScaleFactor: 1 });
    await ctx.addInitScript(loc => { try { localStorage.setItem('bilinote-locale', loc); } catch (e) {} }, c.locale);
    const page = await ctx.newPage();
    await page.clock.install();
    await page.route('**/api/sys_check', r => r.abort());
    await page.goto(BASE + '/', { waitUntil: 'domcontentloaded', timeout: 45000 });
    await page.waitForSelector('#startup-loading-title', { timeout: 20000 });
    await page.clock.runFor(600);
    await page.waitForTimeout(400);

    const loadingFile = OUT + '/ember-boot-' + c.name + '-loading.png';
    await page.screenshot({ path: loadingFile });
    const loadingText = (await page.locator('body').innerText()).replace(/\s+/g, ' ').slice(0, 200);

    // Past the 60s readiness budget the hook flips to its failed state.
    await page.clock.runFor(66000);
    await page.waitForSelector('#startup-failed-title', { timeout: 15000 });
    await page.waitForTimeout(300);
    const failedFile = OUT + '/ember-boot-' + c.name + '-failed.png';
    await page.screenshot({ path: failedFile });
    const failedText = (await page.locator('body').innerText()).replace(/\s+/g, ' ').slice(0, 400);

    results.push({
      case: c.name,
      loading: { file: loadingFile, size: fs.statSync(loadingFile).size, text: loadingText },
      failed: { file: failedFile, size: fs.statSync(failedFile).size, text: failedText },
    });
    await ctx.close();
  }
  await browser.close();
  console.log(JSON.stringify(results, null, 1));
})().catch(e => { console.error('FAILED', String(e).slice(0, 400)); process.exit(1); });
