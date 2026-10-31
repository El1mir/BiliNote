const { chromium } = require('playwright');
const fs = require('fs');
const EXE = 'C:/Users/Administrator/AppData/Local/ms-playwright/chromium-1248/chrome-win64/chrome.exe';
const OUT = 'C:/Users/Administrator/Downloads';
const VPS = [{n:'desktop',w:1440,h:900},{n:'tablet',w:834,h:1112},{n:'mobile',w:390,h:844}];
(async () => {
  const browser = await chromium.launch({ executablePath: EXE, args: ['--no-sandbox'] });
  const out = [];
  for (const vp of VPS) {
    const ctx = await browser.newContext({ viewport: { width: vp.w, height: vp.h }, deviceScaleFactor: 1 });
    await ctx.addInitScript(() => { try { localStorage.setItem('bilinote-locale', 'zh-CN'); } catch (e) {} });
    const page = await ctx.newPage();
    const errs = [];
    page.on('pageerror', e => errs.push(String(e.message).slice(0, 100)));
    await page.goto('http://127.0.0.1:3015/', { waitUntil: 'domcontentloaded' });
    await page.waitForFunction(() => !document.querySelector('[data-boot-state]'), null, { timeout: 30000 });
    await page.waitForTimeout(1200);
    // open the first history card
    const card = page.locator('button').filter({ hasText: 'Neo4j' }).first();
    await card.click();
    await page.waitForTimeout(2500);
    const file = OUT + '/ember3-' + vp.n + '-reader.png';
    await page.screenshot({ path: file });
    const info = await page.evaluate(() => ({
      tabs: Array.from(document.querySelectorAll('[role=tab], button')).map(b => (b.textContent || '').trim()).filter(t => t && t.length < 8).slice(0, 14),
      text: (document.body.innerText || '').replace(/\s+/g, ' ').trim().slice(0, 200),
      h2: Array.from(document.querySelectorAll('h2')).map(h => (h.textContent || '').trim()).slice(0, 6),
    }));
    out.push({ vp: vp.n, size: fs.statSync(file).size, ...info, errs: errs.slice(0, 3) });
    await ctx.close();
  }
  console.log(JSON.stringify(out, null, 1));
  await browser.close();
})().catch(e => { console.error('FAILED', String(e).slice(0, 300)); process.exit(1); });
