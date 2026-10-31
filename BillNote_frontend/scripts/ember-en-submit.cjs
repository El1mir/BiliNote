const { chromium } = require('playwright');
const fs = require('fs');
const EXE = 'C:/Users/Administrator/AppData/Local/ms-playwright/chromium-1248/chrome-win64/chrome.exe';
(async () => {
  const browser = await chromium.launch({ executablePath: EXE, args: ['--no-sandbox'] });
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  await ctx.addInitScript(() => { try { localStorage.setItem('bilinote-locale', 'en-US'); } catch (e) {} });
  const page = await ctx.newPage();
  await page.goto('http://127.0.0.1:3015/', { waitUntil: 'domcontentloaded' });
  await page.waitForSelector('main', { timeout: 45000 });
  await page.waitForTimeout(900);
  await page.fill('#video-url', 'https://www.bilibili.com/video/BV1uY41167Ha');
  await page.getByRole('button', { name: 'Generate notes' }).click();
  await page.waitForTimeout(4500);
  const toasts = await page.evaluate(() => {
    const rht = document.querySelector('[data-rht-toaster]');
    return rht ? Array.from(rht.children).map(k => (k.textContent || '').trim()).filter(Boolean) : [];
  });
  const file = 'C:/Users/Administrator/Downloads/ember3-en-submit-toast.png';
  await page.screenshot({ path: file });
  console.log(JSON.stringify({ toasts, size: fs.statSync(file).size }, null, 1));
  await browser.close();
})().catch(e => { console.error('FAILED', String(e).slice(0, 300)); process.exit(1); });
