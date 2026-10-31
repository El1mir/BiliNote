#!/usr/bin/env node
/**
 * Image probe: scroll the note's inline screenshot into view, confirm it loads,
 * then click it to confirm the zoom overlay opens.
 */
const { chromium } = require('playwright');
const fs = require('node:fs');
const EXE = 'C:/Users/Administrator/AppData/Local/ms-playwright/chromium-1248/chrome-win64/chrome.exe';
const OUT = 'C:/Users/Administrator/Downloads';
(async () => {
  const browser = await chromium.launch({ executablePath: EXE, args: ['--no-sandbox'] })
  const page = await (await browser.newContext({ viewport: { width: 1440, height: 900 }, locale: 'zh-CN' })).newPage()
  const errors = []
  const imageResponses = []
  page.on('pageerror', error => errors.push(String(error)))
  page.on('response', response => {
    if (response.url().includes('/static/screenshots/')) imageResponses.push(response.status() + ' ' + response.url())
  })
  await page.goto('http://127.0.0.1:3015/', { waitUntil: 'domcontentloaded' })
  await page.waitForFunction(() => !document.querySelector('[data-boot-state]'), { timeout: 30000 })
  await page.waitForTimeout(1500)
  await page.locator('button:has(span.line-clamp-2)').first().click()
  await page.waitForTimeout(2500)
  const img = page.locator('main img').first()
  await img.scrollIntoViewIfNeeded()
  await page.waitForTimeout(2500)
  const before = await img.evaluate(node => ({ src: node.getAttribute('src'), complete: node.complete, w: node.naturalWidth, h: node.naturalHeight }))
  await page.locator('main').screenshot({ path: OUT + '/reader-image.png' })
  await img.click()
  await page.waitForTimeout(1200)
  const zoomed = await page.evaluate(() => Boolean(document.querySelector('[data-rmiz-modal-overlay="visible"], [data-rmiz-modal]')))
  await page.screenshot({ path: OUT + '/reader-image-zoom.png' })
  const report = { before, zoomed, imageResponses, errors }
  fs.writeFileSync(OUT + '/reader-image-probe.json', JSON.stringify(report, null, 2), 'utf8')
  console.log(JSON.stringify(report, null, 2))
  await browser.close()
})().catch(error => { console.error('PROBE FAILED', error); process.exit(1) })