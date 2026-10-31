#!/usr/bin/env node
/**
 * Production-build check for the two settings pages this round touched:
 * AI models (provider editing + model fetch) and Transcription (endpoint editing).
 */
const { chromium } = require('playwright');
const fs = require('node:fs');
const EXE = 'C:/Users/Administrator/AppData/Local/ms-playwright/chromium-1248/chrome-win64/chrome.exe';
const OUT = 'C:/Users/Administrator/Downloads';
(async () => {
  const browser = await chromium.launch({ executablePath: EXE, args: ['--no-sandbox'] })
  const page = await (await browser.newContext({ viewport: { width: 1440, height: 900 }, locale: 'zh-CN' })).newPage()
  const errors = []
  page.on('pageerror', error => errors.push(String(error)))
  const shots = []
  for (const [route, name] of [['/settings/model', 'dist-model'], ['/settings/transcriber', 'dist-transcriber']]) {
    await page.goto('http://127.0.0.1:4174' + route, { waitUntil: 'domcontentloaded' })
    await page.waitForFunction(() => !document.querySelector('[data-boot-state]'), { timeout: 30000 })
    await page.waitForTimeout(1500)
    await page.screenshot({ path: OUT + '/' + name + '.png' })
    shots.push({ name, text: (await page.locator('main').innerText()).slice(0, 260) })
  }
  const report = { shots, errors }
  fs.writeFileSync(OUT + '/dist-settings-probe.json', JSON.stringify(report, null, 2), 'utf8')
  console.log(JSON.stringify(report, null, 2))
  await browser.close()
})().catch(error => { console.error('PROBE FAILED', error); process.exit(1) })