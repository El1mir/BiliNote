const { chromium } = require('playwright');
const EXE = 'C:/Users/Administrator/AppData/Local/ms-playwright/chromium-1248/chrome-win64/chrome.exe';
const OUT = 'C:/Users/Administrator/Downloads';
(async () => {
  const browser = await chromium.launch({ executablePath: EXE, args: ['--no-sandbox'] });
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1 });
  await ctx.addInitScript(() => { try { localStorage.setItem('bilinote-locale', 'zh-CN'); } catch (e) {} });
  const page = await ctx.newPage();
  const errs = [];
  const failed = [];
  page.on('pageerror', e => errs.push(String(e.message).slice(0, 200)));
  page.on('requestfailed', r => failed.push(r.url().slice(0, 160) + ' :: ' + (r.failure() || {}).errorText));
  page.on('response', r => { if (r.status() >= 400) failed.push(r.status() + ' ' + r.url().slice(0, 160)); });
  await page.goto('http://127.0.0.1:3015/', { waitUntil: 'domcontentloaded' });
  await page.waitForFunction(() => !document.querySelector('[data-boot-state]'), null, { timeout: 30000 });
  await page.waitForTimeout(1200);
  await page.locator('button:has(span.line-clamp-2)').first().click();
  await page.waitForTimeout(3000);
  const report = await page.evaluate(() => {
    const imgs = Array.from(document.querySelectorAll('img'));
    return {
      count: imgs.length,
      imgs: imgs.slice(0, 12).map(i => ({ src: i.getAttribute('src'), abs: i.currentSrc || i.src, nw: i.naturalWidth, complete: i.complete })),
      readerText: (document.querySelector('main') || document.body).innerText.slice(0, 400).replace(/\s+/g, ' '),
    };
  });
  report.errs = errs.slice(0, 6);
  report.failed = failed.slice(0, 12);
  await page.screenshot({ path: OUT + '/probe-images.png' });
  await browser.close();
  console.log(JSON.stringify(report, null, 1));
})().catch(e => { console.error('FAILED', String(e).slice(0, 300)); process.exit(1); });