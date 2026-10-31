#!/usr/bin/env node
/**
 * Reader probe: the two reader tabs that remain (note, transcript) and inline images.
 *
 * Images matter because the markdown stores them as server-relative /static paths; on the
 * desktop build the page origin is not the backend, so the renderer has to absolutise them.
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
  const tabs = await page.evaluate(() => [...document.querySelectorAll('[role="tab"]')].map(n => n.textContent.trim()))
  const images = await page.evaluate(() => [...document.querySelectorAll('article img, main img')].map(img => ({
    src: img.getAttribute('src'),
    complete: img.complete,
    w: img.naturalWidth,
    h: img.naturalHeight,
  })))
  await page.locator('main').screenshot({ path: OUT + '/reader-note.png' })
  // transcript tab still present and switching
  const transcriptTab = page.getByRole('tab', { name: /转写/ })
  let transcript = null
  if (await transcriptTab.count()) {
    await transcriptTab.first().click()
    await page.waitForTimeout(1500)
    transcript = (await page.locator('main').innerText()).slice(0, 200)
    await page.locator('main').screenshot({ path: OUT + '/reader-transcript.png' })
  }
  const report = { tabs, images, imageResponses, transcript, errors }
  fs.writeFileSync(OUT + '/reader-probe.json', JSON.stringify(report, null, 2), 'utf8')
  console.log(JSON.stringify(report, null, 2).slice(0, 2500))
  await browser.close()
})().catch(error => { console.error('PROBE FAILED', error); process.exit(1) })