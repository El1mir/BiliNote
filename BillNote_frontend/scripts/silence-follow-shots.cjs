const { chromium } = require('playwright');
const fs = require('fs');
const EXE = 'C:/Users/Administrator/AppData/Local/ms-playwright/chromium-1248/chrome-win64/chrome.exe';
const OUT = 'C:/Users/Administrator/Downloads';

(async () => {
  const browser = await chromium.launch({ executablePath: EXE, args: ['--no-sandbox'] });
  const results = [];
  for (const c of [
    { name: 'silence-follow-zh', locale: 'zh-CN', width: 1440, height: 900, base: 'http://127.0.0.1:3015' },
    { name: 'silence-follow-en', locale: 'en-US', width: 1440, height: 900, base: 'http://127.0.0.1:3015' },
    { name: 'silence-follow-mobile', locale: 'zh-CN', width: 390, height: 844, base: 'http://127.0.0.1:3015' },
  ]) {
    const ctx = await browser.newContext({ viewport: { width: c.width, height: c.height }, deviceScaleFactor: 1 });
    await ctx.addInitScript(loc => { try { localStorage.setItem('bilinote-locale', loc); } catch (e) {} }, c.locale);
    const page = await ctx.newPage();
    const errors = [];
    page.on('pageerror', e => errors.push(String(e.message).slice(0, 160)));
    await page.goto(c.base + '/settings/transcriber', { waitUntil: 'domcontentloaded', timeout: 45000 });
    await page.waitForFunction(() => !document.querySelector('[data-boot-state]'), null, { timeout: 30000 });
    await page.waitForSelector('main', { timeout: 15000 });
    await page.waitForTimeout(1800);
    // 打开第一条端点的编辑对话框
    const opened = await page.evaluate(() => {
      const buttons = Array.from(document.querySelectorAll('button'));
      const edit = buttons.find(b => (b.getAttribute('aria-label') || '').match(/编辑|Edit/i));
      if (!edit) return false;
      edit.click();
      return true;
    });
    await page.waitForTimeout(900);
    const info = await page.evaluate(() => {
      const dialog = document.querySelector('[role=dialog]');
      const text = dialog ? dialog.innerText : '';
      const switches = Array.from(document.querySelectorAll('[role=dialog] [role=switch]'));
      const inputs = Array.from(document.querySelectorAll('[role=dialog] input[type=number]'));
      return {
        dialog: !!dialog,
        hasFollowRow: /跟随通用设置|Follow the general silence/i.test(text),
        globalLine: (text.match(/当前全局：[^\n]*|Current global:[^\n]*/) || [''])[0],
        switches: switches.map(s => ({ label: s.getAttribute('aria-label'), checked: s.getAttribute('aria-checked'), disabled: s.disabled })),
        disabledNumbers: inputs.filter(i => i.disabled).length,
        numberCount: inputs.length,
      };
    });
    if (info.dialog) {
      // 把「跟随通用设置」这一行滚进视野再拍，否则截图停在对话框顶部看不到它
      await page.evaluate(() => {
        const nodes = Array.from(document.querySelectorAll('[role=dialog] button[role=switch]'));
        const target = nodes[0];
        if (target) target.scrollIntoView({ block: 'center' });
      });
      await page.waitForTimeout(600);
      await page.screenshot({ path: OUT + '/' + c.name + '.png', fullPage: false });
    }
    results.push({ case: c.name, opened, ...info, errors: errors.slice(0, 3), size: info.dialog ? fs.statSync(OUT + '/' + c.name + '.png').size : 0 });
    await ctx.close();
  }
  await browser.close();
  console.log(JSON.stringify(results, null, 1));
})().catch(e => { console.error('FAILED', String(e).slice(0, 400)); process.exit(1); });
