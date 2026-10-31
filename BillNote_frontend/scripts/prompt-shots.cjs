const { chromium } = require('playwright');
const fs = require('fs');
const EXE = 'C:/Users/Administrator/AppData/Local/ms-playwright/chromium-1248/chrome-win64/chrome.exe';
const OUT = 'C:/Users/Administrator/Downloads';
const VPS = [{ n: 'desktop', w: 1440, h: 900 }, { n: 'tablet', w: 834, h: 1112 }, { n: 'mobile', w: 390, h: 844 }];
(async () => {
  const browser = await chromium.launch({ executablePath: EXE, args: ['--no-sandbox'] });
  const out = [];
  for (const vp of VPS) {
    const ctx = await browser.newContext({ viewport: { width: vp.w, height: vp.h }, deviceScaleFactor: 1 });
    await ctx.addInitScript(() => { try { localStorage.setItem('bilinote-locale', 'zh-CN'); } catch (e) {} });
    const page = await ctx.newPage();
    const errs = [];
    page.on('pageerror', e => errs.push(String(e.message).slice(0, 120)));
    await page.goto('http://127.0.0.1:3015/', { waitUntil: 'domcontentloaded' });
    await page.waitForFunction(() => !document.querySelector('[data-boot-state]'), null, { timeout: 30000 });
    await page.waitForTimeout(1500);
    // 最新任务在历史栏最上面：点它打开笔记
    const card = page.locator('button').filter({ hasText: '需求和架构' }).first();
    await card.click({ timeout: 15000 });
    await page.waitForFunction(() => (document.body.innerText || '').includes('补充：'), null, { timeout: 40000 });
    await page.waitForTimeout(800);
    // 滚到第一条补充段落，让 blockquote 的区分度出现在截图里
    const mark = page.locator('blockquote').filter({ hasText: '补充：' }).first();
    await mark.scrollIntoViewIfNeeded();
    await page.waitForTimeout(400);
    const file = OUT + '/prompt-' + vp.n + '.png';
    await page.screenshot({ path: file });
    const info = await page.evaluate(() => ({
      supplements: Array.from(document.querySelectorAll('blockquote')).filter(b => (b.textContent || '').trim().startsWith('补充')).length,
      rawTimeMarks: (document.body.innerText || '').includes('*Content-[') || (document.body.innerText || '').includes('*Screenshot-['),
      codeChips: Array.from(document.querySelectorAll('code')).map(c => (c.textContent || '').trim()).filter(t => /^\d{1,2}:\d{2}$/.test(t)).slice(0, 4),
      blockquotes: document.querySelectorAll('blockquote').length,
      h2: Array.from(document.querySelectorAll('h2')).map(h => (h.textContent || '').trim()).slice(0, 5),
      tocBullets: Array.from(document.querySelectorAll('ul li')).slice(0, 4).map(l => (l.textContent || '').trim().slice(0, 40)),
      overflowX: document.documentElement.scrollWidth > window.innerWidth + 2,
    }));
    out.push({ vp: vp.n, size: fs.statSync(file).size, ...info, errs: errs.slice(0, 3) });
    await ctx.close();
  }
  console.log(JSON.stringify(out, null, 1));
  await browser.close();
})().catch(e => { console.error('FAILED', String(e).slice(0, 400)); process.exit(1); });