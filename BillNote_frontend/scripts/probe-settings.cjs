#!/usr/bin/env node
/**
 * Settings probe: model provider editing + ASR endpoint editing.
 *
 * Everything is read-only on the server: the probe opens the edit dialogs, checks
 * that the fields arrive pre-filled, and closes without submitting. It only creates
 * something when explicitly asked, so running it never leaves rows behind.
 */
const { chromium } = require('playwright')
const fs = require('node:fs')

const EXE = 'C:/Users/Administrator/AppData/Local/ms-playwright/chromium-1248/chrome-win64/chrome.exe';
const OUT = 'C:/Users/Administrator/Downloads'
const BASE = 'http://127.0.0.1:3015'

async function settle(page) {
  await page.waitForFunction(() => !document.querySelector('[data-boot-state]'), { timeout: 30000 })
  await page.waitForTimeout(1200)
}

(async () => {
  const browser = await chromium.launch({ executablePath: EXE, args: ['--no-sandbox'] })
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 }, locale: 'zh-CN' })
  const page = await context.newPage()
  const errors = []
  page.on('pageerror', error => errors.push(String(error)))
  const report = {}

  await page.goto(BASE + '/settings/model', { waitUntil: 'domcontentloaded' })
  await settle(page)
  report.providers = await page.$$eval('main button[aria-expanded]', nodes =>
    nodes.map(node => node.textContent.replace(/\s+/g, ' ').trim()),
  )
  report.editButtons = await page.locator('button[aria-label="编辑服务商"]').count()
  await page.screenshot({ path: OUT + '/settings-model.png', fullPage: false })

  // Expand the first provider: models list + the on-demand provider fetch.
  await page.locator('main button[aria-expanded]').first().click()
  await page.waitForTimeout(900)
  report.expanded = await page.locator('main').innerText()
  await page.screenshot({ path: OUT + '/settings-model-expanded.png', fullPage: false })

  // Edit dialog must arrive pre-filled, with an empty api key.
  await page.locator('button[aria-label="编辑服务商"]').first().click()
  await page.waitForTimeout(700)
  report.editDialog = await page.evaluate(() => {
    const dialog = document.querySelector('[role="dialog"]')
    if (!dialog) return null
    const inputs = [...dialog.querySelectorAll('input')]
    return {
      title: dialog.textContent.slice(0, 60),
      values: inputs.map(input => ({ id: input.id, type: input.type, value: input.value, placeholder: input.placeholder })),
    }
  })
  await page.screenshot({ path: OUT + '/settings-model-edit.png', fullPage: false })
  await page.keyboard.press('Escape')
  await page.waitForTimeout(500)

  // Fetch the provider's real model list on demand.
  const fetchButton = page.getByRole('button', { name: /从服务商获取/ })
  if (await fetchButton.count()) {
    await fetchButton.first().click()
    await page.waitForTimeout(4000)
    report.remotePanel = await page.evaluate(() => {
      const text = document.querySelector('main').innerText
      const at = text.indexOf('服务商可选模型')
      return at >= 0 ? text.slice(at, at + 260) : null
    })
    await page.screenshot({ path: OUT + '/settings-model-remote.png', fullPage: false })
  }

  await page.goto(BASE + '/settings/transcriber', { waitUntil: 'domcontentloaded' })
  await settle(page)
  report.transcriberText = await page.locator('main').innerText()
  report.endpointRows = await page.locator('main button[aria-label="编辑接口"]').count()
  await page.screenshot({ path: OUT + '/settings-transcriber.png', fullPage: false })

  await page.locator('button[aria-label="编辑接口"]').first().click()
  await page.waitForTimeout(700)
  report.endpointDialog = await page.evaluate(() => {
    const dialog = document.querySelector('[role="dialog"]')
    if (!dialog) return null
    const inputs = [...dialog.querySelectorAll('input, select')]
    return {
      title: dialog.textContent.slice(0, 40),
      values: inputs.map(input => ({ id: input.id, type: input.type, value: input.value, placeholder: input.placeholder || '' })),
    }
  })
  await page.screenshot({ path: OUT + '/settings-transcriber-edit.png', fullPage: false })

  // English pass on the same two pages.
  await page.keyboard.press('Escape')
  await page.waitForTimeout(400)
  await page.goto(BASE + '/settings/transcriber', { waitUntil: 'domcontentloaded' })
  await settle(page)
  await page.evaluate(() => localStorage.setItem('bilinote-locale', 'en-US'))
  await page.reload({ waitUntil: 'domcontentloaded' })
  await settle(page)
  report.enTranscriber = await page.locator('main').innerText()
  await page.screenshot({ path: OUT + '/settings-transcriber-en.png', fullPage: false })
  await page.evaluate(() => localStorage.setItem('bilinote-locale', 'zh-CN'))

  report.errors = errors
  fs.writeFileSync(OUT + '/settings-probe.json', JSON.stringify(report, null, 2), 'utf8')
  console.log(JSON.stringify(report, null, 2))
  await browser.close()
})().catch(error => {
  console.error('PROBE FAILED', error)
  process.exit(1)
})