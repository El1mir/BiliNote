const { chromium } = require('playwright');
const EXE = 'C:/Users/Administrator/AppData/Local/ms-playwright/chromium-1248/chrome-win64/chrome.exe';
(async () => {
  const browser = await chromium.launch({ executablePath: EXE, args: ['--no-sandbox'] });
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  await ctx.addInitScript(() => { try { localStorage.setItem('bilinote-locale', 'zh-CN'); } catch (e) {} });
  const page = await ctx.newPage();
  await page.goto('http://127.0.0.1:3015/settings/transcriber', { waitUntil: 'domcontentloaded', timeout: 45000 });
  await page.waitForFunction(() => !document.querySelector('[data-boot-state]'), null, { timeout: 30000 });
  await page.waitForSelector('main', { timeout: 15000 });
  await page.waitForTimeout(1800);
  await page.evaluate(() => {
    const edit = Array.from(document.querySelectorAll('button')).find(b => (b.getAttribute('aria-label') || '').match(/编辑|Edit/i));
    if (edit) edit.click();
  });
  await page.waitForTimeout(800);
  const before = await page.evaluate(() => {
    const d = document.querySelector('[role=dialog]');
    const sw = Array.from(d.querySelectorAll('button[role=switch]'));
    const nums = Array.from(d.querySelectorAll('input[type=number]'));
    return { follow: sw[0] && sw[0].getAttribute('aria-checked'), splitDisabled: sw[1] && sw[1].disabled, disabledNums: nums.filter(n => n.disabled).length };
  });
  // 关掉跟随：应解除禁用
  await page.evaluate(() => {
    const d = document.querySelector('[role=dialog]');
    const sw = Array.from(d.querySelectorAll('button[role=switch]'));
    sw[0].click();
  });
  await page.waitForTimeout(500);
  const after = await page.evaluate(() => {
    const d = document.querySelector('[role=dialog]');
    const sw = Array.from(d.querySelectorAll('button[role=switch]'));
    const nums = Array.from(d.querySelectorAll('input[type=number]'));
    return {
      follow: sw[0] && sw[0].getAttribute('aria-checked'),
      splitDisabled: sw[1] && sw[1].disabled,
      disabledNums: nums.filter(n => n.disabled).length,
      globalLine: /当前全局/.test(d.innerText),
    };
  });
  console.log(JSON.stringify({ before, after }, null, 1));
  await browser.close();
})().catch(e => { console.error('FAILED', String(e).slice(0, 300)); process.exit(1); });
