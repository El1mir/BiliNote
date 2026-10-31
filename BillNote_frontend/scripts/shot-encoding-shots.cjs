const { chromium } = require('playwright');
const fs = require('fs');
const EXE = 'C:/Users/Administrator/AppData/Local/ms-playwright/chromium-1248/chrome-win64/chrome.exe';
const OUT = 'C:/Users/Administrator/Downloads';

const CASES = [
  { name: 'shot-desktop', base: 'http://127.0.0.1:4174', width: 1440, height: 900, locale: 'zh-CN', label: '截图编码' },
  { name: 'shot-mobile', base: 'http://127.0.0.1:4174', width: 390, height: 844, locale: 'zh-CN', label: '截图编码' },
  { name: 'shot-en', base: 'http://127.0.0.1:3015', width: 1440, height: 900, locale: 'en-US', label: 'Screenshot encoding' },
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
    await page.goto(c.base + '/settings/general', { waitUntil: 'domcontentloaded', timeout: 45000 });
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
    await page.waitForTimeout(700);
    const file = OUT + '/' + c.name + '.png';
    await page.screenshot({ path: file, fullPage: false });
    const mainCount = await page.evaluate(() => document.querySelectorAll('main').length);
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    const cjk = await page.evaluate(() => {
      const main = document.querySelector('main');
      const text = main ? main.innerText : '';
      return (text.match(/[\u4e00-\u9fff]/g) || []).length;
    });
    const values = await page.evaluate(() => Array.from(document.querySelectorAll('main input[type=number]')).map(i => i.value).slice(-4));
    results.push({ case: c.name, found, mainCount, overflowX: overflow, cjk, lastFourInputs: values, size: fs.statSync(file).size });
    if (errors.length) results.push({ case: c.name, errors: errors.slice(0, 4) });
    await ctx.close();
  }
  await browser.close();
  console.log(JSON.stringify(results, null, 1));
})().catch(e => { console.error('FAILED', String(e).slice(0, 400)); process.exit(1); });
