#!/usr/bin/env node
const { chromium } = require('playwright');
const fs = require('node:fs');
const EXE = 'C:/Users/Administrator/AppData/Local/ms-playwright/chromium-1248/chrome-win64/chrome.exe';
const OUT = 'C:/Users/Administrator/Downloads';
(async () => {
  const browser = await chromium.launch({ executablePath: EXE, args: ['--no-sandbox'] })
  const page = await (await browser.newContext({ viewport: { width: 1440, height: 900 }, locale: 'zh-CN' })).newPage()
  const errors = []
  page.on('pageerror', error => errors.push(String(error)))
  await page.goto('http://127.0.0.1:3015/settings/model', { waitUntil: 'domcontentloaded' })
  await page.waitForFunction(() => !document.querySelector('[data-boot-state]'), { timeout: 30000 })
  await page.waitForTimeout(1200)
  await page.locator('main button[aria-expanded]').first().click()
  await page.waitForTimeout(700)
  await page.getByRole('button', { name: /从服务商获取/ }).first().click()
  await page.waitForTimeout(9000)
  const rows = await page.evaluate(() => {
    const panel = [...document.querySelectorAll('main div')].find(node => node.textContent.startsWith('服务商可选模型'))
    if (!panel) return null
    return [...panel.querySelectorAll('.max-h-64 > div')].map(row => ({
      id: row.querySelector('span')?.textContent ?? '',
      box: row.getBoundingClientRect().height,
    }))
  })
  const empty = (rows || []).filter(row => !row.id.trim())
  await page.locator('main').screenshot({ path: OUT + '/settings-model-remote.png' })
  fs.writeFileSync(OUT + '/settings-remote-rows.json', JSON.stringify({ count: rows && rows.length, empty: empty.length, sample: (rows || []).slice(0, 3), errors }, null, 2), 'utf8')
  console.log(JSON.stringify({ count: rows && rows.length, empty: empty.length, emptyRows: empty.slice(0, 5), errors }, null, 2))
  await browser.close()
})().catch(error => { console.error('PROBE FAILED', error); process.exit(1) })