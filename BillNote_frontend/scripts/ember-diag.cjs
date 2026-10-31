const { chromium } = require('playwright');
const EXE = 'C:/Users/Administrator/AppData/Local/ms-playwright/chromium-1248/chrome-win64/chrome.exe';
(async () => {
  const browser = await chromium.launch({ executablePath: EXE, args: ['--no-sandbox'] });
  const page = await (await browser.newContext()).newPage();
  const logs = [];
  page.on('console', m => logs.push(m.type() + ': ' + m.text().slice(0, 300)));
  page.on('pageerror', e => logs.push('PAGEERROR: ' + String(e.message).slice(0, 300)));
  page.on('requestfailed', r => logs.push('REQFAIL: ' + r.url().slice(0, 120) + ' ' + (r.failure()?.errorText || '')));
  page.on('response', r => { if (r.status() >= 400) logs.push('HTTP ' + r.status() + ' ' + r.url().slice(0, 140)); });
  await page.goto('http://127.0.0.1:3015/', { waitUntil: 'load' });
  await page.waitForTimeout(6000);
  const html = await page.evaluate(() => ({ root: (document.getElementById('root')?.innerHTML || '').slice(0, 200), bodyLen: document.body.innerHTML.length }));
  console.log(JSON.stringify({ logs: logs.slice(0, 25), html }, null, 1));
  await browser.close();
})().catch(e => { console.error('FAILED', String(e).slice(0, 300)); process.exit(1); });
