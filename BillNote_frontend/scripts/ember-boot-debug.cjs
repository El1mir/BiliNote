const { chromium } = require('playwright');
const EXE = 'C:/Users/Administrator/AppData/Local/ms-playwright/chromium-1248/chrome-win64/chrome.exe';
(async () => {
  const browser = await chromium.launch({ executablePath: EXE, args: ['--no-sandbox'] });
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await ctx.newPage();
  await page.route('**/api/sys_check', r => r.abort());
  await page.goto('http://127.0.0.1:3015/', { waitUntil: 'domcontentloaded' });
  await page.waitForTimeout(66000);
  const info = await page.evaluate(() => {
    const el = document.querySelector('[data-boot-state]');
    const key = Object.keys(el).find(k => k.startsWith('__reactFiber$'));
    let fiber = el[key];
    while (fiber && !(typeof fiber.type === 'function' && fiber.type.name === 'EmberApp')) fiber = fiber.return;
    if (!fiber) return { error: 'no EmberApp fiber' };
    const hooks = [];
    let h = fiber.memoizedState;
    let i = 0;
    while (h && i < 20) {
      const ms = h.memoizedState;
      let desc;
      if (ms === null || ms === undefined) desc = String(ms);
      else if (typeof ms !== 'object') desc = typeof ms + ':' + String(ms);
      else if ('current' in ms && Object.keys(ms).length === 1) desc = 'ref{current:' + String(ms.current) + '}';
      else desc = 'obj{' + Object.keys(ms).slice(0, 6).join(',') + '} loading=' + String(ms.loading) + ' failed=' + String(ms.failed);
      hooks.push(i + ' ' + desc);
      h = h.next; i++;
    }
    return { attr: el.getAttribute('data-boot-state'), hooks };
  });
  console.log(JSON.stringify(info, null, 1).slice(0, 2500));
  await browser.close();
})().catch(e => { console.error('FAILED', String(e).slice(0, 300)); process.exit(1); });
