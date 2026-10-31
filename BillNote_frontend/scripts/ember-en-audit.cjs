const { chromium } = require('playwright');
const fs = require('fs');
const EXE = 'C:/Users/Administrator/AppData/Local/ms-playwright/chromium-1248/chrome-win64/chrome.exe';
const OUT = 'C:/Users/Administrator/Downloads';
const ROUTES = [['workspace','/'],['general','/settings/general'],['model','/settings/model'],['monitor','/settings/monitor'],['transcriber','/settings/transcriber']];
(async () => {
  const browser = await chromium.launch({ executablePath: EXE, args: ['--no-sandbox'] });
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1 });
  await ctx.addInitScript(() => { try { localStorage.setItem('bilinote-locale', 'en-US'); } catch (e) {} });
  const page = await ctx.newPage();
  const out = [];
  for (const [name, route] of ROUTES) {
    await page.goto('http://127.0.0.1:3015' + route, { waitUntil: 'domcontentloaded' });
    await page.waitForFunction(() => !document.querySelector('[data-boot-state]'), null, { timeout: 30000 });
    await page.waitForTimeout(900);
    const file = OUT + '/ember3-en-' + name + '.png';
    await page.screenshot({ path: file });
    const text = await page.evaluate(() => (document.body.innerText || '').replace(/\s+/g, ' ').trim());
    // any CJK still left in an English build is a missed translation
    const cjk = (text.match(/[\u4e00-\u9fff]+/g) || []).slice(0, 12);
    out.push({ route: name, size: fs.statSync(file).size, cjk });
  }
  console.log(JSON.stringify(out, null, 1));
  await browser.close();
})().catch(e => { console.error('FAILED', String(e).slice(0, 300)); process.exit(1); });
