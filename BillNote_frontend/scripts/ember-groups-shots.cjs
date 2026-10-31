const { chromium } = require('playwright');
const fs = require('fs');
const EXE = 'C:/Users/Administrator/AppData/Local/ms-playwright/chromium-1248/chrome-win64/chrome.exe';
const OUT = 'C:/Users/Administrator/Downloads';
const BASE = 'http://127.0.0.1:3015';
const API = 'http://127.0.0.1:8483/api';
const CREATED = ['论文速读', '技术访谈'];

const boot = async page => {
  await page.goto(BASE + '/', { waitUntil: 'domcontentloaded' });
  await page.waitForFunction(() => !document.querySelector('[data-boot-state]'), null, { timeout: 30000 });
  await page.waitForTimeout(1200);
};

const panelText = page =>
  page.evaluate(() => {
    const sec = document.querySelector('section[aria-label="分组"], section[aria-label="Groups"]');
    return sec ? (sec.innerText || '').replace(/\s+/g, ' ').trim() : 'NO PANEL';
  });

const sampleState = (page, labels) =>
  page.evaluate(keys => {
    const body = document.body.innerText || '';
    const out = {};
    for (const [name, text] of Object.entries(keys)) out[name] = body.includes(text);
    return out;
  }, labels);

const ZH_LABELS = {
  interval: '抽帧间隔（秒）',
  fps: '每秒帧数',
  maxFrames: '最大抽帧数',
  limitMode: '帧数上限方式',
  grid: '宫格尺寸',
  ocr: 'OCR 辅助',
  multimodal: '画面理解必须使用多模态模型',
};

const EN_LABELS = {
  interval: 'Interval (seconds)',
  fps: 'Frames per second',
  maxFrames: 'Max frames',
  limitMode: 'Frame budget',
  grid: 'Grid size',
  ocr: 'OCR assist',
  multimodal: 'visual understanding requires a multimodal model',
};

