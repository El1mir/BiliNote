const { chromium } = require('playwright');
const fs = require('fs');
const EXE = 'C:/Users/Administrator/AppData/Local/ms-playwright/chromium-1248/chrome-win64/chrome.exe';
const BASE = 'http://127.0.0.1:3015';
const OUT = 'C:/Users/Administrator/Downloads';

const CASES = [
  { name: 'desktop', width: 1440, height: 900, locale: 'zh-CN', label: '失败与重试' },
  { name: 'mobile', width: 390, height: 844, locale: 'zh-CN', label: '失败与重试' },
  { name: 'en', width: 1440, height: 900, locale: 'en-US', label: 'Failures and retries' },
];

(async () => {
  const browser = await chromium.launch({ executablePath: EXE, args: ['--no-sandbox'] });
  const results = [];
  for (const c of CASES) {
    const ctx = await browser.newContext({ viewport: { width: c.width, height: c.height }, deviceScaleFactor: 1 });
    await ctx.addInitScript(loc => { try { localStorage.setItem('bilinote-locale', loc); } catch (e) {} }, c.locale);
    const page = await ctx.newPage();
    const errors = [];
    page.on('pageerror', e => errors.push(String(e.message).slice(0, 160)));

    await page.goto(BASE + '/settings/general', { waitUntil: 'domcontentloaded', timeout: 45000 });
    await page.waitForFunction(() => !document.querySelector('[data-boot-state]'), null, { timeout: 30000 });
    await page.waitForSelector('main', { timeout: 15000 });
    await page.waitForTimeout(1500);

    const found = await page.evaluate(label => {
      const nodes = Array.from(document.querySelectorAll('h3'));
      const target = nodes.find(n => (n.textContent || '').includes(label));
      if (!target) return false;
      target.scrollIntoView({ block: 'start' });
      return true;
    }, c.label);
    await page.waitForTimeout(600);

    const file = OUT + '/retry-budget-' + c.name + '.png';
    await page.screenshot({ path: file, fullPage: false });

    const values = await page.evaluate(() => {
      const rows = Array.from(document.querySelectorAll('main input'));
      return rows.map(i => i.value).join(',');
    });
    const headings = await page.evaluate(() =>
      Array.from(document.querySelectorAll('main h3')).map(h => (h.textContent || '').trim())
    );
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    const cjk = await page.evaluate(() => {
      const txt = (document.querySelector('main') || document.body).innerText || '';
      return (txt.match(/[\u4e00-\u9fff]/g) || []).length;
    });

    results.push({ case: c.name, found, size: fs.statSync(file).size, overflowX: overflow, cjkInMain: cjk, headings, inputs: values.slice(0, 220) });
    if (errors.length) results.push({ case: c.name, errors: errors.slice(0, 5) });
    await ctx.close();
  }
  await browser.close();
  console.log(JSON.stringify(results, null, 1));
})().catch(e => { console.error('FAILED', String(e).slice(0, 400)); process.exit(1); });
