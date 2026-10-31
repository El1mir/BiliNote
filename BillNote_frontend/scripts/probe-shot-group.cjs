const { chromium } = require('playwright');
const EXE = 'C:/Users/Administrator/AppData/Local/ms-playwright/chromium-1248/chrome-win64/chrome.exe';
(async () => {
  const browser = await chromium.launch({ executablePath: EXE, args: ['--no-sandbox'] });
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1 });
  await ctx.addInitScript(() => { try { localStorage.setItem('bilinote-locale', 'zh-CN'); } catch (e) {} });
  const page = await ctx.newPage();
  await page.goto('http://127.0.0.1:4174/settings/general', { waitUntil: 'domcontentloaded', timeout: 45000 });
  await page.waitForFunction(() => !document.querySelector('[data-boot-state]'), null, { timeout: 30000 });
  await page.waitForSelector('main', { timeout: 15000 });
  await page.waitForTimeout(1500);
  const report = await page.evaluate(() => {
    const heads = Array.from(document.querySelectorAll('main h3')).map(n => n.textContent);
    const rows = Array.from(document.querySelectorAll('main input[type=number]')).map(i => {
      const row = i.closest('div');
      const label = row && row.parentElement ? (row.parentElement.innerText || '').split('\n')[0] : '';
      return { label, value: i.value };
    });
    return { heads, rows };
  });
  console.log(JSON.stringify(report, null, 1));
  await browser.close();
})().catch(e => { console.error('FAILED', String(e).slice(0, 300)); process.exit(1); });
