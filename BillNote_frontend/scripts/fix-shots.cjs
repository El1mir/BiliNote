const { chromium } = require('playwright');
const fs = require('fs');
const EXE = 'C:/Users/Administrator/AppData/Local/ms-playwright/chromium-1248/chrome-win64/chrome.exe';
const OUT = 'C:/Users/Administrator/Downloads';
(async () => {
  const browser = await chromium.launch({ executablePath: EXE, args: ['--no-sandbox'] });
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  await ctx.addInitScript(() => { try { localStorage.setItem('bilinote-locale', 'zh-CN'); } catch (e) {} });
  const page = await ctx.newPage();
  const errs = [];
  page.on('pageerror', e => errs.push(String(e.message).slice(0, 120)));
  await page.goto('http://127.0.0.1:3015/', { waitUntil: 'domcontentloaded' });
  await page.waitForFunction(() => !document.querySelector('[data-boot-state]'), null, { timeout: 30000 });
  await page.waitForTimeout(1500);
  await page.locator('button').filter({ hasText: '需求和架构' }).first().click({ timeout: 15000 });
  await page.waitForSelector('main h2', { timeout: 40000 });
  await page.waitForTimeout(2500);
  const imgs = await page.evaluate(() => {
    const list = Array.from(document.querySelectorAll('main img'));
    return { count: list.length, loaded: list.filter(i => i.complete && i.naturalWidth > 0).length, first: list[0] ? list[0].getAttribute('src') : null };
  });
  const shot1 = OUT + '/fix-shots-note.png';
  await page.screenshot({ path: shot1 });
  const outlineBtns = page.locator('aside nav button');
  const outlineCount = await outlineBtns.count();
  let scrolled = null;
  if (outlineCount > 5) {
    const y0 = await page.evaluate(() => window.scrollY);
    await outlineBtns.nth(5).click();
    await page.waitForTimeout(1400);
    scrolled = { y0, y1: await page.evaluate(() => window.scrollY), url: page.url() };
  }
  const shot2 = OUT + '/fix-shots-outline-jump.png';
  await page.screenshot({ path: shot2 });
  console.log(JSON.stringify({ imgs, outlineCount, scrolled, errs, sizes: [fs.statSync(shot1).size, fs.statSync(shot2).size] }, null, 1));
  await browser.close();
})().catch(e => { console.error('FAILED', String(e).slice(0, 400)); process.exit(1); });