(async () => {
  const browser = await chromium.launch({ executablePath: EXE, args: ['--no-sandbox'] });
  const report = { shots: {}, steps: [] };

  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1 });
  await ctx.addInitScript(() => { try { localStorage.setItem('bilinote-locale', 'zh-CN'); } catch (e) {} });
  const page = await ctx.newPage();
  const errs = [];
  page.on('pageerror', e => errs.push(String(e.message).slice(0, 140)));
  await boot(page);

  // 1. create two real groups through the panel
  for (const name of CREATED) {
    await page.getByLabel('新建分组').fill(name);
    await page.getByRole('button', { name: '新建', exact: true }).click();
    await page.waitForTimeout(700);
  }
  report.steps.push({ afterCreate: await panelText(page) });

  // 2. click a group row to filter, then back to all
  await page.getByRole('button', { name: /论文速读/ }).first().click();
  await page.waitForTimeout(600);
  report.steps.push({ afterFilter: await page.evaluate(() => (document.body.innerText || '').includes('还没有笔记')) });
  await page.getByRole('button', { name: /全部笔记/ }).first().click();
  await page.waitForTimeout(600);

  // 3. drag the first history card onto the second group
  // HTML5 drag: dispatch the real event sequence with a shared DataTransfer, which is
  // what the panel handlers listen for. Playwright's dragTo drives mouse events and
  // does not always produce a native drag payload for a non-native draggable source.
  const cardCount = await page.locator('button[draggable="true"]').count();
  let dragResult = 'skipped';
  if (cardCount > 0) {
    dragResult = await page.evaluate(() => {
      const card = document.querySelector('button[draggable="true"]');
      const rows = document.querySelectorAll('section[aria-label="分组"] div[class*="group/row"], section[aria-label="Groups"] div[class*="group/row"]');
      const row = rows[1];
      if (!card || !row) return 'no nodes';
      const dt = new DataTransfer();
      const fire = (node, type) =>
        node.dispatchEvent(new DragEvent(type, { bubbles: true, cancelable: true, dataTransfer: dt }));
      fire(card, 'dragstart');
      fire(row, 'dragover');
      fire(row, 'drop');
      fire(card, 'dragend');
      return 'dispatched';
    });
    await page.waitForTimeout(1800);
  }
  report.steps.push({ cardCount, dragResult, afterDrag: await panelText(page) });

  await page.screenshot({ path: OUT + '/ember-groups-desktop.png' });
  await page.locator('section[aria-label="分组"]').screenshot({ path: OUT + '/ember-groups-rail.png' });

  // 4. sampling modes
  await page.getByRole('button', { name: '生成设置' }).click();
  await page.waitForTimeout(500);
  await page.locator('[role=switch]').first().click();
  await page.waitForTimeout(600);
  const focusSampling = async (target, wait) => {
    await target.evaluate(node => node.scrollIntoView({ block: 'center' }));
    await wait.waitForTimeout(400);
  };
  const samplingBlock = () => page.locator('text=抽帧方式').first();
  await focusSampling(await samplingBlock(), page);
  report.steps.push({ intervalMode: await sampleState(page, ZH_LABELS) });
  await page.screenshot({ path: OUT + '/ember-sampling-interval.png' });

  await page.getByRole('tab', { name: '智能' }).click();
  await page.waitForTimeout(500);
  await focusSampling(await samplingBlock(), page);
  report.steps.push({ smartMode: await sampleState(page, ZH_LABELS) });
  await page.screenshot({ path: OUT + '/ember-sampling-smart.png' });

  await page.getByRole('tab', { name: '混合' }).click();
  await page.waitForTimeout(500);
  await focusSampling(await samplingBlock(), page);
  report.steps.push({ hybridMode: await sampleState(page, ZH_LABELS) });
  await page.screenshot({ path: OUT + '/ember-sampling-hybrid.png' });
  await ctx.close();

  // 5. mobile
  const mctx = await browser.newContext({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 1 });
  await mctx.addInitScript(() => { try { localStorage.setItem('bilinote-locale', 'zh-CN'); } catch (e) {} });
  const mpage = await mctx.newPage();
  const merrs = [];
  mpage.on('pageerror', e => merrs.push(String(e.message).slice(0, 140)));
  await boot(mpage);
  report.mobileOverflow = await mpage.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  await mpage.screenshot({ path: OUT + '/ember-groups-mobile.png', fullPage: true });
  await mctx.close();

  // 6. english
  const ectx = await browser.newContext({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1 });
  await ectx.addInitScript(() => { try { localStorage.setItem('bilinote-locale', 'en-US'); } catch (e) {} });
  const epage = await ectx.newPage();
  await boot(epage);
  await epage.getByRole('button', { name: 'Generation options' }).click();
  await epage.waitForTimeout(400);
  await epage.locator('[role=switch]').first().click();
  await epage.waitForTimeout(600);
  await epage.locator('text=Sampling').first().evaluate(node => node.scrollIntoView({ block: 'center' }));
  await epage.waitForTimeout(400);
  report.steps.push({ enSampling: await sampleState(epage, EN_LABELS), enPanel: await panelText(epage) });
  await epage.screenshot({ path: OUT + '/ember-groups-desktop-en.png' });
  await ectx.close();
  await browser.close();

  // 7. clean up the demo groups
  const cleanup = [];
  try {
    const list = await (await fetch(API + '/note_group')).json();
    for (const g of list.data.groups || []) {
      if (!CREATED.includes(g.name)) continue;
      const res = await (await fetch(API + '/note_group/delete', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ group_id: g.id, delete_tasks: false }),
      })).json();
      cleanup.push({ name: g.name, code: res.code });
    }
  } catch (e) {
    cleanup.push({ error: String(e).slice(0, 120) });
  }
  report.cleanup = cleanup;
  report.errs = errs;
  report.merrs = merrs;
  for (const f of fs.readdirSync(OUT)) {
    if (/^ember-(groups|sampling)-.*\.png$/.test(f)) report.shots[f] = fs.statSync(OUT + '/' + f).size;
  }
  fs.writeFileSync(OUT + '/ember-groups-report.json', JSON.stringify(report, null, 1));
  console.log(JSON.stringify(report));
})().catch(e => { console.error('FAILED', String(e).slice(0, 400)); process.exit(1); });