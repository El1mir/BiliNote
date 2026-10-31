const { chromium } = require('playwright');
const fs = require('fs');
const EXE = 'C:/Users/Administrator/AppData/Local/ms-playwright/chromium-1248/chrome-win64/chrome.exe';
(async () => {
  const browser = await chromium.launch({ executablePath: EXE, args: ['--no-sandbox'] });
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  await ctx.addInitScript(() => { try { localStorage.setItem('bilinote-locale', 'zh-CN'); } catch (e) {} });
  const page = await ctx.newPage();
  const reqs = [];
  page.on('request', r => {
    const u = r.url();
    if (u.includes('/events')) return;
    if (!u.includes('/api/')) return;
    reqs.push({ phase: 'req', method: r.method(), url: u.replace('http://127.0.0.1:3015', '') });
  });
  page.on('response', async r => {
    const u = r.url();
    if (u.includes('/events')) return;
    if (!u.includes('/api/')) return;
    reqs.push({ phase: 'res', status: r.status(), url: u.replace('http://127.0.0.1:3015', '') });
  });
  page.on('requestfailed', r => {
    const u = r.url();
    if (u.includes('/events')) return;
    reqs.push({ phase: 'failed', url: u.replace('http://127.0.0.1:3015', ''), err: r.failure() && r.failure().errorText });
  });
  await page.goto('http://127.0.0.1:3015/', { waitUntil: 'domcontentloaded' });
  await page.waitForFunction(() => !document.querySelector('[data-boot-state]'), null, { timeout: 30000 });
  await page.waitForTimeout(1500);
  reqs.push({ phase: 'MARK', note: 'before create' });
  await page.getByLabel('新建分组').fill('probe-ui-2');
  await page.getByRole('button', { name: '新建', exact: true }).click();
  await page.waitForTimeout(3000);
  const toasts = await page.evaluate(() => Array.from(document.querySelectorAll('[data-rht-toaster] div')).map(d => (d.textContent || '').trim()).filter(Boolean).slice(0, 5));
  const panel = await page.evaluate(() => {
    const sec = document.querySelector('section[aria-label="分组"]');
    return sec ? (sec.innerText || '').replace(/\s+/g, ' ').slice(0, 300) : 'NO PANEL';
  });
  fs.writeFileSync('C:/Users/Administrator/Downloads/probe-group-create.json', JSON.stringify({ reqs, toasts, panel }, null, 1));
  console.log(JSON.stringify({ count: reqs.length, toasts, panel }));
  await browser.close();
})().catch(e => { console.error('FAILED', String(e).slice(0, 300)); process.exit(1); });