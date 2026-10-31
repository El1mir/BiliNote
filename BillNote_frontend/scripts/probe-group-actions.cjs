const { chromium } = require('playwright');
const fs = require('fs');
const EXE = 'C:/Users/Administrator/AppData/Local/ms-playwright/chromium-1248/chrome-win64/chrome.exe';
const OUT = 'C:/Users/Administrator/Downloads';
const API = 'http://127.0.0.1:8483/api';
const NAME = 'E2E分组';
const RENAMED = 'E2E改名';
const report = {};
const panel = page =>
  page.evaluate(() => {
    const sec = document.querySelector('section[aria-label="分组"]');
    return sec ? (sec.innerText || '').replace(/\s+/g, ' ').trim() : 'NO PANEL';
  });
(async () => {
  const browser = await chromium.launch({ executablePath: EXE, args: ['--no-sandbox'] });
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1, acceptDownloads: true });
  await ctx.addInitScript(() => { try { localStorage.setItem('bilinote-locale', 'zh-CN'); } catch (e) {} });
  const page = await ctx.newPage();
  const errs = [];
  page.on('pageerror', e => errs.push(String(e.message).slice(0, 140)));
  await page.goto('http://127.0.0.1:3015/', { waitUntil: 'domcontentloaded' });
  await page.waitForFunction(() => !document.querySelector('[data-boot-state]'), null, { timeout: 30000 });
  await page.waitForTimeout(1200);

  await page.getByLabel('新建分组').fill(NAME);
  await page.getByRole('button', { name: '新建', exact: true }).click();
  await page.waitForTimeout(900);
  report.afterCreate = await panel(page);

  await page.getByRole('button', { name: '更多' }).click();
  await page.waitForTimeout(400);
  await page.locator('button:has(span.line-clamp-2)').first().click();
  await page.waitForTimeout(400);
  await page.getByRole('button', { name: '移动到分组' }).click();
  await page.waitForTimeout(500);
  report.moveDialog = await page.evaluate(() => {
    const d = document.querySelector('[role=dialog]');
    return d ? (d.textContent || '').replace(/\s+/g, ' ').trim().slice(0, 160) : 'NO DIALOG';
  });
  await page.screenshot({ path: OUT + '/ember-groups-move.png' });
  await page.getByRole('dialog').getByRole('button', { name: new RegExp(NAME) }).click();
  await page.waitForTimeout(1800);
  report.afterMove = await panel(page);

  const row = page.locator('section[aria-label="分组"] div[class*="group/row"]').filter({ hasText: NAME }).first();
  await row.hover();
  await row.getByRole('button', { name: '重命名' }).click();
  await page.waitForTimeout(400);
  // Once the row switches to its rename form the name text is gone, so the
  // filtered row locator no longer matches; the panel only ever has one rename
  // input at a time, so address it directly.
  const renameInput = page.locator('section[aria-label="分组"] div[class*="group/row"] input');
  await renameInput.fill(RENAMED);
  await renameInput.press('Enter');
  await page.waitForTimeout(1400);
  report.afterRename = await panel(page);

  const row2 = page.locator('section[aria-label="分组"] div[class*="group/row"]').filter({ hasText: RENAMED }).first();
  await row2.hover();
  await row2.getByRole('checkbox').click();
  await page.waitForTimeout(300);
  const downloadPromise = page.waitForEvent('download', { timeout: 20000 }).catch(() => null);
  await page.getByRole('button', { name: '下载所选分组' }).click();
  const download = await downloadPromise;
  report.download = download ? download.suggestedFilename() : 'none';
  if (download) await download.saveAs(OUT + '/e2e-group-archive.zip');

  await row2.hover();
  await row2.getByRole('button', { name: '删除分组' }).click();
  await page.waitForTimeout(500);
  report.deleteDialog = await page.evaluate(() => {
    const d = document.querySelector('[role=dialog]');
    return d ? (d.textContent || '').replace(/\s+/g, ' ').trim().slice(0, 200) : 'NO DIALOG';
  });
  await page.screenshot({ path: OUT + '/ember-groups-delete.png' });
  await page.getByRole('dialog').getByRole('button', { name: '删除' }).last().click();
  await page.waitForTimeout(1800);
  report.afterDelete = await panel(page);

  report.errs = errs;
  await browser.close();

  const cleanup = [];
  try {
    const list = await (await fetch(API + '/note_group')).json();
    for (const g of list.data.groups || []) {
      if (!g.name.startsWith('E2E') && !g.name.startsWith('归档测试')) continue;
      const res = await (await fetch(API + '/note_group/delete', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ group_id: g.id, delete_tasks: false }),
      })).json();
      cleanup.push({ name: g.name, code: res.code });
    }
  } catch (e) { cleanup.push({ error: String(e).slice(0, 100) }); }
  report.cleanup = cleanup;
  report.shots = {};
  for (const f of fs.readdirSync(OUT)) if (/^ember-groups-(move|delete)\.png$/.test(f)) report.shots[f] = fs.statSync(OUT + '/' + f).size;
  console.log(JSON.stringify(report, null, 1));
})().catch(e => { console.error('FAILED', String(e).slice(0, 400)); process.exit(1); });