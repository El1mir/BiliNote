#!/usr/bin/env node
/** Verify the regenerated task now renders inline screenshots in the reader. */
const { chromium } = require('playwright');
const fs = require('node:fs');
const EXE = 'C:/Users/Administrator/AppData/Local/ms-playwright/chromium-1248/chrome-win64/chrome.exe';
const OUT = 'C:/Users/Administrator/Downloads';
(async () => {
  const browser = await chromium.launch({ executablePath: EXE, args: ['--no-sandbox'] })
  const page = await (await browser.newContext({ viewport: { width: 1440, height: 900 }, locale: 'zh-CN' })).newPage()
  const errors = []
  const imageResponses = []
  page.on('pageerror', e => errors.push(String(e)))
  page.on('response', r => { if (r.url().includes('/static/screenshots/')) imageResponses.push(r.status() + ' ' + r.url().split('/').pop()) })
  await page.goto('http://127.0.0.1:3015/', { waitUntil: 'domcontentloaded' })
  await page.waitForFunction(() => !document.querySelector('[data-boot-state]'), { timeout: 30000 })
  await page.waitForTimeout(2000)
  const cards = await page.locator('main button').allInnerTexts()
  const target = page.locator('main button', { hasText: '需求和架构' }).first()
  const found = await target.count()
  if (found) { await target.click() } else { await page.locator('main button').first().click() }
  await page.waitForTimeout(3000)
  // make sure the note tab is active
  const noteTab = page.locator('[role=tab]', { hasText: '笔记' }).first()
  if (await noteTab.count()) { await noteTab.click(); await page.waitForTimeout(1500) }
  const stats = await page.evaluate(() => {
    const imgs = [...document.querySelectorAll('main img')]
    return {
      total: imgs.length,
      loaded: imgs.filter(i => i.complete && i.naturalWidth > 0).length,
      first: imgs[0] ? { src: imgs[0].getAttribute('src'), w: imgs[0].naturalWidth, h: imgs[0].naturalHeight } : null,
      markers: (document.querySelector('main').innerText.match(/\[\[SHOT/g) || []).length,
      textLen: document.querySelector('main').innerText.length,
    }
  })
  const img = page.locator('main img').first()
  if (await img.count()) {
    await img.scrollIntoViewIfNeeded()
    await page.waitForTimeout(2000)
    await page.locator('main').screenshot({ path: OUT + '/reader-fixed-note.png' })
    await img.click()
    await page.waitForTimeout(1200)
    const zoomed = await page.evaluate(() => Boolean(document.querySelector('[data-rmiz-modal-overlay="visible"], [data-rmiz-modal]')))
    await page.screenshot({ path: OUT + '/reader-fixed-zoom.png' })
    const report = { cardsSample: cards.slice(0, 6), targetFound: found, stats, zoomed, imageResponses: imageResponses.slice(0, 6), errors }
    fs.writeFileSync(OUT + '/reader-fixed-probe.json', JSON.stringify(report, null, 2), 'utf8')
    console.log(JSON.stringify(report, null, 2))
  } else {
    console.log(JSON.stringify({ cardsSample: cards.slice(0, 6), targetFound: found, stats, errors }, null, 2))
  }
  await browser.close()
})().catch(e => { console.error('PROBE FAILED', e); process.exit(1) })
