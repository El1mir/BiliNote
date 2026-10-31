const { chromium } = require('playwright');
const fs = require('fs');
const EXE = 'C:/Users/Administrator/AppData/Local/ms-playwright/chromium-1248/chrome-win64/chrome.exe';
const OUT = 'C:/Users/Administrator/Downloads';

/** The app mounts behind a readiness gate; wait for real content, not for a timer. */
async function ready(page) {
  await page.waitForSelector('main', { timeout: 45000 });
  await page.waitForFunction(() => !document.querySelector('[data-boot-state]'), null, { timeout: 45000 });
  await page.waitForTimeout(600);
}

(async () => {
  const browser = await chromium.launch({ executablePath: EXE, args: ['--no-sandbox'] });
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1 });
  await ctx.addInitScript(() => { try { localStorage.setItem('bilinote-locale', 'zh-CN'); } catch (e) {} });
  const page = await ctx.newPage();
  const errs = [];
  page.on('pageerror', e => errs.push(String(e.message).slice(0, 160)));
  const out = [];
  const shot = async (name) => {
    const f = OUT + '/ember3-' + name + '.png';
    await page.screenshot({ path: f });
    const t = await page.evaluate(() => (document.body.innerText || '').replace(/\s+/g, ' ').trim());
    out.push({ name, size: fs.statSync(f).size, text: t.slice(0, 200) });
  };

  await page.goto('http://127.0.0.1:3015/', { waitUntil: 'domcontentloaded' });
  await ready(page);
  await shot('ui-workspace');

  await page.getByRole('button', { name: '批量导入' }).first().click();
  await page.waitForTimeout(600);
  await shot('ui-batch-open');

  await page.fill('#batch-urls', 'https://www.bilibili.com/video/BV1uY41167Ha');
  await page.getByRole('button', { name: '解析链接' }).click();
  await page.waitForTimeout(12000);
  await shot('ui-batch-resolved');

  console.log(JSON.stringify({ out, errs: errs.slice(0, 5) }, null, 1));
  await browser.close();
})().catch(e => { console.error('FAILED', String(e).slice(0, 400)); process.exit(1); });
