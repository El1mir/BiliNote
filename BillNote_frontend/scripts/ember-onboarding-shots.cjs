const { chromium } = require('playwright')
const fs = require('fs')
const EXE =
  'C:/Users/Administrator/AppData/Local/ms-playwright/chromium-1248/chrome-win64/chrome.exe'
const OK = JSON.stringify({ code: 0, msg: 'success', data: 'mock-provider-id' })
const CASES = [
  { name: 'desktop-zh-step1', w: 1440, h: 900, locale: 'zh-CN', step: 1 },
  { name: 'desktop-en-step1', w: 1440, h: 900, locale: 'en-US', step: 1 },
  { name: 'desktop-zh-step2', w: 1440, h: 900, locale: 'zh-CN', step: 2 },
  { name: 'desktop-en-step3', w: 1440, h: 900, locale: 'en-US', step: 3 },
  { name: 'desktop-zh-step4', w: 1440, h: 900, locale: 'zh-CN', step: 4 },
  { name: 'mobile-zh-step2', w: 390, h: 844, locale: 'zh-CN', step: 2 },
  { name: 'mobile-zh-step3', w: 390, h: 844, locale: 'zh-CN', step: 3 },
  { name: 'tablet-zh-step4', w: 834, h: 1112, locale: 'zh-CN', step: 4 },
]
;(async () => {
  const browser = await chromium.launch({ executablePath: EXE, args: ['--no-sandbox'] })
  const out = []
  for (const c of CASES) {
    const ctx = await browser.newContext({ viewport: { width: c.w, height: c.h } })
    await ctx.addInitScript(l => {
      try {
        localStorage.setItem('bilinote-locale', l)
      } catch (e) {}
    }, c.locale)
    const page = await ctx.newPage()
    const errors = []
    page.on('pageerror', e => errors.push(String(e).slice(0, 160)))
    // Never let a screenshot run create a real provider / model row.
    await page.route('**/api/add_provider', r =>
      r.fulfill({ status: 200, contentType: 'application/json', body: OK })
    )
    await page.route('**/api/models', r =>
      r.fulfill({ status: 200, contentType: 'application/json', body: OK })
    )
    await page.route('**/api/connect_test', r =>
      r.fulfill({ status: 200, contentType: 'application/json', body: OK })
    )
    await page.route('**/api/transcriber_config', r =>
      r.request().method() === 'POST'
        ? r.fulfill({ status: 200, contentType: 'application/json', body: OK })
        : r.continue()
    )
    await page.goto('http://127.0.0.1:3015/onboarding', { waitUntil: 'domcontentloaded' })
    await page.waitForSelector('h1', { timeout: 45000 })
    await page.waitForTimeout(700)
    const nextName = c.locale === 'zh-CN' ? '下一步' : 'Next'
    const saveName = c.locale === 'zh-CN' ? '保存并下一步' : 'Save and continue'
    if (c.step > 1) {
      await page.getByRole('button', { name: nextName }).click()
      await page.waitForTimeout(400)
    }
    if (c.step > 2) {
      await page.fill('#onboarding-provider', 'Screenshot Provider')
      await page.getByRole('button', { name: saveName }).click()
      await page.waitForTimeout(1200)
    }
    if (c.step > 3) {
      await page.getByRole('button', { name: saveName }).click()
      await page.waitForTimeout(1200)
    }
    const file = 'C:/Users/Administrator/Downloads/ember-onboarding-' + c.name + '.png'
    await page.screenshot({ path: file, fullPage: true })
    const info = await page.evaluate(() => ({
      heading: document.querySelector('h1') ? document.querySelector('h1').textContent : null,
      stepTitle: document.querySelector('h2') ? document.querySelector('h2').textContent : null,
      overflowX: document.documentElement.scrollWidth > window.innerWidth + 1 ? 'yes' : 'none',
    }))
    out.push({ case: c.name, bytes: fs.statSync(file).size, errors, ...info })
    await ctx.close()
  }
  console.log(JSON.stringify(out, null, 1))
  await browser.close()
})().catch(e => {
  console.error('FAILED', String(e).slice(0, 400))
  process.exit(1)
})
