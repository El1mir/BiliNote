const { chromium } = require('playwright');
const EXE = 'C:/Users/Administrator/AppData/Local/ms-playwright/chromium-1248/chrome-win64/chrome.exe';
(async () => {
  const browser = await chromium.launch({ executablePath: EXE, args: ['--no-sandbox'] });
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  await ctx.addInitScript(() => { try { localStorage.setItem('bilinote-locale', 'zh-CN'); } catch (e) {} });
  const page = await ctx.newPage();
  let popups = 0;
  ctx.on('page', () => { popups += 1; });
  const errs = [];
  page.on('pageerror', e => errs.push(String(e.message).slice(0, 120)));
  await page.goto('http://127.0.0.1:3015/', { waitUntil: 'domcontentloaded' });
  await page.waitForFunction(() => !document.querySelector('[data-boot-state]'), null, { timeout: 30000 });
  await page.waitForTimeout(1500);
  await page.locator('button').filter({ hasText: '需求和架构' }).first().click({ timeout: 15000 });
  await page.waitForSelector('main h2', { timeout: 40000 });
  await page.waitForTimeout(800);
  const before = { url: page.url(), y: await page.evaluate(() => window.scrollY) };
  const outlineBtns = page.locator('aside nav button');
  await page.waitForTimeout(500);
  const outlineCount = await outlineBtns.count();
  if (await outlineBtns.count() > 3) { await outlineBtns.nth(3).click(); }
  await page.waitForTimeout(1200);
  const afterOutline = { url: page.url(), y: await page.evaluate(() => window.scrollY) };
  const headingIds = await page.evaluate(() => Array.from(document.querySelectorAll('h2')).slice(0, 4).map(h => h.id));
  // 目录里的站内锚点
  const tocLink = page.locator('a[href^="#"]').first();
  const tocCount = await page.locator('a[href^="#"]').count();
  let tocOk = null;
  if (tocCount > 0) {
    await page.evaluate(() => window.scrollTo(0, 0));
    await page.waitForTimeout(300);
    await tocLink.click();
    await page.waitForTimeout(1200);
    tocOk = { url: page.url(), y: await page.evaluate(() => window.scrollY) };
  }
  console.log(JSON.stringify({ outlineCount, before, afterOutline, headingIds, tocCount, tocOk, popups, errs }, null, 1));
  await browser.close();
})().catch(e => { console.error('FAILED', String(e).slice(0, 400)); process.exit(1); });