const { chromium } = require('playwright');
const fs = require('fs');
const EXE = 'C:/Users/Administrator/AppData/Local/ms-playwright/chromium-1248/chrome-win64/chrome.exe';
(async () => {
  const browser = await chromium.launch({ executablePath: EXE, args: ['--no-sandbox'] });
  const page = await (await browser.newContext({ viewport: { width: 1440, height: 900 } })).newPage();
  await page.addInitScript(() => { try { localStorage.setItem('bilinote-locale', 'zh-CN'); } catch (e) {} });
  await page.goto('http://127.0.0.1:3015/', { waitUntil: 'domcontentloaded' });
  await page.waitForSelector('main', { timeout: 45000 });
  await page.waitForTimeout(800);
  await page.getByRole('button', { name: '批量导入' }).first().click();
  await page.waitForTimeout(400);
  await page.getByRole('button', { name: '解析链接' }).click();
  await page.waitForTimeout(1200);
  const file = 'C:/Users/Administrator/Downloads/ember3-ui-toast.png';
  await page.screenshot({ path: file });
  const state = await page.evaluate(() => {
    const rht = document.querySelector('[data-rht-toaster]');
    const kids = rht ? Array.from(rht.children) : [];
    return {
      sonner: document.querySelectorAll('[data-sonner-toaster]').length,
      rhtChildren: kids.map(k => {
        const cs = getComputedStyle(k);
        const r = k.getBoundingClientRect();
        return { text: (k.textContent || '').slice(0, 30), display: cs.display, opacity: cs.opacity, size: Math.round(r.width) + 'x' + Math.round(r.height) };
      }),
    };
  });
  console.log(JSON.stringify({ state, size: fs.statSync(file).size }, null, 1));
  await browser.close();
})().catch(e => { console.error('FAILED', String(e).slice(0, 300)); process.exit(1); });
