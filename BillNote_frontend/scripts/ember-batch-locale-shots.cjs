const { chromium } = require('playwright');
const fs = require('fs');
const EXE = 'C:/Users/Administrator/AppData/Local/ms-playwright/chromium-1248/chrome-win64/chrome.exe';
const CASES = [
  { name: 'en-desktop', w: 1440, h: 900, locale: 'en-US' },
  { name: 'zh-mobile', w: 390, h: 844, locale: 'zh-CN' },
];
(async () => {
  const browser = await chromium.launch({ executablePath: EXE, args: ['--no-sandbox'] });
  const out = [];
  for (const c of CASES) {
    const ctx = await browser.newContext({ viewport: { width: c.w, height: c.h }, deviceScaleFactor: 1 });
    await ctx.addInitScript(loc => { try { localStorage.setItem('bilinote-locale', loc); } catch (e) {} }, c.locale);
    const page = await ctx.newPage();
    const errs = [];
    page.on('pageerror', e => errs.push(String(e.message).slice(0, 120)));
    await page.goto('http://127.0.0.1:3015/', { waitUntil: 'domcontentloaded' });
    await page.waitForSelector('main', { timeout: 45000 });
    await page.waitForTimeout(900);
    const openName = c.locale === 'en-US' ? 'Batch import' : '批量导入';
    await page.getByRole('button', { name: openName }).first().click();
    await page.waitForTimeout(700);
    const f = 'C:/Users/Administrator/Downloads/ember3-batch-' + c.name + '.png';
    await page.screenshot({ path: f });
    const text = await page.evaluate(() => (document.body.innerText || '').replace(/\s+/g, ' ').trim());
    const cjk = c.locale === 'en-US' ? (text.match(/[\u4e00-\u9fff]+/g) || []).slice(0, 8) : [];
    out.push({ case: c.name, size: fs.statSync(f).size, cjk, text: text.slice(0, 190), errs: errs.slice(0, 3) });
    await ctx.close();
  }
  console.log(JSON.stringify(out, null, 1));
  await browser.close();
})().catch(e => { console.error('FAILED', String(e).slice(0, 300)); process.exit(1); });
