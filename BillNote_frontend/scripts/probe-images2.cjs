const { chromium } = require('playwright');
const EXE = 'C:/Users/Administrator/AppData/Local/ms-playwright/chromium-1248/chrome-win64/chrome.exe';
(async () => {
  const browser = await chromium.launch({ executablePath: EXE, args: ['--no-sandbox'] });
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  await ctx.addInitScript(() => { try { localStorage.setItem('bilinote-locale', 'zh-CN'); } catch (e) {} });
  const page = await ctx.newPage();
  const net = [];
  page.on('response', r => { if (r.url().includes('/static/')) net.push(r.status() + ' ' + r.url().slice(-50)); });
  page.on('requestfailed', r => { if (r.url().includes('/static/')) net.push('FAILED ' + r.url().slice(-50) + ' ' + (r.failure() || {}).errorText); });
  await page.goto('http://127.0.0.1:3015/', { waitUntil: 'domcontentloaded' });
  await page.waitForFunction(() => !document.querySelector('[data-boot-state]'), null, { timeout: 30000 });
  await page.waitForTimeout(1000);
  await page.locator('button:has(span.line-clamp-2)').first().click();
  await page.waitForTimeout(2500);
  const img = page.locator('.ember-markdown img').first();
  await img.scrollIntoViewIfNeeded();
  await page.waitForTimeout(2500);
  const st = await page.evaluate(() => {
    const i = document.querySelector('.ember-markdown img');
    return i ? { src: i.getAttribute('src'), nw: i.naturalWidth, nh: i.naturalHeight, complete: i.complete, rect: i.getBoundingClientRect().toJSON(), lazy: i.getAttribute('loading') } : null;
  });
  await page.screenshot({ path: 'C:/Users/Administrator/Downloads/probe-images-scrolled.png' });
  await browser.close();
  console.log(JSON.stringify({ st, net }, null, 1));
})().catch(e => { console.error('FAILED', String(e).slice(0, 300)); process.exit(1); });