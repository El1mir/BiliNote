#!/usr/bin/env node
/**
 * Focused probe: does the on-demand provider model fetch actually work end to end?
 * Opens the first provider, clicks 从服务商获取, and records the resulting panel.
 * Read-only: it never adds or removes a model.
 */
const { chromium } = require('playwright')
const fs = require('node:fs')

const EXE = 'C:/Users/Administrator/AppData/Local/ms-playwright/chromium-1248/chrome-win64/chrome.exe';
const OUT = 'C:/Users/Administrator/Downloads';

(async () => {
  const browser = await chromium.launch({ executablePath: EXE, args: ['--no-sandbox'] })
  const page = await (await browser.newContext({ viewport: { width: 1440, height: 1000 }, locale: 'zh-CN' })).newPage()
  const errors = []
  const requests = []
  page.on('pageerror', error => errors.push(String(error)))
  page.on('response', response => {
    if (response.url().includes('/api/model_list/')) requests.push(response.status() + ' ' + response.url())
  })

  await page.goto('http://127.0.0.1:3015/settings/model', { waitUntil: 'domcontentloaded' })
  await page.waitForFunction(() => !document.querySelector('[data-boot-state]'), { timeout: 30000 })
  await page.waitForTimeout(1200)
  await page.locator('main button[aria-expanded]').first().click()
  await page.waitForTimeout(800)
  await page.getByRole('button', { name: /从服务商获取/ }).first().click()

  // The provider list is a live third-party call; give it room, then settle.
  await page.waitForTimeout(9000)
  const panel = await page.evaluate(() => {
    const text = document.querySelector('main').innerText
    const at = text.indexOf('服务商可选模型')
    return { panel: at >= 0 ? text.slice(at, at + 400) : null, toast: document.body.innerText.match(/获取模型列表失败[^\n]*/)?.[0] ?? null }
  })
  await page.locator('main').screenshot({ path: OUT + '/settings-model-remote.png' })
  fs.writeFileSync(OUT + '/settings-remote-probe.json', JSON.stringify({ ...panel, requests, errors }, null, 2), 'utf8')
  console.log(JSON.stringify({ ...panel, requests, errors }, null, 2))
  await browser.close()
})().catch(error => { console.error('PROBE FAILED', error); process.exit(1) })