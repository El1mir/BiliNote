const { chromium } = require('playwright');
const fs = require('fs');
const EXE = 'C:/Users/Administrator/AppData/Local/ms-playwright/chromium-1248/chrome-win64/chrome.exe';
const OUT = 'C:/Users/Administrator/Downloads';
const FILE = OUT + '/probe-group-actions.json';
const state = { steps: [] };
const save = () => fs.writeFileSync(FILE, JSON.stringify(state, null, 1));
const snap = async (page, label) => {
  state.steps.push({
    label,
    header: await page.evaluate(() => {
      const h = document.querySelectorAll('h2')[0];
      const bar = h && h.parentElement ? h.parentElement.innerText : '';
      return (bar || '').replace(/\s+/g, ' ').trim();
    }),
    body: await page.evaluate(() => (document.body.innerText || '').replace(/\s+/g, ' ').slice(0, 200)),
  });
  save();
};
(async () => {
  const browser = await chromium.launch({ executablePath: EXE, args: ['--no-sandbox'] });
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1 });
  await ctx.addInitScript(() => { try { localStorage.setItem('bilinote-locale', 'zh-CN'); } catch (e) {} });
  const page = await ctx.newPage();
  page.on('pageerror', e => state.steps.push({ pageerror: String(e.message).slice(0, 160) }));
  await page.goto('http://127.0.0.1:3015/', { waitUntil: 'domcontentloaded' });
  await page.waitForFunction(() => !document.querySelector('[data-boot-state]'), null, { timeout: 30000 });
  await page.waitForTimeout(1200);
  await snap(page, 'boot');

  await page.getByLabel('新建分组').fill('归档测试');
  await page.getByRole('button', { name: '新建', exact: true }).click();
  await page.waitForTimeout(900);
  await snap(page, 'group-created');

  await page.getByRole('button', { name: '更多' }).click();
  await page.waitForTimeout(500);
  await snap(page, 'select-mode');

  // In select mode the cards deliberately drop draggable (the move dialog is the
  // keyboard/touch path), so locate them by their title span instead.
  const cards = page.locator('button:has(span.line-clamp-2)');
  state.cardCount = await cards.count();
  save();
  await cards.first().click();
  await page.waitForTimeout(600);
  await snap(page, 'card-clicked');

  state.moveDisabled = await page.getByRole('button', { name: '移动到分组' }).isDisabled();
  save();
  await page.screenshot({ path: OUT + '/probe-select-mode.png' });
  await browser.close();
  console.log(JSON.stringify(state, null, 1).slice(0, 2500));
})().catch(e => { state.error = String(e).slice(0, 300); save(); console.error('FAILED', String(e).slice(0, 300)); process.exit(1); });