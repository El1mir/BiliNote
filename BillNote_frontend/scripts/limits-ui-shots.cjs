const { chromium } = require('playwright');
const fs = require('fs');
const EXE = 'C:/Users/Administrator/AppData/Local/ms-playwright/chromium-1248/chrome-win64/chrome.exe';
const BASE = 'http://127.0.0.1:3015';
const OUT = 'C:/Users/Administrator/Downloads';

const VIEWPORTS = [
  { name: 'desktop', width: 1440, height: 900 },
  { name: 'mobile', width: 390, height: 844 },
];

(async () => {
  const browser = await chromium.launch({ executablePath: EXE, args: ['--no-sandbox'] });
  const results = [];
  for (const vp of VIEWPORTS) {
    const ctx = await browser.newContext({ viewport: { width: vp.width, height: vp.height }, deviceScaleFactor: 1 });
    await ctx.addInitScript(() => { try { localStorage.setItem('bilinote-locale', 'zh-CN'); } catch (e) {} });
    const page = await ctx.newPage();
    const errors = [];
    page.on('pageerror', e => errors.push(String(e.message).slice(0, 160)));

    await page.goto(BASE + '/settings/general', { waitUntil: 'domcontentloaded', timeout: 45000 });
    await page.waitForFunction(() => !document.querySelector('[data-boot-state]'), null, { timeout: 30000 });
    await page.waitForSelector('main', { timeout: 15000 });
    await page.waitForTimeout(1200);

    const shot = async (name) => {
      const file = OUT + '/limits-' + vp.name + '-' + name + '.png';
      await page.screenshot({ path: file, fullPage: false });
      return { name, size: fs.statSync(file).size };
    };
    results.push(await shot('general-top'));

    const scrollTo = async (text) => {
      const ok = await page.evaluate((label) => {
        const nodes = Array.from(document.querySelectorAll('h3'));
        const target = nodes.find(n => (n.textContent || '').includes(label));
        if (!target) return false;
        target.scrollIntoView({ block: 'start' });
        return true;
      }, text);
      await page.waitForTimeout(500);
      return ok;
    };

    results.push({ group_asr: await scrollTo('音频转写输入'), shot: await shot('general-asr') });
    results.push({ group_llm: await scrollTo('大模型请求'), shot: await shot('general-llm') });
    results.push({ group_ocr: await scrollTo('截图与 OCR'), shot: await shot('general-ocr') });

    const readback = await page.evaluate(() => {
      const rows = Array.from(document.querySelectorAll('main .flex.flex-col.gap-3.border-b, main div')).slice(0, 0);
      const inputs = Array.from(document.querySelectorAll('main input'));
      return inputs.map(i => i.value).join(',');
    });
    results.push({ inputs: readback.slice(0, 200) });

    await page.goto(BASE + '/settings/transcriber', { waitUntil: 'domcontentloaded', timeout: 45000 });
    await page.waitForFunction(() => !document.querySelector('[data-boot-state]'), null, { timeout: 30000 });
    await page.waitForSelector('main', { timeout: 15000 });
    await page.waitForTimeout(1500);

    let opened = 'none';
    const edit = page.locator('button[aria-label="编辑接口"]').first();
    if (await edit.count()) {
      await edit.click();
      opened = 'edit';
    } else {
      const add = page.locator('button', { hasText: '添加接口' }).first();
      if (await add.count()) { await add.click(); opened = 'add'; }
    }
    await page.waitForTimeout(700);
    const dialogCount = await page.locator('[role="dialog"]').count();
    results.push({ vp: vp.name, dialogOpened: opened, dialogCount });
    if (dialogCount) {
      results.push(await shot('transcriber-dialog-top'));
      const dialog = page.locator('[role="dialog"]').first();
      const scrollable = await dialog.evaluate(el => { const s = el.querySelector('.overflow-y-auto') || el; s.scrollTop = s.scrollHeight; return s.scrollTop; });
      await page.waitForTimeout(400);
      results.push({ dialogScroll: scrollable, shot: await shot('transcriber-dialog-bottom') });
    }

    if (errors.length) results.push({ vp: vp.name, errors: errors.slice(0, 5) });
    await ctx.close();
  }
  await browser.close();
  console.log(JSON.stringify(results, null, 1));
})().catch(e => { console.error('FAILED', String(e).slice(0, 400)); process.exit(1); });
