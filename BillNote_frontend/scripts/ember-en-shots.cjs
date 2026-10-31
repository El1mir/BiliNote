const { chromium } = require('playwright')
const fs = require('fs')
const EXE =
  'C:/Users/Administrator/AppData/Local/ms-playwright/chromium-1248/chrome-win64/chrome.exe'
const BASE = 'http://127.0.0.1:3015'
const OUT = 'C:/Users/Administrator/Downloads'
const VIEWPORTS = [
  { name: 'desktop', width: 1440, height: 900 },
  { name: 'tablet', width: 834, height: 1112 },
  { name: 'mobile', width: 390, height: 844 },
]
const ROUTES = [
  ['workspace', '/'],
  ['general', '/settings/general'],
  ['download', '/settings/download'],
  ['monitor', '/settings/monitor'],
]
;(async () => {
  const browser = await chromium.launch({ executablePath: EXE, args: ['--no-sandbox'] })
  const results = []
  for (const vp of VIEWPORTS) {
    const ctx = await browser.newContext({
      viewport: { width: vp.width, height: vp.height },
      deviceScaleFactor: 1,
    })
    await ctx.addInitScript(() => {
      try {
        localStorage.setItem('bilinote-locale', 'en-US')
      } catch (e) {}
    })
    const page = await ctx.newPage()
    const errors = []
    page.on('pageerror', e => errors.push(String(e.message).slice(0, 120)))
    for (const [name, route] of ROUTES) {
      await page.goto(BASE + route, { waitUntil: 'domcontentloaded', timeout: 45000 })
      let ok = true
      try {
        await page.waitForFunction(() => !document.querySelector('[data-boot-state]'), null, {
          timeout: 30000,
        })
        await page.waitForSelector('main', { timeout: 15000 })
      } catch (e) {
        ok = false
      }
      await page.waitForTimeout(900)
      const file = OUT + '/ember4-en-' + vp.name + '-' + name + '.png'
      await page.screenshot({ path: file, fullPage: false })
      const metrics = await page.evaluate(() => ({
        bodyText: (document.body.innerText || '').replace(/\s+/g, ' ').trim().slice(0, 130),
        cjk: /[\u4e00-\u9fff]/.test(document.querySelector('main')?.innerText || '')
          ? 'main-has-cjk'
          : 'main-clean',
        overflowX:
          document.documentElement.scrollWidth > window.innerWidth + 1 ? 'overflow' : 'none',
      }))
      results.push({ vp: vp.name, route: name, ok, size: fs.statSync(file).size, ...metrics })
    }
    if (errors.length) results.push({ vp: vp.name, errors: errors.slice(0, 6) })
    await ctx.close()
  }
  await browser.close()
  console.log(JSON.stringify(results))
})().catch(e => {
  console.error('FAILED', String(e).slice(0, 400))
  process.exit(1)
})
