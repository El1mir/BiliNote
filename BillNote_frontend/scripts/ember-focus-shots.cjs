const { chromium } = require('playwright')
const BASE = 'http://127.0.0.1:3015'
const EXE =
  'C:/Users/Administrator/AppData/Local/ms-playwright/chromium-1248/chrome-win64/chrome.exe'
const OUT = 'C:/Users/Administrator/Downloads'
const CASES = [
  {
    name: 'focus-desktop-zh-settings',
    w: 1440,
    h: 900,
    route: '/settings/general',
    locale: 'zh-CN',
  },
  {
    name: 'focus-desktop-en-settings',
    w: 1440,
    h: 900,
    route: '/settings/general',
    locale: 'en-US',
  },
  { name: 'focus-mobile-zh-settings', w: 390, h: 844, route: '/settings/model', locale: 'zh-CN' },
  { name: 'focus-tablet-en-workspace', w: 834, h: 1112, route: '/', locale: 'en-US' },
]

;(async () => {
  const browser = await chromium.launch({ executablePath: EXE, args: ['--no-sandbox'] })
  const report = []
  for (const c of CASES) {
    const ctx = await browser.newContext({
      viewport: { width: c.w, height: c.h },
      deviceScaleFactor: 1,
    })
    await ctx.addInitScript(loc => {
      try {
        localStorage.setItem('bilinote-locale', loc)
      } catch (e) {}
    }, c.locale)
    const page = await ctx.newPage()
    const errors = []
    page.on('pageerror', e => errors.push(String(e)))
    await page.goto(BASE + c.route, { waitUntil: 'domcontentloaded' })
    await page.waitForSelector('main', { timeout: 45000 })
    await page.waitForFunction(() => !document.querySelector('[data-boot-state]'), null, {
      timeout: 45000,
    })
    await page.waitForTimeout(900)
    const overflowX = await page.evaluate(() =>
      document.documentElement.scrollWidth > window.innerWidth + 1 ? 'yes' : 'none'
    )
    const text = (await page.locator('main').innerText()).replace(/\s+/g, ' ').slice(0, 200)
    const path = OUT + '/' + c.name + '.png'
    await page.screenshot({ path, fullPage: false })
    report.push({ name: c.name, overflowX, errors, text })
    await ctx.close()
  }
  await browser.close()
  console.log(JSON.stringify(report, null, 1))
})()
