const { chromium } = require('playwright');
const fs = require('fs');
const EXE = 'C:/Users/Administrator/AppData/Local/ms-playwright/chromium-1248/chrome-win64/chrome.exe';
const OUT = 'C:/Users/Administrator/Downloads';
(async () => {
  const browser = await chromium.launch({ executablePath: EXE, args: ['--no-sandbox'] });
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1 });
  await ctx.addInitScript(() => { try { localStorage.setItem('bilinote-locale', 'zh-CN'); } catch (e) {} });
  const page = await ctx.newPage();
  const errs = [];
  page.on('pageerror', e => errs.push(String(e.message).slice(0, 140)));
  const out = [];
  const shot = async (name) => {
    const f = OUT + '/ember3-' + name + '.png';
    await page.screenshot({ path: f });
    const t = await page.evaluate(() => (document.body.innerText || '').replace(/\s+/g, ' ').trim());
    out.push({ name, size: fs.statSync(f).size, text: t.slice(0, 150) });
  };

  await page.goto('http://127.0.0.1:3015/', { waitUntil: 'domcontentloaded' });
  await page.waitForFunction(() => !document.querySelector('[data-boot-state]'), null, { timeout: 30000 });
  await page.waitForTimeout(1000);

  // 1. generation options expanded
  await page.getByRole('button', { name: '生成设置' }).click();
  await page.waitForTimeout(500);
  await shot('ui-options-open');

  // 2. batch import dialog
  await page.getByRole('button', { name: /批量/ }).first().click().catch(() => {});
  await page.waitForTimeout(700);
  await shot('ui-batch-dialog');
  await page.keyboard.press('Escape');
  await page.waitForTimeout(500);

  // 3. open a task, walk the reader tabs
  await page.locator('button').filter({ hasText: 'Neo4j' }).first().click();
  await page.waitForTimeout(2500);
  for (const tab of ['脑图', '转写', 'AI 问答']) {
    await page.getByRole('button', { name: tab, exact: true }).first().click().catch(() => {});
    await page.waitForTimeout(tab === '脑图' ? 3000 : 1500);
    await shot('ui-tab-' + tab);
  }
  console.log(JSON.stringify({ out, errs: errs.slice(0, 5) }, null, 1));
  await browser.close();
})().catch(e => { console.error('FAILED', String(e).slice(0, 400)); process.exit(1); });
