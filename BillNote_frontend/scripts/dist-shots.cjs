const { chromium } = require('playwright')
const EXE =
  'C:/Users/Administrator/AppData/Local/ms-playwright/chromium-1248/chrome-win64/chrome.exe'
const BASE = process.env.BASE || 'http://127.0.0.1:4174'
const OUT = 'C:/Users/Administrator/Downloads/'
const CASES = [
  { name: 'dist-desktop-zh', w: 1440, h: 900, locale: 'zh-CN', route: '/' },
  { name: 'dist-tablet-en', w: 834, h: 1112, locale: 'en-US', route: '/' },
  { name: 'dist-mobile-zh', w: 390, h: 844, locale: 'zh-CN', route: '/' },
  {
    name: 'dist-desktop-en-settings',
    w: 1440,
    h: 900,
    locale: 'en-US',
    route: '/settings/general',
  },
  { name: 'dist-mobile-zh-settings', w: 390, h: 844, locale: 'zh-CN', route: '/settings/general' },
]
;(async () => {
  const b = await chromium.launch({ executablePath: EXE, args: ['--no-sandbox'] })
  const out = []
  for (const c of CASES) {
    const ctx = await b.newContext({ viewport: { width: c.w, height: c.h } })
    await ctx.addInitScript(loc => window.localStorage.setItem('bilinote-locale', loc), c.locale)
    const p = await ctx.newPage()
    const errors = []
    p.on('pageerror', e => errors.push(String(e).slice(0, 160)))
    await p.goto(BASE + c.route, { waitUntil: 'domcontentloaded' })
    await p.waitForSelector('main', { timeout: 45000 })
    await p.waitForFunction(() => !document.querySelector('[data-boot-state]'), null, {
      timeout: 45000,
    })
    await p.waitForTimeout(1500)
    await p.screenshot({ path: OUT + c.name + '.png' })
    const overflowX = await p.evaluate(() => {
      const de = document.documentElement
      return de.scrollWidth > de.clientWidth + 1
        ? 'scroll ' + de.scrollWidth + '>' + de.clientWidth
        : 'none'
    })
    const text = (await p.locator('main').innerText()).replace(/\n+/g, ' | ').slice(0, 220)
    out.push({ name: c.name, overflowX, errors, text })
    await ctx.close()
  }
  console.log(JSON.stringify(out, null, 1))
  await b.close()
})()
