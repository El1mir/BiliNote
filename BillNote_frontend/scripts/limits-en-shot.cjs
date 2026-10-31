const { chromium } = require('playwright');
const fs = require('fs');
const EXE = 'C:/Users/Administrator/AppData/Local/ms-playwright/chromium-1248/chrome-win64/chrome.exe';
const BASE = 'http://127.0.0.1:3015';
const OUT = 'C:/Users/Administrator/Downloads';

(async () => {
  const browser = await chromium.launch({ executablePath: EXE, args: ['--no-sandbox'] });
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1 });
  await ctx.addInitScript(() => { try { localStorage.setItem('bilinote-locale', 'en-US'); } catch (e) {} });
  const page = await ctx.newPage();
  const errors = [];
  page.on('pageerror', e => errors.push(String(e.message).slice(0, 160)));
  await page.goto(BASE + '/settings/general', { waitUntil: 'domcontentloaded', timeout: 45000 });
  await page.waitForFunction(() => !document.querySelector('[data-boot-state]'), null, { timeout: 30000 });
  await page.waitForSelector('main', { timeout: 15000 });
  await page.waitForTimeout(1200);
  await page.evaluate(() => {
    const nodes = Array.from(document.querySelectorAll('h3'));
    const t = nodes.find(n => (n.textContent || '').includes('Transcription input'));
    if (t) t.scrollIntoView({ block: 'start' });
  });
  await page.waitForTimeout(500);
  const file = OUT + '/limits-desktop-en-general.png';
  await page.screenshot({ path: file, fullPage: false });
  const text = await page.evaluate(() => (document.querySelector('main')?.innerText || '').replace(/\s+/g, ' ').slice(0, 400));
  console.log(JSON.stringify({ size: fs.statSync(file).size, text, errors }, null, 1));
  await browser.close();
})().catch(e => { console.error('FAILED', String(e).slice(0, 300)); process.exit(1); });
